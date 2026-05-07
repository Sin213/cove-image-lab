"""MainWindow: drop slots, synced viewer, diff view, threshold slider, export."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QPoint, QSettings, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .compare_engine import (
    CompareResult,
    DimensionMismatchError,
    compare,
    reapply_threshold,
)
from .diff_exporter import DiffExportError, export_png
from .forensic_view import ForensicsPanel
from .help_dialog import open_compare_help
from .image_loader import ImageLoadError, load_rgba
from .image_view import LabeledView, SyncedImageView, ndarray_to_qimage
from .ai_indicator_view import AIIndicatorView
from .redaction_view import RedactionPanel
from .wipe_view import CompareWipeView


_IMAGE_FILTERS = (
    "Images (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif);;All files (*)"
)


def _ndarray_to_pixmap(arr: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(ndarray_to_qimage(arr))


class DropSlot(QFrame):
    """A drop-zone card with Load… / Clear buttons and a tiny preview row."""

    fileChosen = Signal(str)
    cleared = Signal()

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dropzone")
        self.setProperty("active", False)
        self.setAcceptDrops(True)
        self.setMinimumHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._start_dir = ""

        self.title = QLabel(label)
        self.title.setProperty("role", "title")

        self.hint = QLabel("Drop an image here or use Load…")
        self.hint.setProperty("role", "muted")
        self.hint.setWordWrap(True)

        self.path_label = QLabel("")
        self.path_label.setProperty("role", "muted")
        self.path_label.setWordWrap(False)
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        self.load_btn = QPushButton("Load…")
        self.load_btn.clicked.connect(self._open_picker)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setToolTip(f"Remove the loaded {label}")
        self.clear_btn.setEnabled(False)
        self.clear_btn.clicked.connect(self.cleared)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(8)
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.load_btn)
        top.addWidget(self.clear_btn)

        bottom = QVBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(2)
        bottom.addWidget(self.hint)
        bottom.addWidget(self.path_label)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        lay.addLayout(top)
        lay.addLayout(bottom)

    # --- drag/drop ----------------------------------------------------------
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("active", True)
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802, ANN001
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        self.setProperty("active", False)
        self.style().unpolish(self)
        self.style().polish(self)
        urls = event.mimeData().urls()
        if not urls:
            event.ignore()
            return
        local = urls[0].toLocalFile()
        if not local:
            event.ignore()
            return
        event.acceptProposedAction()
        self.fileChosen.emit(local)

    # --- file picker --------------------------------------------------------
    def set_start_dir(self, directory: str) -> None:
        self._start_dir = directory or ""

    def _open_picker(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"Choose {self.title.text()}", self._start_dir, _IMAGE_FILTERS
        )
        if path:
            self.fileChosen.emit(path)

    def set_loaded(self, path: Path | None) -> None:
        if path is None:
            self.path_label.setText("")
            self.clear_btn.setEnabled(False)
        else:
            self.path_label.setText(str(path))
            self.clear_btn.setEnabled(True)


class SummaryCard(QFrame):
    """Compact card showing changed pixels, total, %, threshold."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setProperty("role", "summary")

        self.title = QLabel("Comparison")
        self.title.setProperty("role", "title")

        self.changed = QLabel("Changed: —")
        self.total = QLabel("Total: —")
        self.percent = QLabel("0.0% changed")
        self.percent.setStyleSheet("font-size: 22px; font-weight: 700;")
        self.threshold_label = QLabel("Threshold: 0")
        self.threshold_label.setProperty("role", "muted")

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(2)
        grid.addWidget(self.changed, 0, 0)
        grid.addWidget(self.total, 1, 0)
        grid.addWidget(self.threshold_label, 2, 0)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        right.addStretch(1)
        right.addWidget(self.percent, alignment=Qt.AlignRight)
        right.addStretch(1)

        row = QHBoxLayout()
        row.addLayout(grid, 1)
        row.addLayout(right)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)
        lay.addWidget(self.title)
        lay.addLayout(row)

    def update_result(self, res: CompareResult | None) -> None:
        if res is None:
            self.changed.setText("Changed: —")
            self.total.setText("Total: —")
            self.percent.setText("—")
            self.threshold_label.setText("Threshold: —")
            return
        self.changed.setText(f"Changed: {res.changed_pixels:,}")
        self.total.setText(f"Total: {res.total_pixels:,}")
        self.percent.setText(f"{res.changed_percent:.1f}% changed")
        self.threshold_label.setText(
            f"Threshold: {res.threshold} (tol ±{res.tolerance})"
        )


class StatusBanner(QLabel):
    """Inline status text with role-driven color."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setProperty("role", "muted")
        self.setWordWrap(True)
        self.setMinimumHeight(20)

    def info(self, text: str) -> None:
        self._set("muted", text)

    def ok(self, text: str) -> None:
        self._set("status-ok", text)

    def warn(self, text: str) -> None:
        self._set("status-warn", text)

    def error(self, text: str) -> None:
        self._set("status-error", text)

    def clear_status(self) -> None:
        self._set("muted", "")

    def _set(self, role: str, text: str) -> None:
        self.setProperty("role", role)
        self.setText(text)
        self.style().unpolish(self)
        self.style().polish(self)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Cove Image Lab")
        self.resize(1480, 880)

        self._settings = QSettings()  # uses app/org name set in app.main()
        self._image_a: np.ndarray | None = None
        self._image_b: np.ndarray | None = None
        self._path_a: Path | None = None
        self._path_b: Path | None = None
        self._delta: np.ndarray | None = None
        self._last_result: CompareResult | None = None

        # --- top: two drop slots side by side -----------------------------
        self.slot_a = DropSlot("Image A")
        self.slot_b = DropSlot("Image B")
        self.slot_a.fileChosen.connect(lambda p: self._load_into("a", p))
        self.slot_b.fileChosen.connect(lambda p: self._load_into("b", p))
        self.slot_a.cleared.connect(lambda: self._clear_slot("a"))
        self.slot_b.cleared.connect(lambda: self._clear_slot("b"))

        slots = QHBoxLayout()
        slots.setSpacing(10)
        slots.addWidget(self.slot_a, 1)
        slots.addWidget(self.slot_b, 1)

        # --- middle: synced image views + wipe view + diff view ------------
        self.synced = SyncedImageView()
        self.wipe_view = CompareWipeView()
        self.diff_view = LabeledView("Diff")

        views = QHBoxLayout()
        views.setSpacing(10)
        views.addWidget(self.synced, 2)
        views.addWidget(self.wipe_view, 1)
        views.addWidget(self.diff_view, 1)

        # --- threshold + summary + export ---------------------------------
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setValue(0)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(5)
        self.slider.valueChanged.connect(self._on_threshold_changed)

        slider_label = QLabel("Threshold")
        slider_label.setProperty("role", "title")
        self.slider_value = QLabel("0")
        self.slider_value.setProperty("role", "muted")

        slider_row = QHBoxLayout()
        slider_row.setSpacing(10)
        slider_row.addWidget(slider_label)
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(self.slider_value)

        slider_card = QFrame()
        slider_card.setObjectName("card")
        slider_box = QVBoxLayout(slider_card)
        slider_box.setContentsMargins(12, 10, 12, 12)
        slider_box.setSpacing(6)
        slider_box.addLayout(slider_row)

        threshold_hint = QLabel(
            "Higher threshold ignores small pixel differences. "
            "Changed % counts pixels beyond the threshold."
        )
        threshold_hint.setProperty("role", "muted")
        threshold_hint.setWordWrap(True)
        slider_box.addWidget(threshold_hint)

        self.summary = SummaryCard()
        self.summary.update_result(None)

        self.export_btn = QPushButton("Export diff PNG…")
        self.export_btn.setProperty("role", "primary")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export_clicked)

        self.banner = StatusBanner()
        self.banner.info("Drop or load two images to begin.")

        bottom_left = QVBoxLayout()
        bottom_left.setSpacing(10)
        bottom_left.addWidget(slider_card)
        bottom_left.addWidget(self.summary)

        bottom_right = QVBoxLayout()
        bottom_right.setSpacing(10)
        bottom_right.addStretch(1)
        bottom_right.addWidget(self.export_btn)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addLayout(bottom_left, 3)
        bottom.addLayout(bottom_right, 1)

        # --- compare tab body ---------------------------------------------
        self.compare_help_btn = QPushButton("How to use")
        self.compare_help_btn.setProperty("role", "header")
        self.compare_help_btn.clicked.connect(self._on_compare_help)

        compare_help_row = QHBoxLayout()
        compare_help_row.setContentsMargins(0, 0, 0, 0)
        compare_help_row.setSpacing(0)
        compare_help_row.addStretch(1)
        compare_help_row.addWidget(self.compare_help_btn)

        compare_tab = QWidget()
        compare_lay = QVBoxLayout(compare_tab)
        compare_lay.setContentsMargins(0, 10, 0, 0)
        compare_lay.setSpacing(10)
        compare_lay.addLayout(compare_help_row)
        compare_lay.addLayout(views, 1)
        compare_lay.addWidget(self.banner)
        compare_lay.addLayout(bottom)

        # --- forensics tab body -------------------------------------------
        self.forensics = ForensicsPanel()
        forensics_tab = QWidget()
        forensics_lay = QVBoxLayout(forensics_tab)
        forensics_lay.setContentsMargins(0, 10, 0, 0)
        forensics_lay.setSpacing(0)
        forensics_lay.addWidget(self.forensics)

        # --- redaction tab body -------------------------------------------
        self.redaction = RedactionPanel()
        redaction_tab = QWidget()
        redaction_lay = QVBoxLayout(redaction_tab)
        redaction_lay.setContentsMargins(0, 10, 0, 0)
        redaction_lay.setSpacing(0)
        redaction_lay.addWidget(self.redaction)

        # --- ai indicator tab body ----------------------------------------
        self.ai_indicator = AIIndicatorView()
        ai_indicator_tab = QWidget()
        ai_indicator_lay = QVBoxLayout(ai_indicator_tab)
        ai_indicator_lay.setContentsMargins(0, 10, 0, 0)
        ai_indicator_lay.setSpacing(0)
        ai_indicator_lay.addWidget(self.ai_indicator)

        # --- tabs ---------------------------------------------------------
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(compare_tab, "Compare")
        self.tabs.addTab(forensics_tab, "Forensics")
        self.tabs.addTab(redaction_tab, "Redaction")
        self.tabs.addTab(ai_indicator_tab, "AI Indicator")
        self.tabs.setStyleSheet(_tab_qss())

        # --- root layout --------------------------------------------------
        root = QWidget()
        root_lay = QVBoxLayout(root)
        root_lay.setContentsMargins(14, 14, 14, 12)
        root_lay.setSpacing(12)
        root_lay.addLayout(slots)
        root_lay.addWidget(self.tabs, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar(self))
        self.statusBar().showMessage("Ready")

        self._restore_settings()

    # --- settings ---------------------------------------------------------
    def _restore_settings(self) -> None:
        last_open = self._settings.value("paths/last_open_dir", "", type=str)
        self.slot_a.set_start_dir(last_open)
        self.slot_b.set_start_dir(last_open)

        threshold = self._settings.value("view/threshold", 0, type=int)
        threshold = max(0, min(100, int(threshold)))
        if threshold != self.slider.value():
            self.slider.setValue(threshold)
        else:
            # Force the label to refresh to the persisted value.
            self.slider_value.setText(str(threshold))

    def _remember_open_dir(self, path: Path) -> None:
        directory = str(path.parent)
        self._settings.setValue("paths/last_open_dir", directory)
        self.slot_a.set_start_dir(directory)
        self.slot_b.set_start_dir(directory)

    def closeEvent(self, event) -> None:  # noqa: N802, ANN001
        self._settings.setValue("view/threshold", int(self.slider.value()))
        super().closeEvent(event)

    # --- loading / orchestration ------------------------------------------
    def _load_into(self, slot: str, path_str: str) -> None:
        path = Path(path_str)
        try:
            arr = load_rgba(path)
        except ImageLoadError as e:
            self.banner.error(f"Could not load {path.name}: {e}")
            return

        if slot == "a":
            self._image_a = arr
            self._path_a = path
            self.slot_a.set_loaded(path)
        else:
            self._image_b = arr
            self._path_b = path
            self.slot_b.set_loaded(path)

        self.forensics.set_image(slot, arr, path)
        self.redaction.set_image(slot, arr, path)
        self.ai_indicator.set_image(slot, arr, path)
        self._remember_open_dir(path)
        self._refresh_side_by_side()
        self._recompute()

    def _clear_slot(self, slot: str) -> None:
        if slot == "a":
            if self._image_a is None and self._path_a is None:
                return
            self._image_a = None
            self._path_a = None
            self.slot_a.set_loaded(None)
        elif slot == "b":
            if self._image_b is None and self._path_b is None:
                return
            self._image_b = None
            self._path_b = None
            self.slot_b.set_loaded(None)
        else:
            return

        self.forensics.set_image(slot, None, None)
        self.redaction.set_image(slot, None, None)
        self.ai_indicator.set_image(slot, None, None)
        self._refresh_side_by_side()
        self._recompute()
        self.statusBar().showMessage(f"Cleared Image {slot.upper()}")

    def _refresh_side_by_side(self) -> None:
        left = _ndarray_to_pixmap(self._image_a) if self._image_a is not None else None
        right = _ndarray_to_pixmap(self._image_b) if self._image_b is not None else None
        self.synced.set_images(left, right)
        # Wipe view always gets the latest pair, regardless of dim match.
        self.wipe_view.set_images(left, right)

    def _recompute(self) -> None:
        if self._image_a is None or self._image_b is None:
            self._delta = None
            self._last_result = None
            self.diff_view.set_pixmap(None)
            self.summary.update_result(None)
            self.export_btn.setEnabled(False)
            self.wipe_view.set_note("")
            self.banner.info("Drop or load two images to begin.")
            return
        try:
            res = compare(self._image_a, self._image_b, self.slider.value())
        except DimensionMismatchError:
            a_h, a_w = self._image_a.shape[:2]
            b_h, b_w = self._image_b.shape[:2]
            self._delta = None
            self._last_result = None
            self.diff_view.set_pixmap(None)
            self.summary.update_result(None)
            self.export_btn.setEnabled(False)
            self.wipe_view.set_note(
                "Visual wipe only: B is scaled to A for preview. "
                "Pixel diff requires matching dimensions."
            )
            self.banner.warn(
                f"Image dimensions differ: A is {a_w}×{a_h}, B is {b_w}×{b_h}. "
                "Resize or crop to match before comparing."
            )
            return
        self._delta = res.delta
        self._last_result = res
        self.diff_view.set_pixmap(_ndarray_to_pixmap(res.heatmap))
        self.summary.update_result(res)
        self.export_btn.setEnabled(True)
        self.wipe_view.set_note("")
        self.banner.ok(
            f"Compared at threshold {res.threshold}. {res.changed_percent:.1f}% changed."
        )

    def _on_threshold_changed(self, value: int) -> None:
        self.slider_value.setText(str(value))
        if self._delta is None:
            return
        res = reapply_threshold(self._delta, value)
        self._last_result = res
        self.diff_view.set_pixmap(_ndarray_to_pixmap(res.heatmap))
        self.summary.update_result(res)
        self.banner.ok(
            f"Threshold {res.threshold}. {res.changed_percent:.1f}% changed."
        )

    def _on_export_clicked(self) -> None:
        if self._last_result is None:
            return
        last_save = self._settings.value("paths/last_save_dir", "", type=str)
        default_path = str(Path(last_save) / "diff.png") if last_save else "diff.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Export diff PNG", default_path, "PNG (*.png)"
        )
        if not path:
            return
        if not path.lower().endswith(".png"):
            path = path + ".png"
        try:
            out = export_png(self._last_result.heatmap, path)
        except DiffExportError as e:
            self.banner.error(f"Export failed: {e}")
            self.statusBar().showMessage("Export failed")
            return
        self._settings.setValue("paths/last_save_dir", str(Path(out).parent))
        self.banner.ok(f"Exported {out}")
        self.statusBar().showMessage(f"Saved {out}")

    def _on_compare_help(self) -> None:
        open_compare_help(self)


def _tab_qss() -> str:
    """Cove-themed QSS for the Compare/Forensics tab bar."""
    return f"""
    QTabWidget::pane {{
        border: 1px solid {theme.BORDER};
        border-radius: {theme.RADIUS}px;
        background-color: {theme.BG_BASE};
        top: -1px;
    }}
    QTabBar {{ background: transparent; }}
    QTabBar::tab {{
        background: {theme.BG_SURFACE};
        color: {theme.TEXT_MUTED};
        padding: 8px 18px;
        margin-right: 4px;
        border: 1px solid {theme.BORDER};
        border-bottom: none;
        border-top-left-radius: {theme.RADIUS_SM}px;
        border-top-right-radius: {theme.RADIUS_SM}px;
    }}
    QTabBar::tab:selected {{
        background: {theme.BG_SURFACE_RAISED};
        color: {theme.TEXT_PRIMARY};
        border-color: {theme.ACCENT};
        border-bottom: 1px solid {theme.BG_SURFACE_RAISED};
        font-weight: 600;
    }}
    QTabBar::tab:hover:!selected {{
        color: {theme.ACCENT};
    }}
    """
