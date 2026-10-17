"""Punto de entrada de Trazo."""
from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication

from .window import MainWindow, apply_dark_theme


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Trazo")
    apply_dark_theme(app)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.open_path(sys.argv[1])
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
