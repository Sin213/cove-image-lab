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
from PySide6.QtCore import Qt, Signal
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
    QSizePolicy,
    QSlider,
    QSpinBox,
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
from .metadata_reader import Metadata, MetadataReadError, read_metadata
from .wipe_view import CompareWipeView


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
            btn.setProperty("role", "header")
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
        self.readout.setMinimumWidth(48)
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        lay = QGridLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
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

        # --- source + mode header -------------------------------------------
        header = QFrame()
        header.setObjectName("card")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(12, 10, 12, 10)
        hlay.setSpacing(8)

        title = QLabel("Forensics")
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
        source_label.setProperty("role", "muted")
        mode_label = QLabel("View")
        mode_label.setProperty("role", "muted")
        self.layout_label = QLabel("Layout")
        self.layout_label.setProperty("role", "muted")

        header_grid = QGridLayout()
        header_grid.setContentsMargins(0, 0, 0, 0)
        header_grid.setHorizontalSpacing(16)
        header_grid.setVerticalSpacing(2)
        header_grid.addWidget(source_label, 0, 0)
        header_grid.addWidget(self.source_toggle, 1, 0)
        header_grid.addWidget(mode_label, 0, 1)
        header_grid.addWidget(self.mode_toggle, 1, 1)
        header_grid.addWidget(self.layout_label, 2, 0)
        header_grid.addWidget(self.layout_toggle, 3, 0, 1, 2)
        header_grid.setColumnStretch(0, 0)
        header_grid.setColumnStretch(1, 1)

        hlay.addLayout(title_row)
        hlay.addLayout(header_grid)

        # --- ELA controls ---------------------------------------------------
        self.ela_quality = _LabeledSlider("JPEG quality", 1, 100, 75)
        self.ela_scale = _LabeledSlider("Error scale", 1, 40, 10, suffix="×")
        self.ela_brightness = _LabeledSlider("Brightness", -80, 160, 0)
        for w in (self.ela_quality, self.ela_scale, self.ela_brightness):
            w.valueChanged.connect(lambda _v: self._refresh())

        ela_card = QFrame()
        ela_card.setObjectName("card")
        ela_lay = QVBoxLayout(ela_card)
        ela_lay.setContentsMargins(12, 10, 12, 10)
        ela_lay.setSpacing(8)
        ela_title = QLabel("ELA controls")
        ela_title.setProperty("role", "title")
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
        noise_card.setObjectName("card")
        noise_lay = QVBoxLayout(noise_card)
        noise_lay.setContentsMargins(12, 10, 12, 10)
        noise_lay.setSpacing(8)
        noise_title = QLabel("Noise Map controls")
        noise_title.setProperty("role", "title")
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
        self.metadata_card.setObjectName("card")
        md_lay = QVBoxLayout(self.metadata_card)
        md_lay.setContentsMargins(12, 10, 12, 10)
        md_lay.setSpacing(6)
        md_title = QLabel("Metadata")
        md_title.setProperty("role", "title")
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

        controls_col = QVBoxLayout()
        controls_col.setSpacing(10)
        controls_col.addWidget(self.ela_card)
        controls_col.addWidget(self.noise_card)
        controls_col.addStretch(1)
        controls_col.addWidget(self.export_btn)

        body = QHBoxLayout()
        body.setSpacing(10)
        body.addLayout(controls_col, 1)
        body.addWidget(self.view_stack, 3)

        # --- human review notes (in-memory only, session-scoped) -----------
        notes_card = QFrame()
        notes_card.setObjectName("card")
        notes_lay = QVBoxLayout(notes_card)
        notes_lay.setContentsMargins(12, 10, 12, 10)
        notes_lay.setSpacing(6)

        notes_title = QLabel("Human Review Notes")
        notes_title.setProperty("role", "title")

        self.export_report_btn = QPushButton("Export Review Report")
        self.export_report_btn.setProperty("role", "header")
        self.export_report_btn.setEnabled(False)
        self.export_report_btn.setToolTip(
            "Save a local plain-text review report including session context and your notes."
        )
        self.export_report_btn.clicked.connect(self._on_export_report)

        notes_title_row = QHBoxLayout()
        notes_title_row.setContentsMargins(0, 0, 0, 0)
        notes_title_row.setSpacing(8)
        notes_title_row.addWidget(notes_title)
        notes_title_row.addStretch(1)
        notes_title_row.addWidget(self.export_report_btn)

        notes_hint = QLabel(NOTES_HINT)
        notes_hint.setProperty("role", "muted")
        notes_hint.setWordWrap(True)

        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(NOTES_PLACEHOLDER)
        self.notes_edit.setFixedHeight(110)
        self.notes_edit.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.notes_edit.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background-color: {theme.BG_INPUT};
                color: {theme.TEXT_PRIMARY};
                border: 1px solid {theme.BORDER};
                border-radius: {theme.RADIUS_SM}px;
                padding: 6px 8px;
                selection-background-color: {theme.ACCENT};
                selection-color: {theme.BG_INPUT};
            }}
            QPlainTextEdit:focus {{ border-color: {theme.ACCENT}; }}
            """
        )

        notes_lay.addLayout(notes_title_row)
        notes_lay.addWidget(notes_hint)
        notes_lay.addWidget(self.notes_edit)
        self.notes_card = notes_card

        # --- disclaimer (always visible) ------------------------------------
        disclaimer_card = QFrame()
        disclaimer_card.setObjectName("card")
        disclaimer_card.setProperty("role", "summary")
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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(header)
        root.addWidget(disclaimer_card)
        root.addLayout(body, 1)
        root.addWidget(self.notes_card)
        root.addWidget(self.status)

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
        try:
            if self._mode == self.MODE_ELA:
                view = error_level_analysis(
                    arr,
                    quality=self.ela_quality.value(),
                    scale=float(self.ela_scale.value()),
                    brightness=float(self.ela_brightness.value()),
                )
                label = (
                    f"ELA — quality {self.ela_quality.value()}, "
                    f"scale {self.ela_scale.value()}×, "
                    f"brightness {self.ela_brightness.value():+d}"
                )
            else:
                view = noise_map(
                    arr,
                    scale=float(self.noise_scale.value()),
                    brightness=float(self.noise_brightness.value()),
                )
                label = (
                    f"Noise Map — scale {self.noise_scale.value()}×, "
                    f"brightness {self.noise_brightness.value():+d}"
                )
        except ForensicError as e:
            self._last_view = None
            self.image_view.set_pixmap(None)
            self.image_view.set_toolbar_enabled(False)
            self.side_by_side.set_images(None, None)
            self.forensic_wipe.set_images(None, None)
            self.export_btn.setEnabled(False)
            self.status.setText(f"Could not analyze image: {e}")
            return
        self._last_view = view
        forensic_pix = _ndarray_to_pixmap(view)
        original_pix = _ndarray_to_pixmap(arr)
        self.image_view.set_pixmap(forensic_pix)
        self.image_view.set_toolbar_enabled(True)
        self.side_by_side.set_images(original_pix, forensic_pix)
        self.forensic_wipe.set_images(original_pix, forensic_pix)
        self.export_btn.setEnabled(True)
        self.status.setText(label + " — indicator only")

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
