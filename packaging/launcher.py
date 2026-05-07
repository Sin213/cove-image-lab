"""PyInstaller launcher for Cove Image Lab.

Uses absolute imports so PyInstaller can analyze the dependency graph
when this file is the frozen entry point. The in-tree
``src/cove_image_lab/__main__.py`` uses a relative import
(``from .app import main``) which is correct for ``python -m
cove_image_lab`` but fails when run as top-level ``__main__`` by the
PyInstaller bootloader.
"""
from __future__ import annotations

from cove_image_lab.app import main


if __name__ == "__main__":
    raise SystemExit(main())
