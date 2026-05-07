"""Manual redaction tab: draw opaque black rectangles, export a redacted PNG.

Privacy contract:
    * Original arrays loaded into ``set_image`` are never mutated.
    * Redaction is destructive in the EXPORTED COPY only — covered pixels
      become solid black (RGB 0/0/0; alpha forced to 255 in RGBA so the
      black square stays opaque). No blur, no smoothing.
    * Nothing is auto-saved. Rectangles live in memory for the session
      and disappear when the panel is destroyed.

Drawing surface uses fit-to-widget rendering and stores rectangles in
image-pixel coordinates so they stay precise across window resizes.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image as PILImage
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .image_view import ndarray_to_qimage


REDACTION_HINT = (
    "Click and drag on the image to draw an opaque black redaction rectangle. "
    "Original images are not modified."
)


def _ndarray_to_pixmap(arr: np.ndarray) -> QPixmap:
    return QPixmap.fromImage(ndarray_to_qimage(arr))


def _safe_resolve(p: Path | None) -> Path | None:
    """Resolve ``p`` to a canonical filesystem path with a graceful fallback.

    ``Path.resolve(strict=False)`` is the preferred form because it works
    even if the file does not yet exist (the export target). On platforms
    or filesystems where resolve raises (rare, but documented for some
    network shares) we fall back to ``absolute`` and then to the path
    as-given so the comparison still runs without crashing.
    """
    if p is None:
        return None
    try:
        return p.resolve(strict=False)
    except OSError:
        try:
            return p.absolute()
        except OSError:
            return p


def render_redacted(
    image: np.ndarray, rects: list[tuple[int, int, int, int]]
) -> np.ndarray:
    """Return a COPY of ``image`` with each ``(x, y, w, h)`` rectangle
    filled solid black.

    Coordinates are in image pixels. Rectangles are clamped to the image
    bounds; rectangles with non-positive width or height are ignored.
    The input array is never modified.

    The output preserves shape and dtype. For RGBA input the alpha
    channel inside each rectangle is forced to 255 so the redaction
    stays opaque.
    """
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[2] not in (3, 4):
        raise ValueError(
            f"Unsupported array shape/dtype for redaction: "
            f"shape={image.shape} dtype={image.dtype}"
        )
    out = image.copy()
    h, w = out.shape[:2]
    for rect in rects:
        if len(rect) != 4:
            raise ValueError(f"Rect must be a 4-tuple, got {rect!r}")
        x, y, rw, rh = rect
        if rw <= 0 or rh <= 0:
            continue
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(w, int(x) + int(rw))
        y1 = min(h, int(y) + int(rh))
        if x1 <= x0 or y1 <= y0:
            continue
        out[y0:y1, x0:x1, :3] = 0
        if out.shape[2] == 4:
            out[y0:y1, x0:x1, 3] = 255
    return out


class _ToggleRow(QWidget):
    """Horizontal mutually-exclusive toggle buttons.

    Mirrors the helper in ``forensic_view`` but stays local so the
    Redaction module does not depend on Forensics internals.
    """

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


class _RedactionStage(QWidget):
    """Drawing surface — owns the canonical list of rects while editing.

    Rectangles are stored in image-pixel coordinates as ``(x, y, w, h)``
    so they survive widget resizes and map exactly into the exported PNG.
    """

    rectsChanged = Signal()

    MIN_DIM_IMG_PX = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(260)
        self._pixmap: QPixmap | None = None
        self._image_size: tuple[int, int] | None = None  # (w, h) image pixels
        self._rects: list[tuple[int, int, int, int]] = []
        self._drawing = False
        self._draw_start: QPoint | None = None
        self._draw_current: QPoint | None = None

    # --- public --------------------------------------------------------
    def set_pixmap(self, pix: QPixmap | None) -> None:
        if pix is None or pix.isNull():
            self._pixmap = None
            self._image_size = None
            self.setCursor(Qt.ArrowCursor)
        else:
            self._pixmap = pix
            self._image_size = (pix.width(), pix.height())
            self.setCursor(Qt.CrossCursor)
        self.update()

    def set_rects(self, rects: list[tuple[int, int, int, int]]) -> None:
        # Programmatic load — no signal so callers can install rects
        # without triggering a save loop.
        self._rects = [tuple(r) for r in rects]  # defensive copy
        self.update()

    def rects(self) -> list[tuple[int, int, int, int]]:
        return list(self._rects)

    def has_rects(self) -> bool:
        return bool(self._rects)

    def undo_last(self) -> bool:
        if not self._rects:
            return False
        self._rects.pop()
        self.rectsChanged.emit()
        self.update()
        return True

    def clear_rects(self) -> None:
        if not self._rects:
            return
        self._rects.clear()
        self.rectsChanged.emit()
        self.update()

    # --- coords --------------------------------------------------------
    def _image_rect(self) -> QRect:
        if self._image_size is None:
            return QRect()
        iw, ih = self._image_size
        ww, wh = self.width(), self.height()
        if ww <= 0 or wh <= 0 or iw <= 0 or ih <= 0:
            return QRect()
        scale = min(ww / iw, wh / ih)
        sw = max(1, int(iw * scale))
        sh = max(1, int(ih * scale))
        x = (ww - sw) // 2
        y = (wh - sh) // 2
        return QRect(x, y, sw, sh)

    def _widget_to_image(self, p: QPoint) -> tuple[int, int] | None:
        rect = self._image_rect()
        if rect.isEmpty() or self._image_size is None:
            return None
        iw, ih = self._image_size
        # Qt's QRect.right() / .bottom() are INCLUSIVE: target.right() is the
        # rightmost VISIBLE pixel column, i.e. left + width - 1. The renderer,
        # by contrast, uses HALF-OPEN slicing (out[y0:y1, x0:x1]), so to redact
        # the final image column the rect must end at iw (exclusive). We bridge
        # the two models by mapping the inclusive widget edge to the exclusive
        # image end: a drag landing on target.right() / target.bottom() must
        # produce ix == iw / iy == ih, not iw - 1 / ih - 1.
        span_w = rect.width() - 1
        span_h = rect.height() - 1
        rx = (p.x() - rect.left()) / span_w if span_w > 0 else 0.0
        ry = (p.y() - rect.top()) / span_h if span_h > 0 else 0.0
        ix = int(round(max(0.0, min(1.0, rx)) * iw))
        iy = int(round(max(0.0, min(1.0, ry)) * ih))
        return ix, iy

    def _image_to_widget_rect(self, x: int, y: int, w: int, h: int) -> QRect:
        target = self._image_rect()
        if target.isEmpty() or self._image_size is None:
            return QRect()
        iw, ih = self._image_size
        sx = target.width() / iw
        sy = target.height() / ih
        return QRect(
            target.left() + int(round(x * sx)),
            target.top() + int(round(y * sy)),
            max(1, int(round(w * sx))),
            max(1, int(round(h * sy))),
        )

    # --- painting ------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG_INPUT))
        if self._pixmap is None:
            p.setPen(QColor(theme.TEXT_MUTED))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Select a source image to begin redacting.")
            return
        target = self._image_rect()
        if target.isEmpty():
            return
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        p.drawPixmap(QRectF(target), self._pixmap, QRectF(self._pixmap.rect()))

        # Committed redactions: solid opaque black overlays.
        p.setBrush(QColor(0, 0, 0))
        p.setPen(Qt.NoPen)
        for x, y, w, h in self._rects:
            p.drawRect(self._image_to_widget_rect(x, y, w, h))

        # In-progress rectangle: dashed accent outline.
        if (
            self._drawing
            and self._draw_start is not None
            and self._draw_current is not None
        ):
            pen = QPen(QColor(theme.ACCENT))
            pen.setStyle(Qt.DashLine)
            pen.setWidth(2)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            r = QRect(self._draw_start, self._draw_current).normalized()
            p.drawRect(r)

    # --- input ---------------------------------------------------------
    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton or self._pixmap is None:
            return
        pt = e.position().toPoint()
        if not self._image_rect().contains(pt):
            return
        self._drawing = True
        self._draw_start = pt
        self._draw_current = pt
        self.update()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if not self._drawing:
            return
        pt = e.position().toPoint()
        # Clamp to image rect so the preview rectangle stays inside.
        target = self._image_rect()
        x = max(target.left(), min(target.right(), pt.x()))
        y = max(target.top(), min(target.bottom(), pt.y()))
        self._draw_current = QPoint(x, y)
        self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton or not self._drawing:
            return
        self._drawing = False
        a, b = self._draw_start, self._draw_current
        self._draw_start = None
        self._draw_current = None
        if a is None or b is None:
            self.update()
            return
        ai = self._widget_to_image(a)
        bi = self._widget_to_image(b)
        if ai is None or bi is None:
            self.update()
            return
        ax, ay = ai
        bx, by = bi
        x = min(ax, bx)
        y = min(ay, by)
        w = abs(bx - ax)
        h = abs(by - ay)
        if w >= self.MIN_DIM_IMG_PX and h >= self.MIN_DIM_IMG_PX:
            self._rects.append((x, y, w, h))
            self.rectsChanged.emit()
        self.update()


class RedactionPanel(QWidget):
    """Manual redaction workflow as a tab content widget.

    State is per-source: A and B keep their own list of rectangles for
    the lifetime of the session. Clearing a source via ``set_image(slot,
    None, None)`` also clears that source's rectangles. Nothing is
    written to disk except via the explicit Export Redacted PNG action.
    """

    SOURCE_A = "a"
    SOURCE_B = "b"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._image_a: np.ndarray | None = None
        self._image_b: np.ndarray | None = None
        self._path_a: Path | None = None
        self._path_b: Path | None = None
        self._rects_a: list[tuple[int, int, int, int]] = []
        self._rects_b: list[tuple[int, int, int, int]] = []
        self._source = self.SOURCE_A
        self._last_save_dir = ""

        # --- header card ----------------------------------------------
        header = QFrame()
        header.setObjectName("card")
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(12, 10, 12, 10)
        hlay.setSpacing(8)

        title = QLabel("Privacy Redaction")
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

        hint = QLabel(REDACTION_HINT)
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)

        source_label = QLabel("Source")
        source_label.setProperty("role", "muted")

        self.source_toggle = _ToggleRow(
            [(self.SOURCE_A, "Image A"), (self.SOURCE_B, "Image B")]
        )
        self.source_toggle.set_current(self.SOURCE_A)
        self.source_toggle.selected.connect(self._on_source_changed)

        self.undo_btn = QPushButton("Undo Redaction")
        self.undo_btn.setProperty("role", "header")
        self.undo_btn.setToolTip("Remove the last drawn rectangle.")
        self.undo_btn.clicked.connect(self._on_undo)
        self.undo_btn.setEnabled(False)

        self.clear_btn = QPushButton("Clear Redactions")
        self.clear_btn.setProperty("role", "header")
        self.clear_btn.setToolTip("Remove every redaction rectangle on this source.")
        self.clear_btn.clicked.connect(self._on_clear)
        self.clear_btn.setEnabled(False)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)
        actions_row.addWidget(source_label)
        actions_row.addWidget(self.source_toggle, 1)
        actions_row.addWidget(self.undo_btn)
        actions_row.addWidget(self.clear_btn)

        hlay.addLayout(title_row)
        hlay.addWidget(hint)
        hlay.addLayout(actions_row)

        # --- stage card -----------------------------------------------
        stage_card = QFrame()
        stage_card.setObjectName("card")
        sclay = QVBoxLayout(stage_card)
        sclay.setContentsMargins(10, 8, 10, 10)
        sclay.setSpacing(6)

        stage_title = QLabel("Redaction preview")
        stage_title.setProperty("role", "title")

        self.export_btn = QPushButton("Export Redacted PNG…")
        self.export_btn.setProperty("role", "primary")
        self.export_btn.setToolTip(
            "Save a new PNG copy with the drawn rectangles burned in. "
            "Originals are never modified."
        )
        self.export_btn.clicked.connect(self._on_export)
        self.export_btn.setEnabled(False)

        stage_title_row = QHBoxLayout()
        stage_title_row.setContentsMargins(0, 0, 0, 0)
        stage_title_row.setSpacing(8)
        stage_title_row.addWidget(stage_title)
        stage_title_row.addStretch(1)
        stage_title_row.addWidget(self.export_btn)

        self.stage = _RedactionStage(self)
        self.stage.rectsChanged.connect(self._on_stage_rects_changed)

        sclay.addLayout(stage_title_row)
        sclay.addWidget(self.stage, 1)

        # --- status ---------------------------------------------------
        self.status = QLabel("")
        self.status.setProperty("role", "muted")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(20)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(header)
        root.addWidget(stage_card, 1)
        root.addWidget(self.status)

        self._refresh()

    # --- public wiring -----------------------------------------------
    def set_image(self, slot: str, arr: np.ndarray | None, path: Path | None) -> None:
        """Update one source slot. ``arr=None`` clears that slot AND
        wipes its associated redaction rectangles (no use keeping rects
        that point to missing pixels).
        """
        if slot == self.SOURCE_A:
            self._image_a = arr
            self._path_a = path
            if arr is None:
                self._rects_a = []
        elif slot == self.SOURCE_B:
            self._image_b = arr
            self._path_b = path
            if arr is None:
                self._rects_b = []
        else:
            return
        if slot == self._source:
            self._refresh()
        else:
            self._refresh_action_state()

    # --- internal -----------------------------------------------------
    def _on_help(self) -> None:
        from .help_dialog import open_redaction_help

        open_redaction_help(self)

    def _current_array(self) -> np.ndarray | None:
        return self._image_a if self._source == self.SOURCE_A else self._image_b

    def _current_rects_ref(self) -> list[tuple[int, int, int, int]]:
        return self._rects_a if self._source == self.SOURCE_A else self._rects_b

    def _set_current_rects(self, rects: list[tuple[int, int, int, int]]) -> None:
        if self._source == self.SOURCE_A:
            self._rects_a = list(rects)
        else:
            self._rects_b = list(rects)

    def _on_source_changed(self, key: str) -> None:
        if key not in (self.SOURCE_A, self.SOURCE_B):
            return
        if key == self._source:
            return
        # Stage owns the canonical list while editing; sync any pending
        # state back to the outgoing slot before swapping.
        self._set_current_rects(self.stage.rects())
        self._source = key
        self._refresh()

    def _on_stage_rects_changed(self) -> None:
        self._set_current_rects(self.stage.rects())
        self._refresh_action_state()

    def _on_undo(self) -> None:
        self.stage.undo_last()

    def _on_clear(self) -> None:
        self.stage.clear_rects()

    def _refresh(self) -> None:
        arr = self._current_array()
        if arr is None:
            self.stage.set_pixmap(None)
            self.stage.set_rects([])
        else:
            self.stage.set_pixmap(_ndarray_to_pixmap(arr))
            self.stage.set_rects(self._current_rects_ref())
        self._refresh_action_state()

    def _refresh_action_state(self) -> None:
        arr = self._current_array()
        rect_count = len(self.stage.rects()) if arr is not None else 0
        self.undo_btn.setEnabled(rect_count > 0)
        self.clear_btn.setEnabled(rect_count > 0)
        self.export_btn.setEnabled(arr is not None)
        if arr is None:
            slot_label = self._source.upper()
            self.status.setText(
                f"Load Image {slot_label} on the Compare tab to begin redacting."
            )
            return
        plural = "" if rect_count == 1 else "s"
        self.status.setText(
            f"{rect_count} redaction rectangle{plural} on Image "
            f"{self._source.upper()}. Original is not modified."
        )

    def _default_export_name(self) -> str:
        return f"cove_redacted_{self._source}.png"

    def _on_export(self) -> None:
        arr = self._current_array()
        if arr is None:
            self.status.setText("Load an image before exporting a redacted copy.")
            return
        rects = self.stage.rects()
        default_name = self._default_export_name()
        default_path = (
            str(Path(self._last_save_dir) / default_name)
            if self._last_save_dir
            else default_name
        )
        chosen, _ = QFileDialog.getSaveFileName(
            self, "Export redacted PNG", default_path, "PNG (*.png)"
        )
        if not chosen:
            return
        if not chosen.lower().endswith(".png"):
            chosen = chosen + ".png"
        final_path = Path(chosen)

        # Privacy guard: never overwrite either loaded source file.
        # Compare AFTER the .png suffix is appended — otherwise a user could
        # bypass the check by typing the source path without the extension.
        # We check both slots, not only the active source, so that exporting
        # source A's redaction never overwrites source B and vice versa.
        #
        # Two-tier match:
        #   1. ``Path.samefile`` — inode-level comparison that catches hard
        #      links, bind mounts, and case-insensitive filesystem aliases.
        #      Only valid if the export path already exists; if not, samefile
        #      raises ``FileNotFoundError`` and we fall through.
        #   2. Resolved-path equality — covers the (typical) case where the
        #      target does not exist yet but the user typed the source path
        #      itself or a symlink to it. ``_safe_resolve`` follows symlinks.
        for slot_label, source_path in (
            ("A", self._path_a),
            ("B", self._path_b),
        ):
            if source_path is None:
                continue
            is_match = False
            if final_path.exists():
                try:
                    is_match = final_path.samefile(source_path)
                except (OSError, ValueError):
                    is_match = False
            if not is_match:
                resolved_target = _safe_resolve(final_path)
                resolved_source = _safe_resolve(source_path)
                if (
                    resolved_target is not None
                    and resolved_source is not None
                    and resolved_target == resolved_source
                ):
                    is_match = True
            if is_match:
                self.status.setText(
                    f"That path is the loaded Image {slot_label} file. "
                    "Choose a different filename to keep the original intact."
                )
                return

        try:
            redacted = render_redacted(arr, rects)
            # Save without metadata, fully local Pillow write.
            PILImage.fromarray(redacted).save(str(final_path), format="PNG")
        except (OSError, ValueError) as e:
            self.status.setText(f"Could not save redacted PNG: {e}")
            return
        self._last_save_dir = str(final_path.parent)
        self.status.setText(f"Exported {final_path}")
