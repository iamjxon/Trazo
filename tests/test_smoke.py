"""Pruebas de humo sin pantalla (QT_QPA_PLATFORM=offscreen)."""
import pytest
from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainterPath
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsEllipseItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsSimpleTextItem,
)

from trazo import ops
from trazo.canvas import CanvasView, DocScene, PNode, build_pen_path
from trazo.export import export_pdf, export_png, export_svg
from trazo.model import Group, apply_attrs, item_scene_path, prepare


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def make_rect(scene, x, y, w, h, color="#ff0000"):
    it = QGraphicsRectItem(QRectF(x, y, w, h))
    apply_attrs(it, fill=QColor(color), stroke=QColor("#000000"), width=2.0)
    prepare(it)
    it.setZValue(scene.next_z())
    scene.addItem(it)
    return it


def test_roundtrip_all_item_types(app):
    sc = DocScene()
    make_rect(sc, 0, 0, 100, 50)
    e = QGraphicsEllipseItem(QRectF(10, 10, 60, 40))
    apply_attrs(e, fill=QColor("#00ff00"), stroke=None)
    prepare(e)
    sc.addItem(e)
    ln = QGraphicsLineItem(QLineF(0, 0, 50, 70))
    apply_attrs(ln, stroke=QColor("#0000ff"), width=3)
    prepare(ln)
    sc.addItem(ln)
    nodes = [PNode(QPointF(0, 0)), PNode(QPointF(100, 0)), PNode(QPointF(100, 100))]
    nodes[1].hout = QPointF(120, 10)
    nodes[1].hin = QPointF(80, -10)
    pi = QGraphicsPathItem(build_pen_path(nodes, True))
    apply_attrs(pi, fill=QColor("#ffff00"), stroke=QColor("#000000"), width=1)
    prepare(pi)
    sc.addItem(pi)
    t = QGraphicsSimpleTextItem("Hola\nmundo")
    prepare(t)
    sc.addItem(t)
    sc.commit()

    data = sc.to_dict()
    sc2 = DocScene()
    sc2.load_dict(data)
    assert sc2.to_dict() == data
    assert len(sc2.top_items()) == 5


def test_undo_redo(app):
    sc = DocScene()
    assert not sc.can_undo()
    make_rect(sc, 0, 0, 10, 10)
    assert sc.commit()
    assert len(sc.top_items()) == 1
    sc.undo()
    assert len(sc.top_items()) == 0
    sc.redo()
    assert len(sc.top_items()) == 1


def test_boolean_operations(app):
    sc = DocScene()
    a = make_rect(sc, 0, 0, 100, 100)
    b = make_rect(sc, 50, 50, 100, 100)
    a.setSelected(True)
    b.setSelected(True)
    assert ops.boolean(sc, "intersect")
    (res,) = sc.top_items()
    p = item_scene_path(res)
    assert p.contains(QPointF(75, 75))
    assert not p.contains(QPointF(10, 10))

    sc = DocScene()
    a = make_rect(sc, 0, 0, 100, 100)
    b = make_rect(sc, 50, 50, 100, 100)
    a.setSelected(True)
    b.setSelected(True)
    assert ops.boolean(sc, "trim")
    p = item_scene_path(sc.top_items()[0])
    assert p.contains(QPointF(10, 10))
    assert not p.contains(QPointF(75, 75))


def test_group_ungroup_and_transform(app):
    sc = DocScene()
    a = make_rect(sc, 0, 0, 10, 10)
    b = make_rect(sc, 50, 0, 10, 10)
    a.setSelected(True)
    b.setSelected(True)
    g = ops.group_selected(sc)
    assert isinstance(g, Group)
    assert len(sc.top_items()) == 1
    assert g.sceneBoundingRect().width() >= 60
    ops.rotate_selection(sc, 90)
    assert ops.ungroup_selected(sc)
    assert len(sc.top_items()) == 2


def test_clipboard_roundtrip(app):
    sc = DocScene()
    a = make_rect(sc, 0, 0, 10, 10)
    a.setSelected(True)
    text = ops.copy_data(sc)
    assert text.startswith(ops.CLIP_PREFIX)
    assert ops.paste_data(sc, text) == 1
    assert len(sc.top_items()) == 2


def test_exports(app, tmp_path):
    sc = DocScene()
    make_rect(sc, 20, 20, 200, 120)
    svg, png, pdf = tmp_path / "a.svg", tmp_path / "a.png", tmp_path / "a.pdf"
    export_svg(sc, str(svg))
    assert export_png(sc, str(png), 72)
    export_pdf(sc, str(pdf))
    for f in (svg, png, pdf):
        assert f.exists() and f.stat().st_size > 100


def test_draw_rectangle_with_mouse(app):
    sc = DocScene()
    view = CanvasView(sc)
    view.resize(800, 600)
    view.show()
    view.set_tool("rect")
    vp = view.viewport()
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(100, 100))
    QTest.mouseMove(vp, QPoint(220, 180))
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(220, 180))
    items = sc.top_items()
    assert len(items) == 1 and isinstance(items[0], QGraphicsRectItem)
    assert sc.can_undo()
