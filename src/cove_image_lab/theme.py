"""Cove visual theme. Centralized colors, spacing, and a QSS builder.

Pure data + a string builder. No business logic, no comparison logic.
"""
from __future__ import annotations

from dataclasses import dataclass


ACCENT = "#50e6cf"
ACCENT_HOVER = "#6ff0dc"
ACCENT_PRESSED = "#3ccab4"

BG_BASE = "#0e1113"          # near-black window
BG_SURFACE = "#15191c"       # cards, panels
BG_SURFACE_RAISED = "#1c2125"
BG_INPUT = "#0b0e10"

BORDER = "#262c31"
WINDOW_EDGE = "rgba(255, 255, 255, 0.18)"  # visible outer border on frameless QMainWindow
BORDER_STRONG = "#33393f"

TEXT_PRIMARY = "#e6ecef"
TEXT_MUTED = "#8a949b"
TEXT_DIM = "#5d666c"

DANGER = "#e26c6c"
WARNING = "#e2b06c"
OK = "#7adfb5"

RADIUS = 10
RADIUS_SM = 6
PAD = 12
GAP = 8


@dataclass(frozen=True)
class CovePalette:
    accent: str = ACCENT
    bg_base: str = BG_BASE
    bg_surface: str = BG_SURFACE
    border: str = BORDER
    text: str = TEXT_PRIMARY
    text_muted: str = TEXT_MUTED


def build_qss() -> str:
    """Application-wide QSS in the Cove design language."""
    return f"""
    QWidget {{
        background-color: {BG_BASE};
        color: {TEXT_PRIMARY};
        font-family: "Inter", "Segoe UI", "SF Pro Text", "Cantarell", sans-serif;
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background-color: {BG_BASE};
    }}
    QMainWindow {{
        border: 4px solid {WINDOW_EDGE};
    }}
    QLabel {{
        background: transparent;
        color: {TEXT_PRIMARY};
    }}
    QLabel[role="muted"] {{ color: {TEXT_MUTED}; }}
    QLabel[role="title"] {{
        color: {TEXT_PRIMARY};
        font-size: 14px;
        font-weight: 600;
        padding: 2px 0 6px 0;
    }}
    QLabel[role="status-ok"] {{ color: {OK}; }}
    QLabel[role="status-warn"] {{ color: {WARNING}; }}
    QLabel[role="status-error"] {{ color: {DANGER}; }}

    QFrame#card {{
        background-color: {BG_SURFACE};
        border: 1px solid {BORDER};
        border-radius: {RADIUS}px;
    }}
    QFrame#card[role="summary"] {{
        background-color: {BG_SURFACE_RAISED};
    }}

    QFrame#dropzone {{
        background-color: {BG_SURFACE};
        border: 1px dashed {BORDER_STRONG};
        border-radius: {RADIUS}px;
    }}
    QFrame#dropzone[active="true"] {{
        border: 1px dashed {ACCENT};
        background-color: #16201f;
    }}
    QPushButton {{
        background-color: {BG_SURFACE_RAISED};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_STRONG};
        border-radius: {RADIUS_SM}px;
        padding: 6px 14px;
        min-height: 22px;
    }}
    QPushButton:hover {{
        border-color: {ACCENT};
        color: {ACCENT};
    }}
    QPushButton:pressed {{
        background-color: {BG_SURFACE};
    }}
    QPushButton:disabled {{
        color: {TEXT_DIM};
        border-color: {BORDER};
    }}
    QPushButton[role="primary"] {{
        background-color: {ACCENT};
        color: #0b1413;
        border: 1px solid {ACCENT};
        font-weight: 600;
    }}
    QPushButton[role="primary"]:hover {{
        background-color: {ACCENT_HOVER};
        border-color: {ACCENT_HOVER};
        color: #0b1413;
    }}
    QPushButton[role="primary"]:pressed {{
        background-color: {ACCENT_PRESSED};
        border-color: {ACCENT_PRESSED};
    }}
    QPushButton[role="primary"]:disabled {{
        background-color: {BG_SURFACE_RAISED};
        color: {TEXT_DIM};
        border-color: {BORDER};
    }}
    QPushButton[role="icon"] {{
        padding: 4px 6px;
        min-width: 22px;
        min-height: 22px;
    }}
    QPushButton[role="header"] {{
        padding: 6px 14px;
        background-color: rgba(255, 255, 255, 16);
        border: 1px solid {BORDER_STRONG};
    }}
    QPushButton[role="header"]:checked {{
        background-color: {ACCENT};
        color: #0b1413;
        border-color: {ACCENT};
        font-weight: 600;
    }}
    QPushButton[role="header"]:hover:!checked {{
        border-color: {ACCENT};
        color: {ACCENT};
    }}

    QSlider {{
        background: transparent;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        background: {BORDER};
        border-radius: 2px;
    }}
    QSlider::sub-page:horizontal {{
        background: {ACCENT};
        border-radius: 2px;
    }}
    QSlider::add-page:horizontal {{
        background: {BORDER};
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 14px;
        height: 14px;
        margin: -6px 0;
        border-radius: 7px;
        background: {ACCENT};
        border: 1px solid {ACCENT_PRESSED};
    }}
    QSlider::handle:horizontal:hover {{
        background: {ACCENT_HOVER};
    }}

    QGraphicsView {{
        background-color: {BG_INPUT};
        border: 1px solid {BORDER};
        border-radius: {RADIUS_SM}px;
    }}

    QStatusBar {{
        background-color: {BG_SURFACE};
        color: {TEXT_MUTED};
        border-top: 1px solid {BORDER};
    }}

    QWidget#titleBar {{
        background-color: {BG_SURFACE};
        border-bottom: 1px solid {BORDER};
    }}
    QWidget#tbCenter {{
        background: transparent;
    }}
    QLabel#tbTitle {{
        color: {TEXT_PRIMARY};
        font-size: 14px;
        font-weight: 500;
        background: transparent;
    }}
    QLabel#tbPill {{
        color: {ACCENT};
        font-family: "Geist Mono", "SF Mono", Menlo, monospace;
        font-size: 10px;
        font-weight: 600;
        background: rgba(80, 230, 207, 36);
        border: 1px solid rgba(80, 230, 207, 90);
        border-radius: 11px;
        padding: 0 10px;
        min-height: 22px;
        max-height: 22px;
        letter-spacing: 0.4px;
    }}
    QPushButton#tbWinBtn {{
        background: transparent;
        border: none;
        color: {TEXT_MUTED};
        font-size: 14px;
        padding: 0;
        min-width: 28px;
        min-height: 28px;
        border-radius: 6px;
    }}
    QPushButton#tbWinBtn:hover {{
        background-color: rgba(255, 255, 255, 16);
        color: {TEXT_PRIMARY};
        border: none;
    }}
    QPushButton#tbWinBtn[variant="close"]:hover {{
        background-color: #e5484d;
        color: #ffffff;
    }}

    QToolTip {{
        background-color: {BG_SURFACE_RAISED};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_STRONG};
        padding: 4px 6px;
    }}

    QScrollBar:vertical, QScrollBar:horizontal {{
        background: {BG_BASE};
        border: none;
    }}
    QScrollBar:vertical {{ width: 10px; }}
    QScrollBar:horizontal {{ height: 10px; }}
    QScrollBar::handle {{
        background: {BORDER_STRONG};
        border-radius: 5px;
        min-height: 24px;
        min-width: 24px;
    }}
    QScrollBar::handle:hover {{ background: {ACCENT_PRESSED}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ background: none; border: none; height: 0; width: 0; }}
    """
