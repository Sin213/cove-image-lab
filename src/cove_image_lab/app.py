"""Application entry point. Boots QApplication and shows MainWindow."""
from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow
from .theme import build_qss


def _icon_path() -> Path | None:
    """Locate cove_icon.png for the running interpreter.

    Prefers the icon packaged with the installed wheel/sdist via
    ``importlib.resources`` (``cove_image_lab/assets/cove_icon.png``) so that
    a normal ``pip install`` of the package — including the ``cove-image-lab``
    console script — finds the icon without depending on a repo-root file.

    Falls back to walking up to a repo-root ``cove_icon.png`` for editable
    development trees that predate the packaged copy. No sibling repo is
    consulted.
    """
    try:
        ref = resources.files("cove_image_lab").joinpath("assets/cove_icon.png")
        if ref.is_file():
            return Path(str(ref))
    except (ModuleNotFoundError, FileNotFoundError, OSError, TypeError):
        pass
    here = Path(__file__).resolve()
    for parent in (here.parent, *here.parents):
        candidate = parent / "cove_icon.png"
        if candidate.exists():
            return candidate
    return None


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
