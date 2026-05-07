"""AIIndicatorView: a transparent, local-only AI indicator browser.

The tab surfaces metadata- and provenance-style indicators for whichever
loaded source the user picks (Image A or Image B) and pairs each row with a
plain-language explanation of why it may or may not matter.

The tab is a *review aid*. It never claims an image is AI-generated, fake,
real, authentic, manipulated, tampered, or verified, and never produces a
score, percentage, or summary verdict. Wording rules are tested by
``tests/test_ai_indicator_view.py`` and ``tests/test_help_content.py``.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .ai_indicator_engine import (
    Indicator,
    SEVERITY_POSSIBLE,
    SEVERITY_WEAK,
    SEVERITY_WORTH,
    analyze,
)
from .help_dialog import open_ai_indicator_help
from .metadata_reader import MetadataReadError, read_metadata


DISCLAIMER = (
    "Possible indicators only. This tab is a review aid and is not an "
    "authenticity determination."
)

EMPTY_HINT = "Load Image A or Image B to see possible indicators."

LIMITATIONS = [
    "Metadata can be missing, stripped, edited, or misleading.",
    "Absence of indicators does not mean an image was not generated.",
    "Presence of indicators does not prove generation or editing.",
    "Screenshots, recompression, social-media uploads, and editor exports "
    "can remove or change signals.",
    "This tab is a review aid, not a determination.",
]


_SEVERITY_COLORS = {
    SEVERITY_WEAK: theme.TEXT_MUTED,
    SEVERITY_POSSIBLE: theme.WARNING,
    SEVERITY_WORTH: theme.ACCENT,
}


class _ToggleRow(QWidget):
    """Mutually-exclusive header-style toggle (mirrors the redaction helper)."""

    selected = Signal(str)

    def __init__(
        self,
        options: list[tuple[str, str]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for key, label in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("role", "header")
            btn.setProperty("opt_key", key)
            btn.clicked.connect(
                lambda _checked=False, k=key: self.selected.emit(k)
            )
            self._group.addButton(btn)
            lay.addWidget(btn)
        lay.addStretch(1)
        self._buttons = list(self._group.buttons())

    def set_current(self, key: str) -> None:
        for btn in self._buttons:
            if btn.property("opt_key") == key:
                btn.setChecked(True)
                return


def _severity_chip(severity: str) -> QLabel:
    color = _SEVERITY_COLORS.get(severity, theme.TEXT_MUTED)
    chip = QLabel(severity)
    chip.setStyleSheet(
        f"color: {color}; "
        f"border: 1px solid {color}; "
        f"border-radius: 8px; "
        f"padding: 2px 8px; "
        f"font-size: 11px; "
        f"font-weight: 600;"
    )
    chip.setAlignment(Qt.AlignCenter)
    chip.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
    return chip


def _indicator_card(ind: Indicator) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    card.setProperty("role-card", "ai-indicator")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(6)

    head_row = QHBoxLayout()
    head_row.setContentsMargins(0, 0, 0, 0)
    head_row.setSpacing(8)

    title = QLabel(ind.label)
    title.setProperty("role", "title")
    title.setWordWrap(True)
    head_row.addWidget(title, 1)
    head_row.addWidget(_severity_chip(ind.severity), 0, Qt.AlignTop)

    obs = QLabel(ind.observation)
    obs.setWordWrap(True)

    why = QLabel(ind.explanation)
    why.setProperty("role", "muted")
    why.setWordWrap(True)

    lay.addLayout(head_row)
    lay.addWidget(obs)
    lay.addWidget(why)
    return card


def _empty_card(message: str) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 14, 12, 14)
    lay.setSpacing(0)
    msg = QLabel(message)
    msg.setProperty("role", "muted")
    msg.setWordWrap(True)
    msg.setAlignment(Qt.AlignCenter)
    lay.addWidget(msg)
    return card


def _error_card(message: str) -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(4)
    title = QLabel("Could not read image")
    title.setProperty("role", "title")
    body = QLabel(message)
    body.setProperty("role", "muted")
    body.setWordWrap(True)
    lay.addWidget(title)
    lay.addWidget(body)
    return card


def _limitations_card() -> QFrame:
    card = QFrame()
    card.setObjectName("card")
    lay = QVBoxLayout(card)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(4)
    title = QLabel("Limitations")
    title.setProperty("role", "title")
    lay.addWidget(title)
    for line in LIMITATIONS:
        b = QLabel(f"• {line}")
        b.setProperty("role", "muted")
        b.setWordWrap(True)
        lay.addWidget(b)
    return card


class AIIndicatorView(QWidget):
    """Tab content widget for the AI Indicator review aid.

    Per-source state. The view stores the loaded ndarray + Path for each
    slot so refreshes after a source switch do not need to re-load from
    disk metadata until rendering. ``set_image(slot, None, None)`` clears
    that slot.
    """

    SOURCE_A = "a"
    SOURCE_B = "b"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._image_a: np.ndarray | None = None
        self._image_b: np.ndarray | None = None
        self._path_a: Path | None = None
        self._path_b: Path | None = None
        self._source = self.SOURCE_A

        # --- header card ----------------------------------------------
        header = QFrame()
        header.setObjectName("card")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(12, 10, 12, 10)
        hlay.setSpacing(8)

        title = QLabel("AI Indicator")
        title.setProperty("role", "title")

        self.help_btn = QPushButton("How to use")
        self.help_btn.setProperty("role", "header")
        self.help_btn.clicked.connect(self._on_help)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.help_btn)

        self.disclaimer_label = QLabel(DISCLAIMER)
        self.disclaimer_label.setProperty("role", "muted")
        self.disclaimer_label.setWordWrap(True)

        source_label = QLabel("Source")
        source_label.setProperty("role", "muted")

        self.source_toggle = _ToggleRow(
            [(self.SOURCE_A, "Image A"), (self.SOURCE_B, "Image B")]
        )
        self.source_toggle.set_current(self.SOURCE_A)
        self.source_toggle.selected.connect(self._on_source_changed)

        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.setSpacing(8)
        source_row.addWidget(source_label)
        source_row.addWidget(self.source_toggle, 1)

        hlay.addLayout(title_row)
        hlay.addWidget(self.disclaimer_label)
        hlay.addLayout(source_row)

        # --- scrollable indicator body -------------------------------
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(10)
        self._body_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(self._body)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        # --- limitations card ----------------------------------------
        limitations = _limitations_card()

        # --- root ----------------------------------------------------
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(header)
        root.addWidget(scroll, 1)
        root.addWidget(limitations)

        self._refresh()

    # --- public wiring -----------------------------------------------
    def set_image(
        self,
        slot: str,
        arr: np.ndarray | None,
        path: Path | None,
    ) -> None:
        if slot == self.SOURCE_A:
            self._image_a = arr
            self._path_a = path
        elif slot == self.SOURCE_B:
            self._image_b = arr
            self._path_b = path
        else:
            return
        if slot == self._source:
            self._refresh()

    # --- helpers -----------------------------------------------------
    def current_indicators(self) -> list[Indicator]:
        """Return the indicator list for the active source.

        Empty list when no source is loaded or when the file cannot be
        read. Public so tests can assert engine-rendered content without
        scraping QWidget children.
        """
        path = self._current_path()
        if path is None:
            return []
        try:
            md = read_metadata(path)
        except MetadataReadError:
            return []
        return analyze(md)

    def _current_path(self) -> Path | None:
        return self._path_a if self._source == self.SOURCE_A else self._path_b

    def _on_source_changed(self, key: str) -> None:
        if key not in (self.SOURCE_A, self.SOURCE_B):
            return
        self._source = key
        self.source_toggle.set_current(key)
        self._refresh()

    def _on_help(self) -> None:
        open_ai_indicator_help(self)

    # --- rendering ---------------------------------------------------
    def _refresh(self) -> None:
        self._clear_body()
        path = self._current_path()
        if path is None:
            self._body_layout.insertWidget(
                self._body_layout.count() - 1,
                _empty_card(EMPTY_HINT),
            )
            return
        try:
            md = read_metadata(path)
        except MetadataReadError as e:
            self._body_layout.insertWidget(
                self._body_layout.count() - 1,
                _error_card(str(e)),
            )
            return
        rows = analyze(md)
        if not rows:
            self._body_layout.insertWidget(
                self._body_layout.count() - 1,
                _empty_card(
                    "No indicators were extractable from this file."
                ),
            )
            return
        for ind in rows:
            self._body_layout.insertWidget(
                self._body_layout.count() - 1,
                _indicator_card(ind),
            )

    def _clear_body(self) -> None:
        # Strip every widget item except the trailing stretch.
        i = 0
        while i < self._body_layout.count():
            item = self._body_layout.itemAt(i)
            w = item.widget() if item is not None else None
            if w is None:
                i += 1
                continue
            self._body_layout.takeAt(i)
            w.setParent(None)
            w.deleteLater()
