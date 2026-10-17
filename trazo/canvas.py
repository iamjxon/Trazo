"""Escena y vista del lienzo: historial, herramientas de dibujo, nodos, zoom y selección."""
from __future__ import annotations

import json
import math

from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QInputDialog,
)

from . import ops
from .model import (
    FORMAT_VERSION,
    Style,
    apply_attrs,
    deserialize_item,
    mm,
    path_nodes,
    point_dist,
    prepare,
    serialize_item,
    to_mm,
)

ACCENT = QColor("#3fa7ff")
WHITE = QColor("#ffffff")
HANDLES = [(-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0)]
HANDLE_PX = 8.0
HIT_PX = 7.0


# ====================================================================== escena
class DocScene(QGraphicsScene):
    """Documento: página, objetos e historial (deshacer/rehacer por instantáneas)."""

    docChanged = Signal()
    aboutToReload = Signal()  # antes de destruir los objetos (deshacer, abrir, nuevo)
    MAX_HISTORY = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.NoIndex)
        self.setSceneRect(-60000, -60000, 120000, 120000)
        self.page = QRectF(0, 0, mm(210), mm(297))
        self.dirty = False
        self._hist: list[str] = []
        self._idx = -1
        self.reset_history()

    # -- consultas
    def top_items(self):
        return [i for i in self.items(Qt.SortOrder.AscendingOrder) if i.parentItem() is None]

    def next_z(self) -> float:
        return max((i.zValue() for i in self.top_items()), default=-1) + 1

    # -- (de)serialización
    def to_dict(self) -> dict:
        return {
            "format": "trazo",
            "version": FORMAT_VERSION,
            "page": [self.page.width(), self.page.height()],
            "items": [serialize_item(i) for i in self.top_items()],
        }

    def load_dict(self, d: dict) -> None:
        self.aboutToReload.emit()
        self.clear()
        w, h = d.get("page", [mm(210), mm(297)])
        self.page = QRectF(0, 0, w, h)
        for data in d.get("items", []):
            it = deserialize_item(data)
            prepare(it)
            self.addItem(it)
        self.docChanged.emit()

    def snapshot(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"))

    # -- historial
    def reset_history(self) -> None:
        self._hist = [self.snapshot()]
        self._idx = 0
        self.dirty = False

    def commit(self) -> bool:
        s = self.snapshot()
        if s == self._hist[self._idx]:
            return False
        del self._hist[self._idx + 1:]
        self._hist.append(s)
        if len(self._hist) > self.MAX_HISTORY:
            self._hist.pop(0)
        self._idx = len(self._hist) - 1
        self.dirty = True
        self.docChanged.emit()
        return True

    def can_undo(self) -> bool:
        return self._idx > 0

    def can_redo(self) -> bool:
        return self._idx < len(self._hist) - 1

    def undo(self) -> None:
        if self.can_undo():
            self._idx -= 1
            self._restore()

    def redo(self) -> None:
        if self.can_redo():
            self._idx += 1
            self._restore()

    def _restore(self) -> None:
        self.load_dict(json.loads(self._hist[self._idx]))
        self.dirty = True
        self.docChanged.emit()  # de nuevo, ya con dirty actualizado

    def set_page(self, w: float, h: float) -> None:
        self.page = QRectF(0, 0, w, h)
        self.commit()
        self.update()


# ======================================================================= nodo
class PNode:
    __slots__ = ("a", "hin", "hout")

    def __init__(self, a: QPointF):
        self.a = QPointF(a)
        self.hin = QPointF(a)
        self.hout = QPointF(a)


def build_pen_path(nodes, closed: bool, cursor: QPointF | None = None) -> QPainterPath:
    p = QPainterPath()
    if not nodes:
        return p
    p.moveTo(nodes[0].a)

    def seg(prev: PNode, c_in: QPointF, end: QPointF) -> None:
        if prev.hout == prev.a and c_in == end:
            p.lineTo(end)
        else:
            p.cubicTo(prev.hout, c_in, end)

    for prev, cur in zip(nodes, nodes[1:]):
        seg(prev, cur.hin, cur.a)
    if closed and len(nodes) > 2:
        seg(nodes[-1], nodes[0].hin, nodes[0].a)
        p.closeSubpath()
    elif cursor is not None:
        seg(nodes[-1], cursor, cursor)
    return p


def smooth_path(pts) -> QPainterPath:
    p = QPainterPath(pts[0])
    if len(pts) == 2:
        p.lineTo(pts[1])
        return p
    for i in range(1, len(pts) - 1):
        mid = (pts[i] + pts[i + 1]) / 2
        p.quadTo(pts[i], mid)
    p.lineTo(pts[-1])
    return p


# ====================================================================== vista
class CanvasView(QGraphicsView):
    cursorMoved = Signal(float, float)
    zoomChanged = Signal(float)
    toolChanged = Signal(str)
    styleChanged = Signal()
    message = Signal(str)

    def __init__(self, doc: DocScene, parent=None):
        super().__init__(doc, parent)
        self.doc = doc
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setBackgroundBrush(QColor("#4a4d52"))

        self.cur_style = Style()
        self.tool = "select"
        self.grid_on = False
        self.snap_on = False
        self.grid_mm = 10.0

        self._panning = False
        self._pan_last = QPointF()
        self._space = False
        self._drag_start: QPointF | None = None
        self._drag_cur: QPointF | None = None
        self._free_pts: list[QPointF] = []
        self._pen_nodes: list[PNode] = []
        self._pen_dragging = False
        self._pen_cursor: QPointF | None = None
        self._scale: dict | None = None
        self._node_item: QGraphicsPathItem | None = None
        self._node_drag: int | None = None
        self._node_sel: int | None = None
        self._press_selected = False

        doc.aboutToReload.connect(self._forget_items)
        doc.selectionChanged.connect(self._on_selection_changed)
        doc.docChanged.connect(self._on_selection_changed)
        doc.changed.connect(lambda *_: self.viewport().update())
        self.set_tool("select")

    # ------------------------------------------------------------ utilidades
    def zoom_factor(self) -> float:
        return self.transform().m11()

    def snap(self, p: QPointF) -> QPointF:
        if not self.snap_on:
            return QPointF(p)
        g = mm(self.grid_mm)
        return QPointF(round(p.x() / g) * g, round(p.y() / g) * g)

    def _scene_pos(self, e) -> QPointF:
        return self.mapToScene(e.position().toPoint())

    def _top_item_at(self, vpos):
        it = self.itemAt(vpos)
        while it is not None and it.parentItem() is not None:
            it = it.parentItem()
        return it

    # ------------------------------------------------------------------ zoom
    def zoom_by(self, f: float, center: bool = False) -> None:
        z = self.zoom_factor()
        nz = min(max(z * f, 0.02), 64.0)
        f = nz / z
        if center:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale(f, f)
        if center:
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.zoomChanged.emit(self.zoom_factor())

    def zoom_reset(self) -> None:
        self.zoom_by(1.0 / self.zoom_factor(), center=True)

    def fit_page(self) -> None:
        self.fitInView(self.doc.page.adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoomChanged.emit(self.zoom_factor())

    def fit_selection(self) -> None:
        r = ops.selection_rect(self.doc)
        if r is None:
            self.fit_page()
            return
        self.fitInView(r.adjusted(-20, -20, 20, 20), Qt.AspectRatioMode.KeepAspectRatio)
        self.zoomChanged.emit(self.zoom_factor())

    def wheelEvent(self, e) -> None:
        dy = e.angleDelta().y()
        if dy:
            self.zoom_by(1.0015 ** dy)

    # ------------------------------------------------------------ herramientas
    def set_tool(self, tool: str) -> None:
        self._cancel_interaction()
        self.tool = tool
        self.setDragMode(
            QGraphicsView.DragMode.RubberBandDrag if tool == "select" else QGraphicsView.DragMode.NoDrag
        )
        cursors = {
            "select": Qt.CursorShape.ArrowCursor,
            "node": Qt.CursorShape.ArrowCursor,
            "text": Qt.CursorShape.IBeamCursor,
        }
        self.viewport().setCursor(cursors.get(tool, Qt.CursorShape.CrossCursor))
        self._refresh_node_item()
        self.toolChanged.emit(tool)
        hint = {
            "node": "Herramienta de nodos: arrastre nodos y manijas. Ctrl+Q convierte a curvas.",
            "pen": "Pluma: clic = nodo recto, arrastrar = nodo curvo. Doble clic/Intro termina; clic en el primer nodo cierra.",
            "free": "Mano alzada: arrastre para dibujar.",
            "text": "Texto: haga clic en el lienzo.",
        }.get(tool, "")
        self.message.emit(hint)
        self.viewport().update()

    def _cancel_interaction(self) -> None:
        self._drag_start = self._drag_cur = None
        self._free_pts = []
        self._pen_nodes = []
        self._pen_dragging = False
        self._pen_cursor = None
        self._scale = None
        self._node_drag = None

    # --------------------------------------------------------- estilo/atributos
    def set_attrs(self, **kw) -> None:
        st = self.cur_style
        for k, v in kw.items():
            setattr(st, k, v)
        sel = self.doc.selectedItems()
        for it in sel:
            apply_attrs(it, default_width=st.width, **kw)
        if sel:
            self.doc.commit()
        self.styleChanged.emit()
        self.viewport().update()

    def _add_new(self, item, fill_override="keep") -> None:
        st = self.cur_style
        fill = st.fill if fill_override == "keep" else fill_override
        apply_attrs(item, fill=fill, stroke=st.stroke, width=st.width, default_width=st.width)
        prepare(item)
        item.setZValue(self.doc.next_z())
        self.doc.addItem(item)
        self.doc.clearSelection()
        item.setSelected(True)
        self.doc.commit()

    # ------------------------------------------------------------ nodos (edición)
    def _forget_items(self) -> None:
        """Suelta referencias a objetos que están por destruirse."""
        self._cancel_interaction()
        self._node_item = None
        self._node_sel = None

    def _on_selection_changed(self, *_):
        self._refresh_node_item()
        self.viewport().update()

    def _refresh_node_item(self) -> None:
        self._node_item = None
        self._node_sel = None
        if self.tool == "node":
            sel = self.doc.selectedItems()
            if len(sel) == 1 and isinstance(sel[0], QGraphicsPathItem):
                self._node_item = sel[0]
            elif len(sel) == 1:
                self.message.emit("Este objeto no es una curva: use Ctrl+Q (Convertir a curvas).")

    def _node_points(self):
        """Lista (índice, punto en escena, rol) de los elementos del trazado en edición."""
        it = self._node_item
        if it is None:
            return []
        path = it.path()
        roles = path_nodes(path)
        out = []
        for i, role in enumerate(roles):
            e = path.elementAt(i)
            out.append((i, it.mapToScene(QPointF(e.x, e.y)), role))
        return out

    def _hit_node(self, vpos: QPointF):
        pts = self._node_points()
        anchors = {i: p for i, p, r in pts if r[0] == "a"}
        for i, p, r in pts:  # anclas primero
            if r[0] == "a" and point_dist(QPointF(self.mapFromScene(p)), vpos) <= HIT_PX:
                return i
        for i, p, r in pts:
            if r[0] != "c" or r[1] not in anchors:
                continue
            if point_dist(p, anchors[r[1]]) * self.zoom_factor() < 1.0:
                continue
            if point_dist(QPointF(self.mapFromScene(p)), vpos) <= HIT_PX:
                return i
        return None

    def _node_move(self, idx: int, scene_pos: QPointF) -> None:
        it = self._node_item
        path = it.path()
        roles = path_nodes(path)
        e = path.elementAt(idx)
        target = it.mapFromScene(scene_pos)
        dx, dy = target.x() - e.x, target.y() - e.y
        if roles[idx][0] == "a":
            ox, oy = e.x, e.y
            anchors = [
                j for j, r in enumerate(roles)
                if r[0] == "a" and abs(path.elementAt(j).x - ox) < 1e-6 and abs(path.elementAt(j).y - oy) < 1e-6
            ]
            move = set(anchors)
            for j, r in enumerate(roles):
                if r[0] == "c" and r[1] in anchors:
                    move.add(j)
        else:
            move = {idx}
        for j in move:
            ej = path.elementAt(j)
            path.setElementPositionAt(j, ej.x + dx, ej.y + dy)
        it.setPath(path)

    # --------------------------------------------------------------- escalado
    def _sel_bbox(self) -> QRectF | None:
        return ops.selection_rect(self.doc)

    def _handle_scene_points(self, r: QRectF):
        pts = []
        for hx, hy in HANDLES:
            x = r.left() if hx < 0 else (r.right() if hx > 0 else r.center().x())
            y = r.top() if hy < 0 else (r.bottom() if hy > 0 else r.center().y())
            pts.append(QPointF(x, y))
        return pts

    def _hit_handle(self, vpos: QPointF):
        r = self._sel_bbox()
        if r is None:
            return None
        for i, p in enumerate(self._handle_scene_points(r)):
            if point_dist(QPointF(self.mapFromScene(p)), vpos) <= HIT_PX:
                return i
        return None

    def _begin_scale(self, idx: int) -> None:
        items = self.doc.selectedItems()
        self._scale = {
            "idx": idx,
            "bbox": self._sel_bbox(),
            "items": [(it, it.sceneTransform()) for it in items],
        }

    def _do_scale(self, sp: QPointF, uniform: bool) -> None:
        s = self._scale
        r: QRectF = s["bbox"]
        hx, hy = HANDLES[s["idx"]]
        ax = r.right() if hx < 0 else (r.left() if hx > 0 else r.center().x())
        ay = r.bottom() if hy < 0 else (r.top() if hy > 0 else r.center().y())
        cx = r.left() if hx < 0 else r.right()
        cy = r.top() if hy < 0 else r.bottom()
        sx = 1.0 if hx == 0 or abs(cx - ax) < 1e-6 else (sp.x() - ax) / (cx - ax)
        sy = 1.0 if hy == 0 or abs(cy - ay) < 1e-6 else (sp.y() - ay) / (cy - ay)
        if uniform and hx != 0 and hy != 0:
            k = max(abs(sx), abs(sy))
            sx, sy = math.copysign(k, sx), math.copysign(k, sy)
        if abs(sx) < 0.01:
            sx = 0.01 if sx >= 0 else -0.01
        if abs(sy) < 0.01:
            sy = 0.01 if sy >= 0 else -0.01
        S = QTransform()
        S.translate(ax, ay)
        S.scale(sx, sy)
        S.translate(-ax, -ay)
        for it, m0 in s["items"]:
            it.setPos(0, 0)
            it.setTransform(m0 * S)

    # ------------------------------------------------------------------ ratón
    def mousePressEvent(self, e) -> None:
        btn = e.button()
        if btn == Qt.MouseButton.MiddleButton or (btn == Qt.MouseButton.LeftButton and self._space):
            self._panning = True
            self._pan_last = e.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if btn == Qt.MouseButton.RightButton:
            if self.tool == "pen" and self._pen_nodes:
                self.finish_pen(False)
            return
        if btn != Qt.MouseButton.LeftButton:
            return
        sp = self._scene_pos(e)
        vpos = e.position()
        t = self.tool
        if t == "select":
            h = self._hit_handle(vpos)
            if h is not None:
                self._begin_scale(h)
                return
            self._press_selected = True
            super().mousePressEvent(e)
        elif t == "node":
            if self._node_item is not None:
                hit = self._hit_node(vpos)
                if hit is not None:
                    self._node_drag = hit
                    self._node_sel = hit
                    self.viewport().update()
                    return
            it = self._top_item_at(e.position().toPoint())
            self.doc.clearSelection()
            if it is not None:
                it.setSelected(True)
        elif t in ("rect", "ellipse", "line"):
            self._drag_start = self.snap(sp)
            self._drag_cur = QPointF(self._drag_start)
        elif t == "pen":
            self._pen_press(sp)
        elif t == "free":
            self._free_pts = [QPointF(sp)]
        elif t == "text":
            self._place_text(sp)

    def mouseMoveEvent(self, e) -> None:
        sp = self._scene_pos(e)
        self.cursorMoved.emit(to_mm(sp.x() - self.doc.page.x()), to_mm(sp.y() - self.doc.page.y()))
        if self._panning:
            d = e.position() - self._pan_last
            self._pan_last = e.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(d.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(d.y()))
            return
        shift = bool(e.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if self._scale is not None:
            self._do_scale(sp, shift)
            return
        if self._node_drag is not None and self._node_item is not None:
            self._node_move(self._node_drag, self.snap(sp))
            return
        t = self.tool
        if self._drag_start is not None and t in ("rect", "ellipse", "line"):
            cur = self.snap(sp)
            if shift:
                cur = self._constrain(self._drag_start, cur, t)
            self._drag_cur = cur
            self.viewport().update()
        elif t == "free" and self._free_pts:
            if point_dist(sp, self._free_pts[-1]) * self.zoom_factor() > 2.5:
                self._free_pts.append(QPointF(sp))
                self.viewport().update()
        elif t == "pen" and self._pen_nodes:
            sps = self.snap(sp)
            if self._pen_dragging:
                n = self._pen_nodes[-1]
                if point_dist(sps, n.a) * self.zoom_factor() >= 3:
                    n.hout = QPointF(sps)
                    n.hin = n.a * 2 - sps
            else:
                self._pen_cursor = sps
            self.viewport().update()
        elif t == "select":
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e) -> None:
        if self._panning and e.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton):
            self._panning = False
            self.viewport().setCursor(
                Qt.CursorShape.OpenHandCursor if self._space else self._tool_cursor()
            )
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        t = self.tool
        if self._scale is not None:
            self._scale = None
            self.doc.commit()
            self.viewport().update()
            return
        if self._node_drag is not None:
            self._node_drag = None
            self.doc.commit()
            return
        if t == "select":
            super().mouseReleaseEvent(e)
            if self._press_selected:
                self._press_selected = False
                self.doc.commit()
        elif t in ("rect", "ellipse", "line") and self._drag_start is not None:
            self._finish_shape()
        elif t == "free" and self._free_pts:
            self._finish_free()
        elif t == "pen":
            self._pen_dragging = False

    def mouseDoubleClickEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        t = self.tool
        if t == "pen":
            if len(self._pen_nodes) >= 2:
                self.finish_pen(False)
            else:
                self._cancel_interaction()
            self.viewport().update()
        elif t == "select":
            it = self._top_item_at(e.position().toPoint())
            if isinstance(it, QGraphicsSimpleTextItem):
                self._edit_text(it)
            elif isinstance(it, QGraphicsPathItem):
                self.set_tool("node")
            else:
                super().mouseDoubleClickEvent(e)

    # --------------------------------------------------------------- teclado
    def _tool_cursor(self):
        return {
            "select": Qt.CursorShape.ArrowCursor,
            "node": Qt.CursorShape.ArrowCursor,
            "text": Qt.CursorShape.IBeamCursor,
        }.get(self.tool, Qt.CursorShape.CrossCursor)

    def keyPressEvent(self, e) -> None:
        k = e.key()
        if k == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if self.tool == "pen" and self._pen_nodes:
            if k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.finish_pen(False)
                return
            if k == Qt.Key.Key_Escape:
                self._cancel_interaction()
                self.viewport().update()
                return
            if k == Qt.Key.Key_Backspace:
                self._pen_nodes.pop()
                self.viewport().update()
                return
        if k == Qt.Key.Key_Escape:
            self._cancel_interaction()
            self.doc.clearSelection()
            self.viewport().update()
            return
        if self.tool in ("select", "node") and k in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            step = 10.0 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            dx = {Qt.Key.Key_Left: -step, Qt.Key.Key_Right: step}.get(k, 0.0)
            dy = {Qt.Key.Key_Up: -step, Qt.Key.Key_Down: step}.get(k, 0.0)
            ops.nudge(self.doc, dx, dy)
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e) -> None:
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            self.viewport().setCursor(self._tool_cursor())
            return
        super().keyReleaseEvent(e)

    # --------------------------------------------------------- crear objetos
    @staticmethod
    def _constrain(a: QPointF, b: QPointF, tool: str) -> QPointF:
        dx, dy = b.x() - a.x(), b.y() - a.y()
        if tool == "line":
            ang = round(math.atan2(dy, dx) / (math.pi / 12)) * (math.pi / 12)
            d = math.hypot(dx, dy)
            return QPointF(a.x() + d * math.cos(ang), a.y() + d * math.sin(ang))
        k = max(abs(dx), abs(dy))
        return QPointF(a.x() + math.copysign(k, dx), a.y() + math.copysign(k, dy))

    def _finish_shape(self) -> None:
        a, b, t = self._drag_start, self._drag_cur, self.tool
        self._drag_start = self._drag_cur = None
        self.viewport().update()
        if a is None or b is None or point_dist(a, b) < 2:
            return
        if t == "line":
            item = QGraphicsLineItem(QLineF(a, b))
            self._add_new(item)
            return
        r = QRectF(a, b).normalized()
        if r.width() < 1 or r.height() < 1:
            return
        item = QGraphicsRectItem(r) if t == "rect" else QGraphicsEllipseItem(r)
        self._add_new(item)

    def _finish_free(self) -> None:
        pts = self._free_pts
        self._free_pts = []
        self.viewport().update()
        if len(pts) < 2:
            return
        item = QGraphicsPathItem(smooth_path(pts))
        self._add_new(item, fill_override=None)

    def _pen_press(self, sp: QPointF) -> None:
        sp = self.snap(sp)
        if len(self._pen_nodes) >= 3 and point_dist(sp, self._pen_nodes[0].a) * self.zoom_factor() < 9:
            self.finish_pen(True)
            return
        self._pen_nodes.append(PNode(sp))
        self._pen_dragging = True
        self.viewport().update()

    def finish_pen(self, closed: bool) -> None:
        nodes = self._pen_nodes
        self._cancel_interaction()
        self.viewport().update()
        if len(nodes) < 2:
            return
        item = QGraphicsPathItem(build_pen_path(nodes, closed))
        self._add_new(item, fill_override="keep" if closed else None)

    def _place_text(self, sp: QPointF) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Texto", "Contenido:")
        if not ok or not text.strip():
            return
        st = self.cur_style
        item = QGraphicsSimpleTextItem(text)
        f = QFont(st.font_family)
        f.setPixelSize(max(1, int(st.font_size)))
        item.setFont(f)
        item.setPos(sp)
        color = st.fill or st.stroke or QColor("#000000")
        apply_attrs(item, fill=color)
        prepare(item)
        item.setZValue(self.doc.next_z())
        self.doc.addItem(item)
        self.doc.clearSelection()
        item.setSelected(True)
        self.doc.commit()

    def _edit_text(self, item: QGraphicsSimpleTextItem) -> None:
        text, ok = QInputDialog.getMultiLineText(self, "Editar texto", "Contenido:", item.text())
        if ok and text.strip():
            item.setText(text)
            self.doc.commit()

    # ------------------------------------------------------------------ dibujo
    def drawBackground(self, painter, rect) -> None:
        painter.fillRect(rect, QColor("#4a4d52"))
        page = self.doc.page
        painter.fillRect(page.translated(5 / self.zoom_factor(), 5 / self.zoom_factor()), QColor(0, 0, 0, 70))
        painter.fillRect(page, QColor("#ffffff"))
        if self.grid_on:
            step = mm(self.grid_mm)
            z = self.zoom_factor()
            if step * z >= 5:
                pen = QPen(QColor(0, 0, 0, 38), 0)
                painter.setPen(pen)
                x0 = math.floor(max(rect.left(), page.left()) / step) * step
                x = x0
                while x <= min(rect.right(), page.right()):
                    painter.drawLine(QLineF(x, max(rect.top(), page.top()), x, min(rect.bottom(), page.bottom())))
                    x += step
                y = math.floor(max(rect.top(), page.top()) / step) * step
                while y <= min(rect.bottom(), page.bottom()):
                    painter.drawLine(QLineF(max(rect.left(), page.left()), y, min(rect.right(), page.right()), y))
                    y += step

    def _handle_rect(self, c: QPointF, s: float, size=HANDLE_PX) -> QRectF:
        return QRectF(c.x() - size * s / 2, c.y() - size * s / 2, size * s, size * s)

    def drawForeground(self, painter, rect) -> None:
        s = 1.0 / self.zoom_factor()
        painter.save()
        pen = QPen(ACCENT, 1)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        t = self.tool

        if self._drag_start is not None and self._drag_cur is not None:
            a, b = self._drag_start, self._drag_cur
            if t == "rect":
                painter.drawRect(QRectF(a, b).normalized())
            elif t == "ellipse":
                painter.drawEllipse(QRectF(a, b).normalized())
            elif t == "line":
                painter.drawLine(a, b)
        if self._free_pts:
            painter.drawPolyline(QPolygonF(self._free_pts))
        if self._pen_nodes:
            painter.drawPath(build_pen_path(self._pen_nodes, False, self._pen_cursor))
            painter.setBrush(WHITE)
            for n in self._pen_nodes:
                painter.drawRect(self._handle_rect(n.a, s, 6))
                if n.hout != n.a:
                    painter.drawLine(n.hin, n.hout)
                    painter.drawEllipse(self._handle_rect(n.hout, s, 5))
                    painter.drawEllipse(self._handle_rect(n.hin, s, 5))
            painter.setBrush(Qt.BrushStyle.NoBrush)

        if t == "select":
            r = self._sel_bbox()
            if r is not None:
                dash = QPen(ACCENT, 1, Qt.PenStyle.DashLine)
                dash.setCosmetic(True)
                painter.setPen(dash)
                painter.drawRect(r)
                painter.setPen(pen)
                painter.setBrush(WHITE)
                for c in self._handle_scene_points(r):
                    painter.drawRect(self._handle_rect(c, s))
        elif t == "node" and self._node_item is not None:
            pts = self._node_points()
            anchors = {i: p for i, p, r_ in pts if r_[0] == "a"}
            for i, p, r_ in pts:
                if r_[0] == "c" and r_[1] in anchors and point_dist(p, anchors[r_[1]]) * self.zoom_factor() >= 1:
                    painter.drawLine(anchors[r_[1]], p)
            for i, p, r_ in pts:
                if r_[0] == "a":
                    painter.setBrush(ACCENT if i == self._node_sel else WHITE)
                    painter.drawRect(self._handle_rect(p, s, 7))
                elif r_[1] in anchors and point_dist(p, anchors[r_[1]]) * self.zoom_factor() >= 1:
                    painter.setBrush(ACCENT if i == self._node_sel else WHITE)
                    painter.drawEllipse(self._handle_rect(p, s, 6))
        painter.restore()
