"""Application entry point. Boots QApplication and shows MainWindow."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow, _icon_path
from .theme import build_qss


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    if hasattr(Qt, "AA_EnableHighDpiScaling"):
        QGuiApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, "AA_UseHighDpiPixmaps"):
        QGuiApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Cove Image Lab")
    app.setOrganizationName("Cove")

    icon = _icon_path()
    if icon is not None:
        app.setWindowIcon(QIcon(str(icon)))

    app.setStyleSheet(build_qss())

    win = MainWindow()
    if icon is not None:
        win.setWindowIcon(QIcon(str(icon)))
    win.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
