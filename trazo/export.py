"""Exportación a SVG, PNG y PDF (el área exportada es la página)."""
from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QMarginsF, QRectF, QSize, QSizeF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtSvg import QSvgGenerator

from .model import to_mm


@contextmanager
def _clean_selection(scene):
    selected = scene.selectedItems()
    scene.blockSignals(True)
    scene.clearSelection()
    try:
        yield
    finally:
        for it in selected:
            it.setSelected(True)
        scene.blockSignals(False)


def _hints(p: QPainter) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)


def export_svg(scene, path: str) -> None:
    page = scene.page
    w, h = page.width(), page.height()
    gen = QSvgGenerator()
    gen.setFileName(path)
    gen.setResolution(96)
    gen.setSize(QSize(round(w), round(h)))
    gen.setViewBox(QRectF(0, 0, w, h))
    gen.setTitle("Trazo")
    gen.setDescription("Exportado con Trazo")
    with _clean_selection(scene):
        p = QPainter(gen)
        _hints(p)
        scene.render(p, QRectF(0, 0, w, h), page)
        p.end()


def export_png(scene, path: str, dpi: int = 150) -> bool:
    page = scene.page
    k = dpi / 96.0
    w, h = max(1, round(page.width() * k)), max(1, round(page.height() * k))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    dpm = round(dpi / 0.0254)
    img.setDotsPerMeterX(dpm)
    img.setDotsPerMeterY(dpm)
    with _clean_selection(scene):
        p = QPainter(img)
        _hints(p)
        scene.render(p, QRectF(0, 0, w, h), page)
        p.end()
    return img.save(path, "PNG")


def export_pdf(scene, path: str) -> None:
    page = scene.page
    wr = QPdfWriter(path)
    wr.setResolution(300)
    wr.setTitle("Trazo")
    wr.setPageSize(QPageSize(QSizeF(to_mm(page.width()), to_mm(page.height())), QPageSize.Unit.Millimeter))
    wr.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    with _clean_selection(scene):
        p = QPainter(wr)
        _hints(p)
        scene.render(p, QRectF(0, 0, wr.width(), wr.height()), page)
        p.end()
