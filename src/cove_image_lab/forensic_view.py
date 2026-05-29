"""ForensicsPanel: Cove-themed UI for ELA, Noise Map, and Metadata views.

Displays an image-derived inspection map for the currently-selected source
(Image A or Image B) plus metadata read from the on-disk source file. The
panel never claims an image is fake, real, authentic, or AI-generated; a
permanent disclaimer makes the indicator-only framing explicit.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .diff_exporter import DiffExportError, export_png
from .forensic_engine import ForensicError, error_level_analysis, noise_map
from .help_dialog import open_forensics_help
from .image_view import LabeledView, SyncedImageView, ndarray_to_qimage
from .metadata_reader import MetadataReadError, read_metadata
from .wipe_view import CompareWipeView


class _ForensicWorker(QObject):
    """Runs ELA or noise-map computation on a background QThread.

    Emits ``finished(result_array, label)`` on success or
    ``error(message)`` on failure.  Both signals are connected in the
    main thread so Qt cross-thread queued connections guarantee that
    the slots run on the GUI thread.
    """

    finished = Signal(object, str)   # (np.ndarray, label_text)
    error = Signal(str)              # human-readable error message

    def __init__(
        self,
        mode: str,
        arr: np.ndarray,
        params: dict,
    ) -> None:
        super().__init__()
        self._mode = mode
        self._arr = arr
        self._params = params

    def run(self) -> None:
        try:
            if self._mode == "ela":
                view = error_level_analysis(
                    self._arr,
                    quality=self._params["quality"],
                    scale=self._params["scale"],
                    brightness=self._params["brightness"],
                )
                label = (
                    f"ELA — quality {self._params['quality']}, "
                    f"scale {self._params['scale']}×, "
                    f"brightness {self._params['brightness']:+d}"
                )
            else:
                view = noise_map(
                    self._arr,
                    scale=self._params["scale"],
                    brightness=self._params["brightness"],
                )
                label = (
                    f"Noise Map — scale {self._params['scale']}×, "
                    f"brightness {self._params['brightness']:+d}"
                )
        except ForensicError as e:
            self.error.emit(str(e))
            return
        self.finished.emit(view, label)


DISCLAIMER = (
    "Forensic views can reveal suspicious patterns, "
    "but they do not prove authenticity or manipulation."
)

NOTES_PLACEHOLDER = (
    "Write your own observations here. "
    "Notes are local and are not an authenticity determination."
)

NOTES_HINT = "Local to this session. Not an authenticity determination."

REVIEW_REPORT_CAUTION = (
    "This report is for visual inspection only and is not an authenticity determination."
)
REVIEW_REPORT_TITLE = "Cove Image Lab Review Report"
REVIEW_REPORT_DEFAULT_NAME = "cove_review_report.txt"

_MODE_LABELS = {
    "ela": "Error Level Analysis",
    "noise": "Noise Map",
    "metadata": "Metadata",
}
_LAYOUT_LABELS = {
    "single": "Single",
    "side_by_side": "Side-by-side",
    "wipe": "Wipe",
}


def _ndarray_to_pixmap(arr: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(ndarray_to_qimage(arr))


def _forensics_qss() -> str:
    """Forensics-only layout polish mirroring the reference hierarchy."""
    return f"""
    QFrame#forensicWorkspace {{
        background-color: {theme.BG_SURFACE};
        border: 1px solid {theme.BORDER};
        border-radius: 14px;
    }}
    QFrame#forensicHeader,
    QFrame#forensicPanel {{
        background-color: {theme.BG_SURFACE_RAISED};
        border: 1px solid {theme.BORDER};
        border-radius: {theme.RADIUS}px;
    }}
    QFrame#forensicDisclaimer {{
        background-color: rgba(226, 176, 108, 18);
        border: 1px solid rgba(226, 176, 108, 54);
        border-radius: {theme.RADIUS_SM}px;
    }}
    QLabel[role="forensic-title"] {{
        color: {theme.TEXT_MUTED};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 1px;
        text-transform: uppercase;
        padding: 0;
    }}
    QLabel[role="field-label"] {{
        color: {theme.TEXT_DIM};
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    QLabel[role="panel-title"] {{
        color: {theme.TEXT_MUTED};
        font-size: 12px;
        font-weight: 700;
        letter-spacing: 0.8px;
        text-transform: uppercase;
        padding: 0;
    }}
    QScrollArea#forensicSidebar {{
        background: transparent;
        border: none;
    }}
    QScrollArea#forensicSidebar > QWidget > QWidget {{
        background: transparent;
    }}
    QPushButton[role="segmented"] {{
        padding: 5px 11px;
        min-height: 22px;
        background-color: {theme.BG_INPUT};
        color: {theme.TEXT_MUTED};
        border: 1px solid {theme.BORDER};
        border-radius: {theme.RADIUS_SM}px;
    }}
    QPushButton[role="segmented"]:checked {{
        background-color: rgba(80, 230, 207, 34);
        color: {theme.ACCENT};
        border-color: rgba(80, 230, 207, 110);
        font-weight: 600;
    }}
    QPushButton[role="segmented"]:hover:!checked {{
        color: {theme.TEXT_PRIMARY};
        border-color: {theme.BORDER_STRONG};
        background-color: {theme.BG_SURFACE_RAISED};
    }}
    QPlainTextEdit#forensicNotes {{
        background-color: {theme.BG_INPUT};
        color: {theme.TEXT_PRIMARY};
        border: 1px solid {theme.BORDER};
        border-radius: {theme.RADIUS_SM}px;
        padding: 6px 8px;
        selection-background-color: {theme.ACCENT};
        selection-color: {theme.BG_INPUT};
    }}
    QPlainTextEdit#forensicNotes:focus {{
        border-color: {theme.ACCENT};
    }}
    """


class _ToggleRow(QWidget):
    """A horizontal row of mutually-exclusive header-style buttons."""

    selected = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        for key, label in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("role", "segmented")
            btn.setProperty("opt_key", key)
            btn.clicked.connect(lambda _checked=False, k=key: self.selected.emit(k))
            self._group.addButton(btn)
            lay.addWidget(btn)
        lay.addStretch(1)
        self._buttons = list(self._group.buttons())

    def set_current(self, key: str) -> None:
        for btn in self._buttons:
            if btn.property("opt_key") == key:
                btn.setChecked(True)
                return


class _LabeledSlider(QWidget):
    """Horizontal slider with a title label and a numeric readout."""

    valueChanged = Signal(int)

    def __init__(
        self,
        title: str,
        minimum: int,
        maximum: int,
        value: int,
        suffix: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._suffix = suffix

        self.title = QLabel(title)
        self.title.setProperty("role", "muted")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(minimum, maximum)
        self.slider.setValue(value)
        self.slider.valueChanged.connect(self._on_value)

        self.readout = QLabel("")
        self.readout.setProperty("role", "muted")
        # Wide enough for "-80", "100", "160", "40×" with a glyph margin so the
        # last digit doesn't 1-px-clip against the readout's own bounding rect.
        self.readout.setMinimumWidth(56)
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lay = QGridLayout(self)
        # Right margin keeps the readout off the card's inner edge.
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setHorizontalSpacing(8)
        lay.setVerticalSpacing(2)
        lay.addWidget(self.title, 0, 0)
        lay.addWidget(self.readout, 0, 1, alignment=Qt.AlignRight)
        lay.addWidget(self.slider, 1, 0, 1, 2)
        self._refresh_readout(value)

    def _on_value(self, v: int) -> None:
        self._refresh_readout(v)
        self.valueChanged.emit(v)

    def _refresh_readout(self, v: int) -> None:
        self.readout.setText(f"{v}{self._suffix}")

    def value(self) -> int:
        return int(self.slider.value())


class _MetadataTable(QTableWidget):
    """Two-column key/value table styled to match the Cove theme."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Field", "Value"])
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setAlternatingRowColors(False)
        self.setShowGrid(False)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.horizontalHeader().setStretchLastSection(True)
        # Don't propagate the table's preferred (column-sum) width up the layout
        # tree — otherwise QStackedWidget.sizeHint() picks up this card's wide
        # hint and forces the whole Forensics workspace wider than the window,
        # clipping every right-edge label in both the sidebar and the right
        # pane. The table scrolls horizontally inside its own frame instead.
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: {theme.BG_INPUT};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.BORDER};
                border-radius: {theme.RADIUS_SM}px;
                gridline-color: {theme.BORDER};
            }}
            QHeaderView::section {{
                background-color: {theme.BG_SURFACE_RAISED};
                color: {theme.TEXT_MUTED};
                padding: 6px 10px;
                border: none;
                border-bottom: 1px solid {theme.BORDER};
            }}
            QTableWidget::item {{ padding: 4px 8px; }}
            QTableWidget::item:selected {{
                background-color: rgba(80, 230, 207, 28);
                color: {theme.TEXT_PRIMARY};
            }}
            """
        )

    def set_rows(self, rows: list[tuple[str, str]]) -> None:
        self.setRowCount(len(rows))
        for i, (k, v) in enumerate(rows):
            self.setItem(i, 0, QTableWidgetItem(k))
            self.setItem(i, 1, QTableWidgetItem(v))


class ForensicsPanel(QWidget):
    """Forensics tab content: source picker, mode picker, controls, view."""

    MODE_ELA = "ela"
    MODE_NOISE = "noise"
    MODE_METADATA = "metadata"

    LAYOUT_SINGLE = "single"
    LAYOUT_SIDE_BY_SIDE = "side_by_side"
    LAYOUT_WIPE = "wipe"

    WIPE_NOTE = "Visual inspection only — not a strict diff."

    EXPORT_FILENAMES = {
        MODE_ELA: "cove_ela.png",
        MODE_NOISE: "cove_noise_map.png",
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._image_a: np.ndarray | None = None
        self._image_b: np.ndarray | None = None
        self._path_a: Path | None = None
        self._path_b: Path | None = None
        self._last_view: np.ndarray | None = None
        self._source = "a"
        self._mode = self.MODE_ELA
        self._layout = self.LAYOUT_SINGLE
        self._last_save_dir = ""
        self._worker: _ForensicWorker | None = None
        self._thread: QThread | None = None

        self.setStyleSheet(_forensics_qss())

        # --- source + mode header -------------------------------------------
        header = QFrame()
        header.setObjectName("forensicHeader")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(14, 12, 14, 12)
        hlay.setSpacing(12)

        title = QLabel("FORENSICS")
        title.setProperty("role", "forensic-title")

        self.help_btn = QPushButton("How to use")
        self.help_btn.setProperty("role", "header")
        self.help_btn.clicked.connect(self._on_help)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.help_btn)

        self.source_toggle = _ToggleRow([("a", "Image A"), ("b", "Image B")])
        self.source_toggle.set_current("a")
        self.source_toggle.selected.connect(self._on_source_changed)

        self.mode_toggle = _ToggleRow([
            (self.MODE_ELA, "Error Level Analysis"),
            (self.MODE_NOISE, "Noise Map"),
            (self.MODE_METADATA, "Metadata"),
        ])
        self.mode_toggle.set_current(self.MODE_ELA)
        self.mode_toggle.selected.connect(self._on_mode_changed)

        self.layout_toggle = _ToggleRow([
            (self.LAYOUT_SINGLE, "Single"),
            (self.LAYOUT_SIDE_BY_SIDE, "Side-by-side"),
            (self.LAYOUT_WIPE, "Wipe"),
        ])
        self.layout_toggle.set_current(self.LAYOUT_SINGLE)
        self.layout_toggle.selected.connect(self._on_layout_changed)

        source_label = QLabel("Source")
        source_label.setProperty("role", "field-label")
        mode_label = QLabel("View")
        mode_label.setProperty("role", "field-label")
        self.layout_label = QLabel("Layout")
        self.layout_label.setProperty("role", "field-label")

        header_grid = QGridLayout()
        header_grid.setContentsMargins(0, 0, 0, 0)
        header_grid.setHorizontalSpacing(18)
        header_grid.setVerticalSpacing(6)
        header_grid.addWidget(source_label, 0, 0)
        header_grid.addWidget(self.source_toggle, 1, 0)
        header_grid.addWidget(mode_label, 0, 1)
        header_grid.addWidget(self.mode_toggle, 1, 1)
        header_grid.addWidget(self.layout_label, 0, 2)
        header_grid.addWidget(self.layout_toggle, 1, 2)
        header_grid.setColumnStretch(0, 0)
        header_grid.setColumnStretch(1, 0)
        header_grid.setColumnStretch(2, 1)

        hlay.addLayout(title_row)
        hlay.addLayout(header_grid)

        # --- ELA controls ---------------------------------------------------
        self.ela_quality = _LabeledSlider("JPEG quality", 1, 100, 75)
        self.ela_scale = _LabeledSlider("Error scale", 1, 40, 10, suffix="×")
        self.ela_brightness = _LabeledSlider("Brightness", -80, 160, 0)
        for w in (self.ela_quality, self.ela_scale, self.ela_brightness):
            w.valueChanged.connect(lambda _v: self._refresh())

        ela_card = QFrame()
        ela_card.setObjectName("forensicPanel")
        ela_lay = QVBoxLayout(ela_card)
        ela_lay.setContentsMargins(12, 10, 12, 10)
        ela_lay.setSpacing(8)
        ela_title = QLabel("ELA controls")
        ela_title.setProperty("role", "panel-title")
        ela_hint = QLabel(
            "ELA highlights compression inconsistencies. Indicator only."
        )
        ela_hint.setProperty("role", "muted")
        ela_hint.setWordWrap(True)
        ela_lay.addWidget(ela_title)
        ela_lay.addWidget(ela_hint)
        ela_lay.addWidget(self.ela_quality)
        ela_lay.addWidget(self.ela_scale)
        ela_lay.addWidget(self.ela_brightness)
        self.ela_card = ela_card

        # --- Noise controls -------------------------------------------------
        self.noise_scale = _LabeledSlider("Scale", 1, 30, 4, suffix="×")
        self.noise_brightness = _LabeledSlider("Brightness", -80, 160, 0)
        for w in (self.noise_scale, self.noise_brightness):
            w.valueChanged.connect(lambda _v: self._refresh())

        noise_card = QFrame()
        noise_card.setObjectName("forensicPanel")
        noise_lay = QVBoxLayout(noise_card)
        noise_lay.setContentsMargins(12, 10, 12, 10)
        noise_lay.setSpacing(8)
        noise_title = QLabel("Noise Map controls")
        noise_title.setProperty("role", "panel-title")
        noise_hint = QLabel(
            "Noise Map highlights fine detail / noise differences. "
            "Indicator only."
        )
        noise_hint.setProperty("role", "muted")
        noise_hint.setWordWrap(True)
        noise_lay.addWidget(noise_title)
        noise_lay.addWidget(noise_hint)
        noise_lay.addWidget(self.noise_scale)
        noise_lay.addWidget(self.noise_brightness)
        self.noise_card = noise_card

        # --- view stack: forensic image vs metadata table -------------------
        self.image_view = LabeledView("Forensic view", with_zoom_toolbar=True)
        self.metadata_card = QFrame()
        self.metadata_card.setObjectName("forensicPanel")
        md_lay = QVBoxLayout(self.metadata_card)
        md_lay.setContentsMargins(12, 10, 12, 10)
        md_lay.setSpacing(6)
        md_title = QLabel("Metadata")
        md_title.setProperty("role", "panel-title")
        md_hint = QLabel(
            "Metadata may be missing, stripped, or altered. Absence is not proof."
        )
        md_hint.setProperty("role", "muted")
        md_hint.setWordWrap(True)
        self.metadata_table = _MetadataTable()
        self.metadata_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        md_lay.addWidget(md_title)
        md_lay.addWidget(md_hint)
        md_lay.addWidget(self.metadata_table, 1)

        self.side_by_side = SyncedImageView(
            left_label="Original",
            right_label="Forensic",
        )

        self.forensic_wipe = CompareWipeView(
            title="Wipe — Original vs Forensic",
            left_label="Original",
            right_label="Forensic",
            empty_hint="Load an image on the Compare tab to view the forensic wipe.",
        )
        self.forensic_wipe.set_note(self.WIPE_NOTE)

        self.view_stack = QStackedWidget()
        self.view_stack.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.view_stack.addWidget(self.image_view)         # single forensic view
        self.view_stack.addWidget(self.metadata_card)      # metadata table
        self.view_stack.addWidget(self.side_by_side)       # original | forensic
        self.view_stack.addWidget(self.forensic_wipe)      # wipe original vs forensic

        # --- export + status ------------------------------------------------
        self.export_btn = QPushButton("Export Result")
        self.export_btn.setProperty("role", "primary")
        self.export_btn.setToolTip(
            "Save the current ELA or Noise Map result as a PNG image"
        )
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export)

        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(20)

        metadata_controls = QFrame()
        metadata_controls.setObjectName("forensicPanel")
        metadata_controls_lay = QVBoxLayout(metadata_controls)
        metadata_controls_lay.setContentsMargins(12, 10, 12, 10)
        metadata_controls_lay.setSpacing(8)
        metadata_controls_title = QLabel("Metadata read")
        metadata_controls_title.setProperty("role", "panel-title")
        metadata_controls_hint = QLabel(
            "EXIF, XMP, and PNG text are read locally. No network lookups are performed."
        )
        metadata_controls_hint.setProperty("role", "muted")
        metadata_controls_hint.setWordWrap(True)
        metadata_controls_lay.addWidget(metadata_controls_title)
        metadata_controls_lay.addWidget(metadata_controls_hint)
        self.metadata_controls_card = metadata_controls

        # --- human review notes (in-memory only, session-scoped) -----------
        notes_card = QFrame()
        notes_card.setObjectName("forensicPanel")
        notes_lay = QVBoxLayout(notes_card)
        notes_lay.setContentsMargins(12, 10, 12, 10)
        notes_lay.setSpacing(6)

        notes_title = QLabel("Human Review Notes")
        notes_title.setProperty("role", "panel-title")

        self.export_report_btn = QPushButton("Export Review Report")
        self.export_report_btn.setProperty("role", "header")
        self.export_report_btn.setEnabled(False)
        self.export_report_btn.setToolTip(
            "Save a local plain-text review report including session context and your notes."
        )
        self.export_report_btn.clicked.connect(self._on_export_report)

        notes_hint = QLabel(NOTES_HINT)
        notes_hint.setProperty("role", "muted")
        notes_hint.setWordWrap(True)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setObjectName("forensicNotes")
        self.notes_edit.setPlaceholderText(NOTES_PLACEHOLDER)
        self.notes_edit.setFixedHeight(96)
        self.notes_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # Title and Export button stack vertically: the side-by-side row would
        # need ~290 px just for label + button text, leaving no slack inside a
        # 360 px-max sidebar.
        notes_lay.addWidget(notes_title)
        notes_lay.addWidget(notes_hint)
        notes_lay.addWidget(self.notes_edit)
        notes_lay.addWidget(self.export_report_btn)
        self.notes_card = notes_card

        # --- disclaimer (always visible) ------------------------------------
        disclaimer_card = QFrame()
        disclaimer_card.setObjectName("forensicDisclaimer")
        dl = QHBoxLayout(disclaimer_card)
        dl.setContentsMargins(12, 8, 12, 8)
        dl.setSpacing(8)
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {theme.WARNING};")
        msg = QLabel(DISCLAIMER)
        msg.setWordWrap(True)
        msg.setProperty("role", "muted")
        dl.addWidget(dot)
        dl.addWidget(msg, 1)

        # --- workspace body --------------------------------------------------
        sidebar_contents = QWidget()
        sidebar_contents.setObjectName("forensicSidebarContents")
        sidebar_lay = QVBoxLayout(sidebar_contents)
        sidebar_lay.setContentsMargins(0, 0, 0, 0)
        sidebar_lay.setSpacing(10)
        sidebar_lay.addWidget(self.ela_card)
        sidebar_lay.addWidget(self.noise_card)
        sidebar_lay.addWidget(self.metadata_controls_card)
        sidebar_lay.addWidget(self.export_btn)
        sidebar_lay.addWidget(self.notes_card)
        sidebar_lay.addStretch(1)
        sidebar_lay.addWidget(self.status)

        sidebar = QScrollArea()
        sidebar.setObjectName("forensicSidebar")
        sidebar.setWidgetResizable(True)
        sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        sidebar.setWidget(sidebar_contents)
        sidebar.setMinimumWidth(340)
        sidebar.setMaximumWidth(400)
        sidebar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(12)
        body.addWidget(sidebar)
        body.addWidget(self.view_stack, 1)

        workspace = QFrame()
        workspace.setObjectName("forensicWorkspace")
        workspace_lay = QVBoxLayout(workspace)
        workspace_lay.setContentsMargins(14, 14, 14, 14)
        workspace_lay.setSpacing(12)
        workspace_lay.addWidget(header)
        workspace_lay.addWidget(disclaimer_card)
        workspace_lay.addLayout(body, 1)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(workspace, 1)

        self._update_mode_visibility()
        self._refresh()

    # --- public wiring ------------------------------------------------------

    def set_image(self, slot: str, arr: np.ndarray | None, path: Path | None) -> None:
        if slot == "a":
            self._image_a = arr
            self._path_a = path
        elif slot == "b":
            self._image_b = arr
            self._path_b = path
        self._refresh()

    # --- internal -----------------------------------------------------------

    def _current_array(self) -> np.ndarray | None:
        return self._image_a if self._source == "a" else self._image_b

    def _current_path(self) -> Path | None:
        return self._path_a if self._source == "a" else self._path_b

    def _on_source_changed(self, key: str) -> None:
        self._source = key
        self._refresh()

    def _on_help(self) -> None:
        open_forensics_help(self)

    def _on_mode_changed(self, key: str) -> None:
        self._mode = key
        self._update_mode_visibility()
        self._refresh()

    def _on_layout_changed(self, key: str) -> None:
        self._layout = key
        self._update_mode_visibility()
        self._refresh()

    def _update_mode_visibility(self) -> None:
        self.ela_card.setVisible(self._mode == self.MODE_ELA)
        self.noise_card.setVisible(self._mode == self.MODE_NOISE)
        is_metadata = self._mode == self.MODE_METADATA
        self.metadata_controls_card.setVisible(is_metadata)
        # Layout toggle is meaningless for the metadata table.
        self.layout_label.setVisible(not is_metadata)
        self.layout_toggle.setVisible(not is_metadata)
        if is_metadata:
            self.view_stack.setCurrentWidget(self.metadata_card)
        elif self._layout == self.LAYOUT_SIDE_BY_SIDE:
            self.view_stack.setCurrentWidget(self.side_by_side)
        elif self._layout == self.LAYOUT_WIPE:
            self.view_stack.setCurrentWidget(self.forensic_wipe)
        else:
            self.view_stack.setCurrentWidget(self.image_view)

    def _refresh(self) -> None:
        if self._mode == self.MODE_METADATA:
            self._refresh_metadata()
        else:
            self._refresh_forensic_image()
        self._refresh_report_btn_state()

    def _refresh_report_btn_state(self) -> None:
        has_any_image = self._image_a is not None or self._image_b is not None
        self.export_report_btn.setEnabled(has_any_image)

    def _refresh_forensic_image(self) -> None:
        arr = self._current_array()
        if arr is None:
            self._cancel_worker()
            self._last_view = None
            self.image_view.set_pixmap(None)
            self.image_view.set_toolbar_enabled(False)
            self.side_by_side.set_images(None, None)
            self.forensic_wipe.set_images(None, None)
            self.export_btn.setEnabled(False)
            self.status.setText(
                f"Load Image {'A' if self._source == 'a' else 'B'} on the Compare tab to begin."
            )
            return

        # Cancel any in-flight worker before launching a new one.
        self._cancel_worker()
        self.status.setText("Analyzing…")
        self.export_btn.setEnabled(False)

        if self._mode == self.MODE_ELA:
            params = {
                "quality": self.ela_quality.value(),
                "scale": float(self.ela_scale.value()),
                "brightness": float(self.ela_brightness.value()),
            }
        else:
            params = {
                "scale": float(self.noise_scale.value()),
                "brightness": float(self.noise_brightness.value()),
            }

        worker = _ForensicWorker(self._mode, arr, params)
        thread = QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_forensic_done)
        worker.error.connect(self._on_forensic_error)
        # Clean up thread and worker objects after the thread finishes.
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        self._worker = worker
        self._thread = thread
        thread.start()

    def _cancel_worker(self) -> None:
        """Request stop of any running background worker/thread."""
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait()
        self._worker = None
        self._thread = None

    def _on_forensic_done(self, view: np.ndarray, label: str) -> None:
        self._last_view = view
        arr = self._current_array()
        forensic_pix = _ndarray_to_pixmap(view)
        self.image_view.set_pixmap(forensic_pix)
        self.image_view.set_toolbar_enabled(True)
        if arr is not None:
            original_pix = _ndarray_to_pixmap(arr)
            self.side_by_side.set_images(original_pix, forensic_pix)
            self.forensic_wipe.set_images(original_pix, forensic_pix)
        self.export_btn.setEnabled(True)
        self.status.setText(label + " — indicator only")

    def _on_forensic_error(self, message: str) -> None:
        self._last_view = None
        self.image_view.set_pixmap(None)
        self.image_view.set_toolbar_enabled(False)
        self.side_by_side.set_images(None, None)
        self.forensic_wipe.set_images(None, None)
        self.export_btn.setEnabled(False)
        self.status.setText(f"Could not analyze image: {message}")

    def _refresh_metadata(self) -> None:
        path = self._current_path()
        if path is None:
            self.metadata_table.set_rows([])
            self.export_btn.setEnabled(False)
            self.status.setText(
                f"Load Image {'A' if self._source == 'a' else 'B'} on the Compare tab to read metadata."
            )
            return
        try:
            md = read_metadata(path)
        except MetadataReadError as e:
            self.metadata_table.set_rows([("Error", str(e))])
            self.export_btn.setEnabled(False)
            self.status.setText("Metadata could not be read.")
            return
        rows = md.iter_rows()
        self.metadata_table.set_rows(rows)
        self.export_btn.setEnabled(False)  # metadata view is not exportable as image
        if md.has_metadata:
            self.status.setText("Metadata read locally — no network lookups performed.")
        else:
            self.status.setText("No EXIF/XMP/PNG metadata found in this file.")

    def _on_export(self) -> None:
        if self._last_view is None or self._mode == self.MODE_METADATA:
            return
        default_name = self.EXPORT_FILENAMES.get(self._mode, "cove_forensic.png")
        default_path = (
            str(Path(self._last_save_dir) / default_name)
            if self._last_save_dir
            else default_name
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export forensic result", default_path, "PNG (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path = path + ".png"
        try:
            out = export_png(self._last_view, path)
        except DiffExportError as e:
            self.status.setText(f"Export failed: {e}")
            return
        self._last_save_dir = str(Path(out).parent)
        self.status.setText(f"Exported {out}")

    def build_review_report(self, *, now: datetime | None = None) -> str:
        """Return the plain-text review report for the current panel state.

        Pure: no I/O, no Qt dialogs. ``now`` is injectable for tests; defaults
        to ``datetime.now()`` at call time.
        """
        if now is None:
            now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

        # Filenames only — never full paths — so a shared report does not
        # leak local usernames, folders, or client/project directory names.
        a_path = self._path_a.name if self._path_a is not None else "(not loaded)"
        b_path = self._path_b.name if self._path_b is not None else "(not loaded)"
        source_label = "A" if self._source == "a" else "B"
        mode_label = _MODE_LABELS.get(self._mode, self._mode)
        layout_label = _LAYOUT_LABELS.get(self._layout, self._layout)

        notes_text = self.notes_edit.toPlainText().rstrip()
        notes_block = notes_text if notes_text else "(none)"

        lines = [
            REVIEW_REPORT_TITLE,
            "=" * len(REVIEW_REPORT_TITLE),
            "",
            f"Generated: {timestamp}",
            "",
            f"Image A: {a_path}",
            f"Image B: {b_path}",
            "",
            f"Active source: {source_label}",
            f"View mode: {mode_label}",
            f"Layout: {layout_label}",
            "",
            "Human Review Notes:",
            "-" * len("Human Review Notes:"),
            notes_block,
            "",
            REVIEW_REPORT_CAUTION,
            "",
        ]
        return "\n".join(lines)

    def _on_export_report(self) -> None:
        if self._image_a is None and self._image_b is None:
            self.status.setText("Load Image A or Image B before exporting a review report.")
            return
        default_path = (
            str(Path(self._last_save_dir) / REVIEW_REPORT_DEFAULT_NAME)
            if self._last_save_dir
            else REVIEW_REPORT_DEFAULT_NAME
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Export review report", default_path, "Text files (*.txt)"
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path = path + ".txt"
        try:
            Path(path).write_text(self.build_review_report(), encoding="utf-8")
        except OSError as e:
            self.status.setText(f"Could not save report: {e}")
            return
        self._last_save_dir = str(Path(path).parent)
        self.status.setText(f"Exported {path}")
