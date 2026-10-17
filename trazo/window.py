"""Ventana principal: menús, herramientas, propiedades, paleta, panel de objetos."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import (
    QAction,
    QActionGroup,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QSpinBox,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import __version__, ops
from .canvas import CanvasView, DocScene
from .export import export_pdf, export_png, export_svg
from .model import item_label, item_style, mm, to_mm

FILE_FILTER = "Documentos Trazo (*.trz);;Todos los archivos (*)"

TOOLS = [
    ("select", "Selección (V)", "V"),
    ("node", "Nodos (N)", "N"),
    ("rect", "Rectángulo (R)", "R"),
    ("ellipse", "Elipse (E)", "E"),
    ("line", "Línea (L)", "L"),
    ("pen", "Pluma Bézier (P)", "P"),
    ("free", "Mano alzada (F)", "F"),
    ("text", "Texto (T)", "T"),
]

PAGE_PRESETS = {
    "A3": (297, 420), "A4": (210, 297), "A5": (148, 210), "A6": (105, 148),
    "Carta": (215.9, 279.4), "Oficio": (215.9, 355.6), "Cuadrada 200": (200, 200),
}

PALETTE = [
    "#000000", "#303030", "#606060", "#909090", "#c0c0c0", "#ffffff",
    "#7f0000", "#d32f2f", "#ff5252", "#ff9800", "#ffc107", "#ffeb3b",
    "#cddc39", "#8bc34a", "#4caf50", "#009688", "#00bcd4", "#03a9f4",
    "#2196f3", "#3f51b5", "#673ab7", "#9c27b0", "#e91e63", "#795548",
    "#ffcdd2", "#ffe0b2", "#fff9c4", "#c8e6c9", "#b3e5fc", "#d1c4e9",
]


# ------------------------------------------------------------ apariencia
def apply_dark_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: "#2d2d30", QPalette.ColorRole.WindowText: "#e6e6e6",
        QPalette.ColorRole.Base: "#1e1e20", QPalette.ColorRole.AlternateBase: "#2d2d30",
        QPalette.ColorRole.Text: "#e6e6e6", QPalette.ColorRole.Button: "#3a3a3e",
        QPalette.ColorRole.ButtonText: "#e6e6e6", QPalette.ColorRole.ToolTipBase: "#3a3a3e",
        QPalette.ColorRole.ToolTipText: "#e6e6e6", QPalette.ColorRole.Highlight: "#2b7fd4",
        QPalette.ColorRole.HighlightedText: "#ffffff", QPalette.ColorRole.BrightText: "#ff5555",
        QPalette.ColorRole.Link: "#3fa7ff",
    }
    for role, c in roles.items():
        p.setColor(role, QColor(c))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#808080"))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor("#808080"))
    app.setPalette(p)


def tool_icon(name: str, color: QColor = QColor("#e6e6e6")) -> QIcon:
    pm = QPixmap(28, 28)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 2)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == "select":
        poly = QPolygonF([QPointF(8, 4), QPointF(8, 22), QPointF(12.5, 17.5), QPointF(16, 25),
                          QPointF(19, 23.5), QPointF(15.5, 16.5), QPointF(21, 16.5)])
        p.setBrush(color)
        p.drawPolygon(poly)
    elif name == "node":
        path = QPainterPath(QPointF(5, 22))
        path.cubicTo(8, 4, 20, 26, 23, 7)
        p.drawPath(path)
        p.setBrush(QColor("#2d2d30"))
        p.drawRect(QRectF(3, 20, 5, 5))
        p.drawRect(QRectF(20.5, 4.5, 5, 5))
    elif name == "rect":
        p.drawRect(QRectF(5, 8, 18, 13))
    elif name == "ellipse":
        p.drawEllipse(QRectF(4, 7, 20, 15))
    elif name == "line":
        p.drawLine(5, 23, 23, 5)
    elif name == "pen":
        path = QPainterPath(QPointF(5, 22))
        path.cubicTo(5, 6, 23, 22, 23, 6)
        p.drawPath(path)
        p.setBrush(color)
        p.drawEllipse(QPointF(5, 22), 2.2, 2.2)
        p.drawEllipse(QPointF(23, 6), 2.2, 2.2)
    elif name == "free":
        path = QPainterPath(QPointF(4, 17))
        path.cubicTo(7, 6, 10, 6, 12, 14)
        path.cubicTo(14, 22, 18, 22, 24, 9)
        p.drawPath(path)
    elif name == "text":
        f = QFont("Segoe UI", 15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, 28, 28), Qt.AlignmentFlag.AlignCenter, "T")
    p.end()
    return QIcon(pm)


def swatch_icon(color: QColor | None, size: int = 18) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    r = QRectF(1, 1, size - 2, size - 2)
    if color is None:
        p.fillRect(r, QColor("#ffffff"))
        p.setPen(QPen(QColor("#d32f2f"), 2))
        p.drawLine(QPointF(2, size - 2), QPointF(size - 2, 2))
    else:
        p.fillRect(r, color)
    p.setPen(QPen(QColor("#888888"), 1))
    p.drawRect(r)
    p.end()
    return QIcon(pm)


class PaletteBar(QWidget):
    """Paleta de colores: clic izquierdo = relleno, clic derecho = contorno."""

    SIZE = 18

    def __init__(self, on_pick, parent=None):
        super().__init__(parent)
        self._on_pick = on_pick
        self._colors: list[QColor | None] = [None] + [QColor(c) for c in PALETTE]
        self.setFixedHeight(self.SIZE + 8)
        self.setToolTip("Clic izquierdo: relleno · Clic derecho: contorno")

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        for i, c in enumerate(self._colors):
            r = QRectF(4 + i * (self.SIZE + 2), 4, self.SIZE, self.SIZE)
            if c is None:
                p.fillRect(r, QColor("#ffffff"))
                p.setPen(QPen(QColor("#d32f2f"), 2))
                p.drawLine(r.bottomLeft(), r.topRight())
            else:
                p.fillRect(r, c)
            p.setPen(QPen(QColor(0, 0, 0, 100), 1))
            p.drawRect(r)

    def mousePressEvent(self, e) -> None:
        i = int((e.position().x() - 4) // (self.SIZE + 2))
        if 0 <= i < len(self._colors):
            self._on_pick(self._colors[i], e.button() == Qt.MouseButton.RightButton)


# ================================================================ ventana
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(980, 640)
        self.resize(1320, 820)
        self.doc = DocScene()
        self.view = CanvasView(self.doc)
        self.path: str | None = None
        self._objs: list = []
        self._clip_cache = ""

        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.view, 1)
        lay.addWidget(PaletteBar(self._palette_pick))
        self.setCentralWidget(central)

        self._build_actions()
        self._build_menus()
        self._build_toolbars()
        self._build_objects_dock()
        self._build_statusbar()

        self.doc.aboutToReload.connect(self._forget_objs)
        self.doc.docChanged.connect(self._on_doc_changed)
        self.doc.selectionChanged.connect(self._on_selection)
        self.view.cursorMoved.connect(self._on_cursor)
        self.view.zoomChanged.connect(self._on_zoom)
        self.view.toolChanged.connect(self._on_tool_changed)
        self.view.message.connect(lambda m: self.statusBar().showMessage(m, 8000))
        self._on_doc_changed()
        self._on_selection()
        self.view.fit_page()
        self._update_title()

    # --------------------------------------------------------------- acciones
    def _act(self, text, slot, shortcut=None, checkable=False, tip=None) -> QAction:
        a = QAction(text, self)
        if shortcut is not None:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        if tip:
            a.setStatusTip(tip)
        a.triggered.connect(lambda *_: slot())
        return a

    def _build_actions(self) -> None:
        S = QKeySequence.StandardKey
        d, v = self.doc, self.view
        self.a_new = self._act("&Nuevo", self.new_document, S.New)
        self.a_open = self._act("&Abrir…", self.open_dialog, S.Open)
        self.a_save = self._act("&Guardar", self.save, S.Save)
        self.a_save_as = self._act("Guardar &como…", self.save_as, S.SaveAs)
        self.a_exp_svg = self._act("Exportar &SVG…", lambda: self.export("svg"))
        self.a_exp_png = self._act("Exportar &PNG…", lambda: self.export("png"))
        self.a_exp_pdf = self._act("Exportar P&DF…", lambda: self.export("pdf"))
        self.a_quit = self._act("&Salir", self.close, S.Quit)

        self.a_undo = self._act("&Deshacer", d.undo, S.Undo)
        self.a_redo = self._act("&Rehacer", d.redo, S.Redo)
        self.a_cut = self._act("Cor&tar", self.cut, S.Cut)
        self.a_copy = self._act("&Copiar", self.copy, S.Copy)
        self.a_paste = self._act("&Pegar", self.paste, S.Paste)
        self.a_dup = self._act("D&uplicar", lambda: ops.duplicate(d), "Ctrl+D")
        self.a_del = self._act("&Eliminar", lambda: ops.delete_selected(d), S.Delete)
        self.a_all = self._act("Seleccionar &todo", self.select_all, S.SelectAll)

        self.a_group = self._act("&Agrupar", lambda: ops.group_selected(d), "Ctrl+G")
        self.a_ungroup = self._act("&Desagrupar", lambda: ops.ungroup_selected(d), "Ctrl+U")
        self.a_curves = self._act("Convertir a &curvas", self.to_curves, "Ctrl+Q")
        self.a_weld = self._act("&Soldar (unión)", lambda: self.boolean("weld"))
        self.a_inter = self._act("&Intersección", lambda: self.boolean("intersect"))
        self.a_trim = self._act("&Recortar (inferior − superiores)", lambda: self.boolean("trim"))
        self.a_front = self._act("Traer al &frente", lambda: ops.reorder(d, "front"), "Ctrl+Shift+Up")
        self.a_back = self._act("Enviar al &fondo", lambda: ops.reorder(d, "back"), "Ctrl+Shift+Down")
        self.a_fwd = self._act("Subir un nivel", lambda: ops.reorder(d, "forward"), "Ctrl+Up")
        self.a_bwd = self._act("Bajar un nivel", lambda: ops.reorder(d, "backward"), "Ctrl+Down")
        self.a_rot_cw = self._act("Rotar 90° horario", lambda: ops.rotate_selection(d, 90))
        self.a_rot_ccw = self._act("Rotar 90° antihorario", lambda: ops.rotate_selection(d, -90))
        self.a_rot_any = self._act("Rotar ángulo…", self.rotate_dialog)
        self.a_flip_h = self._act("Voltear horizontal", lambda: ops.flip_selection(d, True))
        self.a_flip_v = self._act("Voltear vertical", lambda: ops.flip_selection(d, False))

        self.a_zoom_in = self._act("&Acercar", lambda: v.zoom_by(1.25, True), "Ctrl++")
        self.a_zoom_out = self._act("A&lejar", lambda: v.zoom_by(0.8, True), "Ctrl+-")
        self.a_zoom_100 = self._act("Zoom &100%", v.zoom_reset, "Ctrl+1")
        self.a_fit = self._act("Ajustar a &página", v.fit_page, "Ctrl+0")
        self.a_fit_sel = self._act("Ajustar a la &selección", v.fit_selection, "Ctrl+2")
        self.a_grid = self._act("Mostrar &cuadrícula", self.toggle_grid, "Ctrl+'", checkable=True)
        self.a_snap = self._act("&Ajustar a cuadrícula", self.toggle_snap, checkable=True)
        self.a_grid_size = self._act("Tamaño de cuadrícula…", self.grid_dialog)
        self.a_page = self._act("&Tamaño de página…", self.page_dialog)
        self.a_about = self._act("&Acerca de Trazo", self.about)

        self.tool_group = QActionGroup(self)
        self.tool_actions: dict[str, QAction] = {}
        for name, label, key in TOOLS:
            a = QAction(tool_icon(name), label, self)
            a.setCheckable(True)
            a.setShortcut(QKeySequence(key))
            a.setStatusTip(label)
            a.triggered.connect(lambda _c=False, n=name: self.view.set_tool(n))
            self.tool_group.addAction(a)
            self.tool_actions[name] = a
        self.tool_actions["select"].setChecked(True)

        # alineación
        self.align_actions = []
        for text, mode in [("Izquierda", "left"), ("Centro horizontal", "hcenter"), ("Derecha", "right"),
                           ("Arriba", "top"), ("Centro vertical", "vcenter"), ("Abajo", "bottom")]:
            self.align_actions.append(self._act(text, lambda m=mode: ops.align(d, m)))
        self.a_dist_h = self._act("Distribuir horizontal", lambda: ops.distribute(d, True))
        self.a_dist_v = self._act("Distribuir vertical", lambda: ops.distribute(d, False))

        for a in (self.a_new, self.a_open, self.a_save, self.a_save_as, self.a_undo, self.a_redo,
                  self.a_cut, self.a_copy, self.a_paste, self.a_dup, self.a_del, self.a_all, self.a_group,
                  self.a_ungroup, self.a_curves, self.a_front, self.a_back, self.a_fwd, self.a_bwd,
                  self.a_zoom_in, self.a_zoom_out, self.a_zoom_100, self.a_fit, self.a_fit_sel, self.a_grid):
            self.addAction(a)

    def _build_menus(self) -> None:
        mb = self.menuBar()
        m = mb.addMenu("&Archivo")
        m.addActions([self.a_new, self.a_open, self.a_save, self.a_save_as])
        m.addSeparator()
        m.addActions([self.a_exp_svg, self.a_exp_png, self.a_exp_pdf])
        m.addSeparator()
        m.addAction(self.a_quit)

        m = mb.addMenu("&Edición")
        m.addActions([self.a_undo, self.a_redo])
        m.addSeparator()
        m.addActions([self.a_cut, self.a_copy, self.a_paste, self.a_dup, self.a_del])
        m.addSeparator()
        m.addAction(self.a_all)

        m = mb.addMenu("&Objeto")
        m.addActions([self.a_group, self.a_ungroup, self.a_curves])
        m.addSeparator()
        sub = m.addMenu("Formas")
        sub.addActions([self.a_weld, self.a_inter, self.a_trim])
        sub = m.addMenu("Orden")
        sub.addActions([self.a_front, self.a_back, self.a_fwd, self.a_bwd])
        sub = m.addMenu("Alinear")
        sub.addActions(self.align_actions)
        sub.addSeparator()
        sub.addActions([self.a_dist_h, self.a_dist_v])
        sub = m.addMenu("Transformar")
        sub.addActions([self.a_rot_cw, self.a_rot_ccw, self.a_rot_any, self.a_flip_h, self.a_flip_v])

        m = mb.addMenu("&Ver")
        m.addActions([self.a_zoom_in, self.a_zoom_out, self.a_zoom_100, self.a_fit, self.a_fit_sel])
        m.addSeparator()
        m.addActions([self.a_grid, self.a_snap, self.a_grid_size])
        m.addSeparator()
        m.addAction(self.a_page)

        m = mb.addMenu("A&yuda")
        m.addAction(self.a_about)

    def _build_toolbars(self) -> None:
        tb = QToolBar("Herramientas")
        tb.setOrientation(Qt.Orientation.Vertical)
        tb.setIconSize(QSize(26, 26))
        tb.setMovable(False)
        for a in self.tool_actions.values():
            tb.addAction(a)
        self.addToolBar(Qt.ToolBarArea.LeftToolBarArea, tb)

        pb = QToolBar("Propiedades")
        pb.setMovable(False)
        pb.addWidget(QLabel(" Relleno "))
        self.fill_btn = QToolButton()
        self.fill_btn.setToolTip("Color de relleno")
        self.fill_btn.clicked.connect(self.pick_fill)
        pb.addWidget(self.fill_btn)
        pb.addWidget(QLabel("  Contorno "))
        self.stroke_btn = QToolButton()
        self.stroke_btn.setToolTip("Color de contorno")
        self.stroke_btn.clicked.connect(self.pick_stroke)
        pb.addWidget(self.stroke_btn)
        pb.addWidget(QLabel("  Grosor "))
        self.width_spin = QDoubleSpinBox()
        self.width_spin.setRange(0.1, 500)
        self.width_spin.setSingleStep(0.5)
        self.width_spin.setDecimals(1)
        self.width_spin.setSuffix(" px")
        self.width_spin.setValue(self.view.cur_style.width)
        self.width_spin.valueChanged.connect(lambda v: self.view.set_attrs(width=float(v)))
        pb.addWidget(self.width_spin)
        pb.addWidget(QLabel("  Texto "))
        self.font_spin = QSpinBox()
        self.font_spin.setRange(4, 800)
        self.font_spin.setSuffix(" px")
        self.font_spin.setValue(int(self.view.cur_style.font_size))
        self.font_spin.valueChanged.connect(lambda v: self.view.set_attrs(font_size=float(v)))
        pb.addWidget(self.font_spin)
        self._refresh_swatches(self.view.cur_style.fill, self.view.cur_style.stroke)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, pb)

    def _build_objects_dock(self) -> None:
        self.obj_list = QListWidget()
        self.obj_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.obj_list.itemSelectionChanged.connect(self._list_selection_changed)
        self.obj_list.itemChanged.connect(self._list_item_changed)
        dock = QDockWidget("Objetos", self)
        dock.setWidget(self.obj_list)
        dock.setMinimumWidth(190)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        self.lbl_sel = QLabel("")
        self.lbl_pos = QLabel("X: –  Y: –")
        self.lbl_zoom = QLabel("100%")
        for w in (self.lbl_sel, self.lbl_pos, self.lbl_zoom):
            w.setMinimumWidth(110)
            sb.addPermanentWidget(w)

    # -------------------------------------------------------------- señales
    def _on_cursor(self, x: float, y: float) -> None:
        self.lbl_pos.setText(f"X: {x:.1f} mm   Y: {y:.1f} mm")

    def _on_zoom(self, z: float) -> None:
        self.lbl_zoom.setText(f"{z * 100:.0f}%")

    def _on_tool_changed(self, tool: str) -> None:
        a = self.tool_actions.get(tool)
        if a is not None and not a.isChecked():
            a.setChecked(True)

    def _on_doc_changed(self) -> None:
        self.a_undo.setEnabled(self.doc.can_undo())
        self.a_redo.setEnabled(self.doc.can_redo())
        self._refresh_objects()
        self._update_title()

    def _on_selection(self) -> None:
        sel = self.doc.selectedItems()
        r = ops.selection_rect(self.doc)
        if r is None:
            self.lbl_sel.setText("Sin selección")
        else:
            n = len(sel)
            self.lbl_sel.setText(f"{n} obj. · {to_mm(r.width()):.1f} × {to_mm(r.height()):.1f} mm")
        if sel:
            fill, stroke, width = item_style(sel[0])
            self._refresh_swatches(fill, stroke)
            self.width_spin.blockSignals(True)
            self.width_spin.setValue(width)
            self.width_spin.blockSignals(False)
        self._sync_list_selection()

    def _update_title(self) -> None:
        name = os.path.basename(self.path) if self.path else "Sin título"
        self.setWindowTitle(f"{name}{'*' if self.doc.dirty else ''} — Trazo")

    # ------------------------------------------------------- panel de objetos
    def _refresh_objects(self) -> None:
        self._objs = list(reversed(self.doc.top_items()))
        self.obj_list.blockSignals(True)
        self.obj_list.clear()
        for it in self._objs:
            li = QListWidgetItem(item_label(it))
            li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked if it.isVisible() else Qt.CheckState.Unchecked)
            self.obj_list.addItem(li)
            li.setSelected(it.isSelected())
        self.obj_list.blockSignals(False)

    def _forget_objs(self) -> None:
        self._objs = []

    def _sync_list_selection(self) -> None:
        if len(self._objs) != self.obj_list.count():
            return
        self.obj_list.blockSignals(True)
        try:
            for i, it in enumerate(self._objs):
                self.obj_list.item(i).setSelected(it.isSelected())
        except RuntimeError:  # objeto ya destruido por una recarga; la lista se reconstruye enseguida
            pass
        finally:
            self.obj_list.blockSignals(False)

    def _list_selection_changed(self) -> None:
        rows = {ix.row() for ix in self.obj_list.selectedIndexes()}
        self.doc.blockSignals(True)
        self.doc.clearSelection()
        for r in rows:
            if 0 <= r < len(self._objs):
                self._objs[r].setSelected(True)
        self.doc.blockSignals(False)
        self.view.viewport().update()
        self._on_selection()

    def _list_item_changed(self, li: QListWidgetItem) -> None:
        r = self.obj_list.row(li)
        if 0 <= r < len(self._objs):
            self._objs[r].setVisible(li.checkState() == Qt.CheckState.Checked)
            self.doc.commit()

    # ----------------------------------------------------------- propiedades
    def _refresh_swatches(self, fill, stroke) -> None:
        self.fill_btn.setIcon(swatch_icon(fill))
        self.stroke_btn.setIcon(swatch_icon(stroke))

    def pick_fill(self) -> None:
        st = self.view.cur_style
        c = QColorDialog.getColor(st.fill or QColor("#ffffff"), self, "Color de relleno",
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.view.set_attrs(fill=c)
            self._refresh_swatches(c, self.view.cur_style.stroke)

    def pick_stroke(self) -> None:
        st = self.view.cur_style
        c = QColorDialog.getColor(st.stroke or QColor("#000000"), self, "Color de contorno",
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            self.view.set_attrs(stroke=c)
            self._refresh_swatches(self.view.cur_style.fill, c)

    def _palette_pick(self, color, is_stroke: bool) -> None:
        if is_stroke:
            self.view.set_attrs(stroke=color)
        else:
            self.view.set_attrs(fill=color)
        self._refresh_swatches(self.view.cur_style.fill, self.view.cur_style.stroke)

    # ------------------------------------------------------------ edición
    def copy(self) -> None:
        data = ops.copy_data(self.doc)
        if data:
            QApplication.clipboard().setText(data)

    def cut(self) -> None:
        self.copy()
        ops.delete_selected(self.doc)

    def paste(self) -> None:
        ops.paste_data(self.doc, QApplication.clipboard().text())

    def select_all(self) -> None:
        for it in self.doc.top_items():
            if it.isVisible():
                it.setSelected(True)

    def to_curves(self) -> None:
        if not ops.convert_to_curves(self.doc):
            self.statusBar().showMessage("Seleccione rectángulos, elipses, líneas o textos para convertirlos.", 5000)

    def boolean(self, mode: str) -> None:
        if not ops.boolean(self.doc, mode):
            self.statusBar().showMessage("Seleccione al menos dos objetos que se superpongan.", 5000)

    def rotate_dialog(self) -> None:
        v, ok = QInputDialog.getDouble(self, "Rotar", "Ángulo (grados, horario):", 15.0, -360, 360, 1)
        if ok:
            ops.rotate_selection(self.doc, v)

    # --------------------------------------------------------------- vista
    def toggle_grid(self) -> None:
        self.view.grid_on = self.a_grid.isChecked()
        self.view.viewport().update()

    def toggle_snap(self) -> None:
        self.view.snap_on = self.a_snap.isChecked()

    def grid_dialog(self) -> None:
        v, ok = QInputDialog.getDouble(self, "Cuadrícula", "Separación (mm):", self.view.grid_mm, 0.5, 200, 1)
        if ok:
            self.view.grid_mm = v
            self.view.viewport().update()

    def page_dialog(self) -> None:
        options = [f"{n} vertical" for n in PAGE_PRESETS] + [f"{n} horizontal" for n in PAGE_PRESETS]
        choice, ok = QInputDialog.getItem(self, "Tamaño de página", "Formato:", options, 1, False)
        if not ok:
            return
        name, orient = choice.rsplit(" ", 1)
        w, h = PAGE_PRESETS[name]
        if orient == "horizontal":
            w, h = h, w
        self.doc.set_page(mm(w), mm(h))
        self.view.fit_page()

    # ------------------------------------------------------------- archivos
    def _confirm_discard(self) -> bool:
        if not self.doc.dirty:
            return True
        r = QMessageBox.question(
            self, "Trazo", "Hay cambios sin guardar. ¿Desea guardarlos?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def new_document(self) -> None:
        if not self._confirm_discard():
            return
        self.doc.load_dict({"page": [mm(210), mm(297)], "items": []})
        self.doc.reset_history()
        self.path = None
        self._on_doc_changed()
        self.view.fit_page()

    def open_dialog(self) -> None:
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "Abrir", "", FILE_FILTER)
        if path:
            self.open_path(path)

    def open_path(self, path: str) -> bool:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("format") != "trazo":
                raise ValueError("El archivo no es un documento de Trazo.")
            self.doc.load_dict(data)
        except (OSError, ValueError, KeyError, TypeError) as ex:
            QMessageBox.critical(self, "Trazo", f"No se pudo abrir el archivo:\n{ex}")
            return False
        self.doc.reset_history()
        self.path = path
        self._on_doc_changed()
        self.view.fit_page()
        return True

    def save(self) -> bool:
        if not self.path:
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        path, _ = QFileDialog.getSaveFileName(self, "Guardar como", self.path or "dibujo.trz", FILE_FILTER)
        if not path:
            return False
        if not path.lower().endswith(".trz"):
            path += ".trz"
        return self._write(path)

    def _write(self, path: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.doc.to_dict(), f, ensure_ascii=False)
        except OSError as ex:
            QMessageBox.critical(self, "Trazo", f"No se pudo guardar:\n{ex}")
            return False
        self.path = path
        self.doc.dirty = False
        self._update_title()
        return True

    def export(self, kind: str) -> None:
        filters = {"svg": "SVG (*.svg)", "png": "PNG (*.png)", "pdf": "PDF (*.pdf)"}
        base = os.path.splitext(self.path)[0] if self.path else "dibujo"
        path, _ = QFileDialog.getSaveFileName(self, "Exportar", f"{base}.{kind}", filters[kind])
        if not path:
            return
        if not path.lower().endswith("." + kind):
            path += "." + kind
        try:
            if kind == "svg":
                export_svg(self.doc, path)
            elif kind == "pdf":
                export_pdf(self.doc, path)
            else:
                dpi, ok = QInputDialog.getInt(self, "Exportar PNG", "Resolución (DPI):", 150, 36, 1200)
                if not ok:
                    return
                if not export_png(self.doc, path, dpi):
                    raise OSError("No se pudo escribir la imagen.")
        except OSError as ex:
            QMessageBox.critical(self, "Trazo", f"No se pudo exportar:\n{ex}")
            return
        self.statusBar().showMessage(f"Exportado: {path}", 6000)

    def about(self) -> None:
        QMessageBox.about(
            self, "Acerca de Trazo",
            f"<b>Trazo {__version__}</b><br>Editor de gráficos vectoriales de código abierto.<br>"
            "Construido con Python y Qt (PySide6).",
        )

    def closeEvent(self, e) -> None:
        if self._confirm_discard():
            e.accept()
        else:
            e.ignore()
