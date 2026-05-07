"""In-app "How to use" dialogs for the Compare and Forensics tabs.

Pure presentation. No new dependencies. No external links. No browser opens.
The content lists are intentionally plain Python data so they can be diffed,
re-used, and tested without launching Qt.

Wording rules (kept consistent with the Forensics disclaimer) are enforced
by ``tests/test_help_content.py`` — see that file for the canonical list of
forbidden conclusive phrases and the negation-only rule for the word
"prove" / "proof".
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import theme


# ---------------------------------------------------------------------------
# Content (data only — importable without instantiating Qt widgets)
# ---------------------------------------------------------------------------

COMPARE_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "What the Compare tab is for",
        [
            "Use Compare when you want to compare Image A and Image B directly.",
            "Image A and Image B are the loaded source images.",
            "Compare/Wipe lets you visually slide between A and B.",
            "Diff is the strict pixel-difference view.",
        ],
    ),
    (
        "Threshold and Changed %",
        [
            "Threshold controls how much tiny pixel difference is ignored.",
            "Lower threshold = stricter.",
            "Higher threshold = ignores more small differences.",
            "Changed % means how many pixels changed beyond the current threshold.",
            "Changed % does NOT mean how visually different the whole image feels.",
        ],
    ),
    (
        "Threshold cheat sheet",
        [
            "0 — exact, pixel-perfect comparison.",
            "1–3 — tiny tolerance, useful for small anti-aliasing or render differences.",
            "5 — practical default for screenshots, light compression, and app/PDF QA.",
            "10–15 — useful for JPEG/WebP compression noise or social-media recompression.",
            "20+ — rough comparison; only larger visual changes remain.",
            "100 — ignores essentially everything; mostly a sanity check.",
        ],
    ),
    (
        "Common examples",
        [
            "App screenshot before vs after a patch.",
            "PDF render before vs after a patch.",
            "Original vs compressed image.",
            "Edited image vs original.",
        ],
    ),
    (
        "Mismatched dimensions",
        [
            "If image dimensions do not match, strict Diff and Export are disabled.",
            "The visual wipe can still preview mismatched dimensions by scaling B to A for preview only.",
            "The scaled wipe preview never affects strict diff math.",
        ],
    ),
]


FORENSICS_SECTIONS: list[tuple[str, list[str]]] = [
    (
        "What the Forensics tab is for",
        [
            "Use Forensics to inspect one selected image, Image A or Image B.",
            "Forensic views are indicators only.",
            "They do not prove authenticity or manipulation.",
            "Compression, screenshots, social-media recompression, text/subtitles, sharp edges, anime/illustration line art, and repeated resaves can all create suspicious-looking patterns.",
        ],
    ),
    (
        "Error Level Analysis (ELA)",
        [
            "ELA recompresses the image as JPEG and shows where the recompressed version differs from the original.",
            "It can reveal compression inconsistencies.",
            "Bright or standout regions can be worth inspecting.",
            "ELA does not prove an edit.",
        ],
    ),
    (
        "ELA controls",
        [
            "JPEG quality — controls the internal recompression quality. Lower values usually exaggerate compression differences more.",
            "Error scale — makes the ELA differences brighter / stronger.",
            "Brightness — raises or lowers the overall ELA view.",
        ],
    ),
    (
        "Noise Map",
        [
            "Noise Map emphasizes fine detail / noise patterns by suppressing smoother image content.",
            "It can help reveal abrupt texture or detail differences.",
            "It can also light up naturally from compression, blur, lighting, depth of field, texture, or low-light noise.",
            "Noise Map does not prove an edit.",
        ],
    ),
    (
        "Noise Map controls",
        [
            "Scale — controls the strength / visibility of the noise / detail map.",
            "Brightness — raises or lowers the overall Noise Map view.",
        ],
    ),
    (
        "Metadata",
        [
            "Metadata shows information embedded in the file, when present.",
            "This can include format, size, mode, camera / software tags, dates, GPS, XMP, or PNG text.",
            "Metadata can be missing, stripped, incomplete, or altered.",
            "Missing metadata does not prove anything by itself.",
            "GPS is displayed locally only. No online lookups.",
        ],
    ),
    (
        "Zoom controls (ELA / Noise Map)",
        [
            "Fit — scales the forensic view to fill the available area.",
            "100% — shows the forensic view at native pixel size for close inspection.",
            "The percentage readout shows the current on-screen scale.",
            "Use the mouse wheel to zoom in or out, and drag to pan when zoomed in.",
            "Zoom controls are unavailable in Metadata view and when no image is loaded.",
        ],
    ),
    (
        "Layout (ELA / Noise Map)",
        [
            "Single — shows the forensic view on its own.",
            "Side-by-side — shows the source image on the left labeled Original and the forensic view on the right labeled Forensic.",
            "In Side-by-side, mouse-wheel zoom and drag-pan stay in sync between the two panes.",
            "Wipe — overlays the source image and the forensic view in a single frame; drag the divider to reveal more of either side.",
            "Wipe is captioned \"Visual inspection only — not a strict diff\" because it is for the eye, not for pixel-difference math.",
            "The layout choice does not change ELA or Noise Map calculations.",
            "The Layout toggle is hidden in Metadata view because the metadata table is not an image.",
        ],
    ),
]


# ---------------------------------------------------------------------------
# Widget
# ---------------------------------------------------------------------------

def _section_card(heading: str, bullets: list[str]) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(4)

    h = QLabel(heading)
    h.setProperty("role", "title")
    lay.addWidget(h)

    for line in bullets:
        b = QLabel(f"• {line}")
        b.setWordWrap(True)
        b.setProperty("role", "muted")
        lay.addWidget(b)
    return card


class HelpDialog(QDialog):
    """Cove-themed scrollable "How to use" dialog with section cards."""

    def __init__(
        self,
        title: str,
        sections: list[tuple[str, list[str]]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(560, 620)

        header = QLabel(title)
        header.setStyleSheet(
            f"font-size: 16px; font-weight: 700; color: {theme.TEXT_PRIMARY};"
        )

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(10)
        for heading, bullets in sections:
            body_lay.addWidget(_section_card(heading, bullets))
        body_lay.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        close_btn = QPushButton("Close")
        close_btn.setProperty("role", "primary")
        close_btn.clicked.connect(self.accept)

        footer = QHBoxLayout()
        footer.addStretch(1)
        footer.addWidget(close_btn)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        root.addWidget(header)
        root.addWidget(scroll, 1)
        root.addLayout(footer)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def open_compare_help(parent: QWidget | None = None) -> None:
    """Open the modal Compare help dialog."""
    HelpDialog("Compare — How to use", COMPARE_SECTIONS, parent=parent).exec()


def open_forensics_help(parent: QWidget | None = None) -> None:
    """Open the modal Forensics help dialog."""
    HelpDialog("Forensics — How to use", FORENSICS_SECTIONS, parent=parent).exec()
