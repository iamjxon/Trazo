"""Operaciones sobre la selección: agrupar, orden, alinear, transformar, booleanas, portapapeles."""
from __future__ import annotations

import json
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPen, QTransform
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsSimpleTextItem

from .model import (
    Group,
    copy_style,
    deserialize_item,
    item_scene_path,
    prepare,
    serialize_item,
    shape_path_local,
)

CLIP_PREFIX = "TRAZO1:"


def selected_sorted(scene):
    return sorted(scene.selectedItems(), key=lambda i: i.zValue())


def selection_rect(scene) -> QRectF | None:
    items = scene.selectedItems()
    if not items:
        return None
    r = items[0].sceneBoundingRect()
    for it in items[1:]:
        r = r.united(it.sceneBoundingRect())
    return r


def delete_selected(scene) -> bool:
    items = scene.selectedItems()
    for it in items:
        scene.removeItem(it)
    if items:
        scene.commit()
    return bool(items)


# ------------------------------------------------------------- grupos
def group_selected(scene):
    items = selected_sorted(scene)
    if len(items) < 2:
        return None
    z = max(i.zValue() for i in items)
    g = Group()
    scene.addItem(g)
    # transformaciones relativas al grupo (identidad): los hijos conservan su posición
    g.add_children(items)
    prepare(g)
    g.setZValue(z)
    scene.clearSelection()
    g.setSelected(True)
    scene.commit()
    return g


def ungroup_selected(scene) -> bool:
    groups = [i for i in scene.selectedItems() if isinstance(i, Group)]
    if not groups:
        return False
    scene.clearSelection()
    for g in groups:
        base_z = g.zValue()
        for n, c in enumerate(sorted(g.childItems(), key=lambda c: c.zValue())):
            st = c.sceneTransform()
            c.setParentItem(None)
            c.setPos(0, 0)
            c.setTransform(st)
            c.setZValue(base_z + n * 1e-3)
            prepare(c)
            c.setSelected(True)
        scene.removeItem(g)
    scene.commit()
    return True


# -------------------------------------------------------------- orden
def reorder(scene, mode: str) -> None:
    items = scene.top_items()
    sel = [i for i in items if i.isSelected()]
    if not sel:
        return
    rest = [i for i in items if not i.isSelected()]
    if mode == "front":
        order = rest + sel
    elif mode == "back":
        order = sel + rest
    else:
        order = list(items)
        if mode == "forward":
            for i in range(len(order) - 2, -1, -1):
                if order[i].isSelected() and not order[i + 1].isSelected():
                    order[i], order[i + 1] = order[i + 1], order[i]
        elif mode == "backward":
            for i in range(1, len(order)):
                if order[i].isSelected() and not order[i - 1].isSelected():
                    order[i], order[i - 1] = order[i - 1], order[i]
    for n, it in enumerate(order):
        it.setZValue(n)
    scene.commit()


# ------------------------------------------------------- transformar
def apply_scene_transform(items, S: QTransform) -> None:
    for it in items:
        m = it.sceneTransform() * S
        it.setPos(0, 0)
        it.setTransform(m)


def rotate_selection(scene, degrees: float) -> None:
    r = selection_rect(scene)
    if r is None:
        return
    c = r.center()
    S = QTransform()
    S.translate(c.x(), c.y())
    S.rotate(degrees)
    S.translate(-c.x(), -c.y())
    apply_scene_transform(scene.selectedItems(), S)
    scene.commit()


def flip_selection(scene, horizontal: bool) -> None:
    r = selection_rect(scene)
    if r is None:
        return
    c = r.center()
    S = QTransform()
    S.translate(c.x(), c.y())
    S.scale(-1 if horizontal else 1, 1 if horizontal else -1)
    S.translate(-c.x(), -c.y())
    apply_scene_transform(scene.selectedItems(), S)
    scene.commit()


def align(scene, mode: str) -> None:
    items = scene.selectedItems()
    if not items:
        return
    ref = scene.page if len(items) == 1 else selection_rect(scene)
    for it in items:
        r = it.sceneBoundingRect()
        dx = dy = 0.0
        if mode == "left":
            dx = ref.left() - r.left()
        elif mode == "hcenter":
            dx = ref.center().x() - r.center().x()
        elif mode == "right":
            dx = ref.right() - r.right()
        elif mode == "top":
            dy = ref.top() - r.top()
        elif mode == "vcenter":
            dy = ref.center().y() - r.center().y()
        elif mode == "bottom":
            dy = ref.bottom() - r.bottom()
        it.moveBy(dx, dy)
    scene.commit()


def distribute(scene, horizontal: bool) -> None:
    items = scene.selectedItems()
    if len(items) < 3:
        return
    key = (lambda i: i.sceneBoundingRect().center().x()) if horizontal else (lambda i: i.sceneBoundingRect().center().y())
    items = sorted(items, key=key)
    a, b = key(items[0]), key(items[-1])
    step = (b - a) / (len(items) - 1)
    for n, it in enumerate(items[1:-1], start=1):
        d = a + n * step - key(it)
        it.moveBy(d if horizontal else 0, 0 if horizontal else d)
    scene.commit()


# ---------------------------------------------------------- curvas
def convert_to_curves(scene) -> int:
    count = 0
    for it in scene.selectedItems():
        if isinstance(it, (QGraphicsPathItem, Group)):
            continue
        new = QGraphicsPathItem(shape_path_local(it))
        copy_style(it, new)
        if isinstance(it, QGraphicsSimpleTextItem):
            new.setPen(QPen(Qt.PenStyle.NoPen))
        new.setPos(it.pos())
        new.setTransform(it.transform())
        new.setZValue(it.zValue())
        scene.removeItem(it)
        prepare(new)
        scene.addItem(new)
        new.setSelected(True)
        count += 1
    if count:
        scene.commit()
    return count


def boolean(scene, mode: str) -> bool:
    """mode: weld (soldar), intersect (intersección), trim (recortar: inferior menos los demás)."""
    items = selected_sorted(scene)
    if len(items) < 2:
        return False
    paths = [item_scene_path(i) for i in items]
    res = paths[0]
    for p in paths[1:]:
        if mode == "weld":
            res = res.united(p)
        elif mode == "intersect":
            res = res.intersected(p)
        else:
            res = res.subtracted(p)
    if res.isEmpty():
        return False
    new = QGraphicsPathItem(res)
    copy_style(items[0], new)
    z = items[0].zValue()
    for it in items:
        scene.removeItem(it)
    new.setZValue(z)
    prepare(new)
    scene.addItem(new)
    scene.clearSelection()
    new.setSelected(True)
    scene.commit()
    return True


# --------------------------------------------------- portapapeles
def copy_data(scene) -> str | None:
    items = selected_sorted(scene)
    if not items:
        return None
    return CLIP_PREFIX + json.dumps([serialize_item(i) for i in items], separators=(",", ":"))


def paste_data(scene, text: str, offset: float = 12.0) -> int:
    if not text or not text.startswith(CLIP_PREFIX):
        return 0
    try:
        data = json.loads(text[len(CLIP_PREFIX):])
    except ValueError:
        return 0
    scene.clearSelection()
    z = scene.next_z()
    for n, d in enumerate(data):
        it = deserialize_item(d)
        prepare(it)
        it.setZValue(z + n)
        it.moveBy(offset, offset)
        scene.addItem(it)
        it.setSelected(True)
    if data:
        scene.commit()
    return len(data)


def duplicate(scene) -> int:
    text = copy_data(scene)
    return paste_data(scene, text) if text else 0


def nudge(scene, dx: float, dy: float) -> None:
    for it in scene.selectedItems():
        it.moveBy(dx, dy)
    scene.commit()


def angle_between(a: QPointF, b: QPointF) -> float:
    return math.degrees(math.atan2(b.y() - a.y(), b.x() - a.x()))
