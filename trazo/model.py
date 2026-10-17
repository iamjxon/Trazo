"""Modelo: ítems del dibujo, estilos, (de)serialización y geometría."""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
)

FORMAT_VERSION = 1
MM = 96.0 / 25.4  # píxeles de escena por milímetro


def mm(v: float) -> float:
    return v * MM


def to_mm(v: float) -> float:
    return v / MM


UNSET = object()


@dataclass
class Style:
    fill: QColor | None = field(default_factory=lambda: QColor("#4f8cff"))
    stroke: QColor | None = field(default_factory=lambda: QColor("#1d1d1f"))
    width: float = 2.0
    font_family: str = "Segoe UI"
    font_size: float = 32.0


class Group(QGraphicsItem):
    """Grupo de objetos. Los hijos no son seleccionables por separado."""

    def boundingRect(self) -> QRectF:
        return self.childrenBoundingRect()

    def shape(self) -> QPainterPath:
        p = QPainterPath()
        p.addRect(self.childrenBoundingRect())
        return p

    def paint(self, painter, option, widget=None) -> None:  # noqa: D401
        pass

    def add_children(self, items) -> None:
        for it in items:
            it.setParentItem(self)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
            it.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            it.setSelected(False)
        self.prepareGeometryChange()
        self.update()


def prepare(item: QGraphicsItem) -> QGraphicsItem:
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
    item.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
    return item


# ---------------------------------------------------------------- estilos
def _pen(color: QColor | None, width: float) -> QPen:
    if color is None or width <= 0:
        return QPen(Qt.PenStyle.NoPen)
    p = QPen(QColor(color), width)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p


def _brush(color: QColor | None) -> QBrush:
    return QBrush(Qt.BrushStyle.NoBrush) if color is None else QBrush(QColor(color))


def _pen_parts(pen: QPen, default_width: float):
    if pen.style() == Qt.PenStyle.NoPen:
        return None, default_width
    return QColor(pen.color()), pen.widthF()


def apply_attrs(item, fill=UNSET, stroke=UNSET, width=UNSET, font_size=UNSET,
                font_family=UNSET, default_width: float = 1.0) -> None:
    """Aplica solo los atributos indicados (UNSET = no tocar)."""
    if isinstance(item, Group):
        for c in item.childItems():
            apply_attrs(c, fill, stroke, width, font_size, font_family, default_width)
        return
    if isinstance(item, QGraphicsSimpleTextItem):
        if fill is not UNSET:
            item.setBrush(_brush(fill))
        if font_size is not UNSET or font_family is not UNSET:
            f = item.font()
            if font_family is not UNSET:
                f.setFamily(font_family)
            if font_size is not UNSET:
                f.setPixelSize(max(1, int(font_size)))
            item.setFont(f)
        return
    if fill is not UNSET and hasattr(item, "setBrush"):
        item.setBrush(_brush(fill))
    if (stroke is not UNSET or width is not UNSET) and hasattr(item, "setPen"):
        col, w = _pen_parts(item.pen(), default_width)
        if stroke is not UNSET:
            col = stroke
        if width is not UNSET:
            w = width
        item.setPen(_pen(col, w))


def first_leaf(item):
    if isinstance(item, Group):
        for c in sorted(item.childItems(), key=lambda c: c.zValue()):
            r = first_leaf(c)
            if r is not None:
                return r
        return None
    return item


def item_style(item):
    """(relleno, contorno, grosor) del primer objeto hoja."""
    leaf = first_leaf(item)
    fill, stroke, width = None, None, 1.0
    if leaf is None:
        return fill, stroke, width
    if hasattr(leaf, "brush"):
        b = leaf.brush()
        fill = None if b.style() == Qt.BrushStyle.NoBrush else QColor(b.color())
    if hasattr(leaf, "pen"):
        p = leaf.pen()
        width = p.widthF() or 1.0
        stroke = None if p.style() == Qt.PenStyle.NoPen else QColor(p.color())
    return fill, stroke, width


def copy_style(src, dst) -> None:
    fill, stroke, width = item_style(src)
    apply_attrs(dst, fill=fill, stroke=stroke, width=width, default_width=width)


# ------------------------------------------------------------ geometría
def shape_path_local(item) -> QPainterPath:
    p = QPainterPath()
    if isinstance(item, QGraphicsRectItem):
        p.addRect(item.rect())
    elif isinstance(item, QGraphicsEllipseItem):
        p.addEllipse(item.rect())
    elif isinstance(item, QGraphicsPathItem):
        p = QPainterPath(item.path())
    elif isinstance(item, QGraphicsLineItem):
        ln = item.line()
        p.moveTo(ln.p1())
        p.lineTo(ln.p2())
    elif isinstance(item, QGraphicsSimpleTextItem):
        f = item.font()
        fm = QFontMetricsF(f)
        for n, line in enumerate(item.text().split("\n")):
            p.addText(0, fm.ascent() + n * fm.lineSpacing(), f, line)
    elif isinstance(item, Group):
        for c in item.childItems():
            p.addPath(c.mapToParent(shape_path_local(c)))
    return p


def item_scene_path(item) -> QPainterPath:
    return item.sceneTransform().map(shape_path_local(item))


def path_nodes(path: QPainterPath):
    """Rol de cada elemento: ('a', None) ancla, ('c', índice_ancla) punto de control."""
    n = path.elementCount()
    roles = [None] * n
    i, prev_anchor = 0, None
    while i < n:
        e = path.elementAt(i)
        if e.isCurveTo() and i + 2 < n:
            roles[i] = ("c", prev_anchor)
            roles[i + 1] = ("c", i + 2)
            roles[i + 2] = ("a", None)
            prev_anchor = i + 2
            i += 3
        else:
            roles[i] = ("a", None)
            prev_anchor = i
            i += 1
    return roles


# ------------------------------------------------------- serialización
def color_to(c: QColor | None):
    return None if c is None else c.name(QColor.NameFormat.HexArgb)


def color_from(s):
    return None if s is None else QColor(s)


def path_to_data(path: QPainterPath) -> list:
    out: list = []
    n = path.elementCount()
    i = 0
    start = None
    eps = 1e-9
    while i < n:
        e = path.elementAt(i)
        if e.isMoveTo():
            out.append(["M", e.x, e.y])
            start = (e.x, e.y)
            i += 1
        elif e.isLineTo():
            last = i == n - 1 or path.elementAt(i + 1).isMoveTo()
            if last and start and abs(e.x - start[0]) < eps and abs(e.y - start[1]) < eps:
                out.append(["Z"])
            else:
                out.append(["L", e.x, e.y])
            i += 1
        elif e.isCurveTo() and i + 2 < n:
            c2, en = path.elementAt(i + 1), path.elementAt(i + 2)
            out.append(["C", e.x, e.y, c2.x, c2.y, en.x, en.y])
            last = i + 3 >= n or path.elementAt(i + 3).isMoveTo()
            if last and start and abs(en.x - start[0]) < eps and abs(en.y - start[1]) < eps:
                out.append(["Z"])
            i += 3
        else:
            i += 1
    return out


def path_from_data(data: list) -> QPainterPath:
    p = QPainterPath()
    for seg in data:
        k = seg[0]
        if k == "M":
            p.moveTo(seg[1], seg[2])
        elif k == "L":
            p.lineTo(seg[1], seg[2])
        elif k == "C":
            p.cubicTo(*seg[1:7])
        elif k == "Z":
            p.closeSubpath()
    return p


def serialize_item(item) -> dict:
    t = item.transform()
    d: dict = {
        "pos": [item.x(), item.y()],
        "m": [t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy()],
        "z": item.zValue(),
        "visible": item.isVisible(),
    }
    if isinstance(item, Group):
        d["type"] = "group"
        d["children"] = [serialize_item(c) for c in sorted(item.childItems(), key=lambda c: c.zValue())]
        return d
    if hasattr(item, "brush"):
        b = item.brush()
        d["fill"] = None if b.style() == Qt.BrushStyle.NoBrush else color_to(b.color())
    if hasattr(item, "pen"):
        p = item.pen()
        d["stroke"] = None if p.style() == Qt.PenStyle.NoPen else color_to(p.color())
        d["width"] = p.widthF()
    if isinstance(item, QGraphicsRectItem):
        r = item.rect()
        d.update(type="rect", rect=[r.x(), r.y(), r.width(), r.height()])
    elif isinstance(item, QGraphicsEllipseItem):
        r = item.rect()
        d.update(type="ellipse", rect=[r.x(), r.y(), r.width(), r.height()])
    elif isinstance(item, QGraphicsLineItem):
        ln = item.line()
        d.update(type="line", line=[ln.x1(), ln.y1(), ln.x2(), ln.y2()])
    elif isinstance(item, QGraphicsPathItem):
        d.update(type="path", path=path_to_data(item.path()))
    elif isinstance(item, QGraphicsSimpleTextItem):
        f = item.font()
        size = f.pixelSize() if f.pixelSize() > 0 else int(f.pointSizeF() * 96 / 72)
        d.update(type="text", text=item.text(), font=[f.family(), size, f.bold(), f.italic()])
    else:
        raise TypeError(f"Tipo de ítem no soportado: {type(item)}")
    return d


def deserialize_item(d: dict) -> QGraphicsItem:
    t = d["type"]
    if t == "group":
        item = Group()
        item.add_children([deserialize_item(c) for c in d["children"]])
    elif t == "rect":
        item = QGraphicsRectItem(QRectF(*d["rect"]))
    elif t == "ellipse":
        item = QGraphicsEllipseItem(QRectF(*d["rect"]))
    elif t == "line":
        from PySide6.QtCore import QLineF
        item = QGraphicsLineItem(QLineF(*d["line"]))
    elif t == "path":
        item = QGraphicsPathItem(path_from_data(d["path"]))
    elif t == "text":
        item = QGraphicsSimpleTextItem(d["text"])
        fam, size, bold, ital = d["font"]
        f = QFont(fam)
        f.setPixelSize(max(1, int(size)))
        f.setBold(bool(bold))
        f.setItalic(bool(ital))
        item.setFont(f)
    else:
        raise ValueError(f"Tipo desconocido: {t}")
    if t != "group":
        if "fill" in d and hasattr(item, "setBrush"):
            item.setBrush(_brush(color_from(d["fill"])))
        if "stroke" in d and hasattr(item, "setPen"):
            item.setPen(_pen(color_from(d["stroke"]), d.get("width", 1.0)))
    item.setPos(*d["pos"])
    item.setTransform(QTransform(*d["m"]))
    item.setZValue(d["z"])
    item.setVisible(d.get("visible", True))
    return item


def item_label(item) -> str:
    if isinstance(item, Group):
        return f"Grupo ({len(item.childItems())})"
    if isinstance(item, QGraphicsRectItem):
        return "Rectángulo"
    if isinstance(item, QGraphicsEllipseItem):
        return "Elipse"
    if isinstance(item, QGraphicsLineItem):
        return "Línea"
    if isinstance(item, QGraphicsPathItem):
        return "Curva"
    if isinstance(item, QGraphicsSimpleTextItem):
        t = item.text().replace("\n", " ")
        return "Texto: " + (t[:24] + "…" if len(t) > 24 else t)
    return "Objeto"


def point_dist(a: QPointF, b: QPointF) -> float:
    return ((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2) ** 0.5
