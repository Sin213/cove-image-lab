"""CompareWipeView: before/after wipe slider with optional fullscreen overlay.

Paints A under, B over, with a vertical divider that clips B on the right.
B is drawn into the same target rect as A — its source pixmap is never
resampled or written to disk. The compare_engine math is untouched.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme


def _make_fullscreen_icon(size: int = 14, color: str = theme.TEXT_PRIMARY) -> QIcon:
    """Render a small four-corner-bracket icon as a QIcon."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    p.setPen(pen)
    arm = max(2.0, size * 0.32)
    s = size - 1
    # top-left
    p.drawLine(QPointF(0.5, arm), QPointF(0.5, 0.5))
    p.drawLine(QPointF(0.5, 0.5), QPointF(arm, 0.5))
    # top-right
    p.drawLine(QPointF(s - arm, 0.5), QPointF(s, 0.5))
    p.drawLine(QPointF(s, 0.5), QPointF(s, arm))
    # bottom-left
    p.drawLine(QPointF(0.5, s - arm), QPointF(0.5, s))
    p.drawLine(QPointF(0.5, s), QPointF(arm, s))
    # bottom-right
    p.drawLine(QPointF(s - arm, s), QPointF(s, s))
    p.drawLine(QPointF(s, s), QPointF(s, s - arm))
    p.end()
    return QIcon(pm)


class _WipeStage(QWidget):
    """Drawing surface for the wipe. Owns mouse + keyboard interaction.

    Zoom modes:
      - 'fit':    image rect aspect-fits the widget. Click anywhere = move
                  divider. No panning.
      - 'native': image rect is at A's native pixel size. Click within
                  HANDLE_GRAB px of the divider = move divider; click elsewhere
                  = pan (clamped).
    """

    positionChanged = Signal(float)  # 0..1

    HANDLE_R = 16
    HANDLE_GRAB = 24  # x-distance from divider that counts as 'on the handle'
    NUDGE = 0.04
    NUDGE_FINE = 0.01

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.SizeHorCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumHeight(220)
        self._a: QPixmap | None = None
        self._b: QPixmap | None = None
        self._pos: float = 0.5
        self._zoom_mode: str = "fit"
        self._pan_x: int = 0
        self._pan_y: int = 0
        self._gesture: str | None = None  # 'drag' | 'pan' | None
        self._pan_anchor: QPointF | None = None
        self._left_corner: str = "A"
        self._right_corner: str = "B"
        self._empty_hint: str = "Drop or load both images to compare."

    # --- public API ---------------------------------------------------------
    def set_corner_labels(self, left: str, right: str) -> None:
        self._left_corner = left
        self._right_corner = right
        self.update()

    def set_empty_hint(self, text: str) -> None:
        self._empty_hint = text or ""
        self.update()

    def set_images(self, a: QPixmap | None, b: QPixmap | None) -> None:
        self._a = a if (a is not None and not a.isNull()) else None
        self._b = b if (b is not None and not b.isNull()) else None
        self._pan_x = 0
        self._pan_y = 0
        self.update()

    def position(self) -> float:
        return self._pos

    def set_position(self, p: float) -> None:
        new = max(0.0, min(1.0, float(p)))
        if new != self._pos:
            self._pos = new
            self.positionChanged.emit(new)
            self.update()

    def zoom_mode(self) -> str:
        return self._zoom_mode

    def set_zoom_mode(self, mode: str) -> None:
        if mode not in ("fit", "native"):
            return
        if mode != self._zoom_mode:
            self._zoom_mode = mode
            self._pan_x = 0
            self._pan_y = 0
            self.update()

    # --- internal -----------------------------------------------------------
    def _ref_size(self) -> tuple[int, int] | None:
        ref = self._a or self._b
        if ref is None:
            return None
        rw, rh = ref.width(), ref.height()
        if rw <= 0 or rh <= 0:
            return None
        return rw, rh

    def _image_rect(self) -> QRect:
        """Target rect that A is painted into (and B is forced into).

        Depends on zoom mode and pan offsets.
        """
        sz = self._ref_size()
        if sz is None:
            return QRect()
        rw, rh = sz
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return QRect()
        if self._zoom_mode == "native":
            sw, sh = rw, rh
        else:
            scale = min(w / rw, h / rh)
            sw = max(1, int(rw * scale))
            sh = max(1, int(rh * scale))
        x = (w - sw) // 2 + self._pan_x
        y = (h - sh) // 2 + self._pan_y
        return QRect(x, y, sw, sh)

    def _x_to_pos(self, x: float) -> float:
        rect = self._image_rect()
        if rect.isEmpty() or rect.width() <= 0:
            return self._pos
        rel = (x - rect.left()) / rect.width()
        return max(0.0, min(1.0, rel))

    def _clamp_pan(self) -> None:
        if self._zoom_mode != "native":
            self._pan_x = 0
            self._pan_y = 0
            return
        sz = self._ref_size()
        if sz is None:
            return
        rw, rh = sz
        sw, sh = self.width(), self.height()
        if rw > sw:
            max_x = (rw - sw) // 2 + sw // 2  # allow sliding past center
            self._pan_x = max(-max_x, min(max_x, self._pan_x))
        else:
            self._pan_x = 0
        if rh > sh:
            max_y = (rh - sh) // 2 + sh // 2
            self._pan_y = max(-max_y, min(max_y, self._pan_y))
        else:
            self._pan_y = 0

    # --- painting -----------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        p.fillRect(self.rect(), QColor(theme.BG_INPUT))

        if self._a is None and self._b is None:
            if self._empty_hint:
                self._draw_hint(p, self._empty_hint)
            return

        rect = self._image_rect()
        if rect.isEmpty():
            return
        target = QRectF(rect)

        if self._a is not None:
            p.drawPixmap(target, self._a, QRectF(self._a.rect()))

        div_x = rect.left() + rect.width() * self._pos
        if self._b is not None:
            right_clip = QRectF(div_x, rect.top(), rect.right() - div_x + 1, rect.height())
            if right_clip.width() > 0:
                p.save()
                p.setClipRect(right_clip)
                p.drawPixmap(target, self._b, QRectF(self._b.rect()))
                p.restore()

        if self._a is not None and self._b is not None:
            self._draw_corner_label(
                p, self._left_corner, rect.left() + 10, rect.top() + 10, accent=False
            )
            self._draw_corner_label(
                p, self._right_corner, rect.right() - 10, rect.top() + 10,
                accent=True, align_right=True,
            )

        # Divider extends across the full widget height when in native mode
        # (the user might be panned away from rect vertically); otherwise
        # constrain to the image rect.
        if self._zoom_mode == "native":
            line_top, line_bot = 0, self.height()
        else:
            line_top, line_bot = rect.top(), rect.bottom()
        line_pen = QPen(QColor(theme.ACCENT))
        line_pen.setWidthF(2.0)
        p.setPen(line_pen)
        p.drawLine(QPointF(div_x, line_top), QPointF(div_x, line_bot))
        handle_y = max(line_top + self.HANDLE_R + 4, min(line_bot - self.HANDLE_R - 4, self.height() / 2))
        self._draw_handle(p, div_x, handle_y)

    def _draw_hint(self, p: QPainter, text: str) -> None:
        p.setPen(QColor(theme.TEXT_MUTED))
        p.drawText(self.rect(), Qt.AlignCenter, text)

    def _draw_corner_label(
        self,
        p: QPainter,
        text: str,
        x: float,
        y: float,
        *,
        accent: bool,
        align_right: bool = False,
    ) -> None:
        pad_x, pad_y = 8, 4
        font = p.font()
        font.setBold(True)
        p.setFont(font)
        fm = p.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        rect_w = tw + pad_x * 2
        rect_h = th + pad_y * 2
        if align_right:
            box = QRectF(x - rect_w, y, rect_w, rect_h)
        else:
            box = QRectF(x, y, rect_w, rect_h)
        p.setBrush(QColor(0, 0, 0, 140))
        border = QColor(theme.ACCENT) if accent else QColor(theme.BORDER_STRONG)
        p.setPen(QPen(border, 1))
        p.drawRoundedRect(box, 4, 4)
        p.setPen(QColor(theme.ACCENT) if accent else QColor(theme.TEXT_PRIMARY))
        p.drawText(box, Qt.AlignCenter, text)

    def _draw_handle(self, p: QPainter, cx: float, cy: float) -> None:
        r = self.HANDLE_R
        p.setBrush(QBrush(QColor("#0b1413")))
        p.setPen(QPen(QColor(theme.ACCENT), 2))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setPen(QPen(QColor(theme.ACCENT), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        s = 5.0
        left = QPolygonF(
            [
                QPointF(cx - s + 1, cy - s),
                QPointF(cx - s - 2, cy),
                QPointF(cx - s + 1, cy + s),
            ]
        )
        right = QPolygonF(
            [
                QPointF(cx + s - 1, cy - s),
                QPointF(cx + s + 2, cy),
                QPointF(cx + s - 1, cy + s),
            ]
        )
        p.drawPolyline(left)
        p.drawPolyline(right)

    # --- input --------------------------------------------------------------
    def _is_near_handle(self, x: float) -> bool:
        rect = self._image_rect()
        if rect.isEmpty():
            return False
        div_x = rect.left() + rect.width() * self._pos
        return abs(x - div_x) <= self.HANDLE_GRAB

    def mousePressEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        if self._zoom_mode == "fit" or self._is_near_handle(e.position().x()):
            self._gesture = "drag"
            self.set_position(self._x_to_pos(e.position().x()))
        else:
            self._gesture = "pan"
            self._pan_anchor = QPointF(e.position())
            self.setCursor(Qt.ClosedHandCursor)
        self.setFocus(Qt.MouseFocusReason)

    def mouseMoveEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if self._gesture == "drag":
            self.set_position(self._x_to_pos(e.position().x()))
        elif self._gesture == "pan" and self._pan_anchor is not None:
            delta = e.position() - self._pan_anchor
            self._pan_anchor = QPointF(e.position())
            self._pan_x += int(delta.x())
            self._pan_y += int(delta.y())
            self._clamp_pan()
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        self._gesture = None
        self._pan_anchor = None
        self.setCursor(Qt.SizeHorCursor)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        step = self.NUDGE_FINE if e.modifiers() & Qt.ShiftModifier else self.NUDGE
        if e.key() == Qt.Key_Left:
            self.set_position(self._pos - step)
            e.accept()
        elif e.key() == Qt.Key_Right:
            self.set_position(self._pos + step)
            e.accept()
        elif e.key() == Qt.Key_Home:
            self.set_position(0.0)
            e.accept()
        elif e.key() == Qt.Key_End:
            self.set_position(1.0)
            e.accept()
        else:
            super().keyPressEvent(e)


class CompareWipeView(QFrame):
    """Cove-style card holding the wipe stage, a title, and an inline note.

    Reusable: pass ``title`` plus ``left_label`` / ``right_label`` to relabel
    the title strip and the in-image corner badges. Defaults match the
    original Compare-tab look (``"Compare"`` / ``"A"`` / ``"B"``).
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str = "Compare",
        left_label: str = "A",
        right_label: str = "B",
        empty_hint: str = "Drop or load both images to compare.",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._a: QPixmap | None = None
        self._b: QPixmap | None = None
        self._note_text: str = ""
        self._title_text: str = title
        self._left_label: str = left_label
        self._right_label: str = right_label
        self._empty_hint: str = empty_hint

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "title")

        self.percent_label = QLabel("50%")
        self.percent_label.setProperty("role", "muted")

        self.fullscreen_btn = QPushButton()
        self.fullscreen_btn.setIcon(_make_fullscreen_icon(14, theme.TEXT_PRIMARY))
        self.fullscreen_btn.setToolTip("Fullscreen compare (F11 / Esc to exit)")
        self.fullscreen_btn.setProperty("role", "icon")
        self.fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self.fullscreen_btn.setEnabled(False)
        self.fullscreen_btn.clicked.connect(self._open_fullscreen)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)
        title_row.addWidget(self.percent_label)
        title_row.addWidget(self.fullscreen_btn)

        self.stage = _WipeStage(self)
        self.stage.set_corner_labels(left_label, right_label)
        self.stage.set_empty_hint(empty_hint)
        self.stage.positionChanged.connect(self._on_position_changed)

        self.note_label = QLabel("")
        self.note_label.setProperty("role", "muted")
        self.note_label.setWordWrap(True)
        self.note_label.setVisible(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lay.addLayout(title_row)
        lay.addWidget(self.stage, 1)
        lay.addWidget(self.note_label)

    def set_images(self, a: QPixmap | None, b: QPixmap | None) -> None:
        self._a = a
        self._b = b
        self.stage.set_images(a, b)
        self.fullscreen_btn.setEnabled(a is not None and b is not None)

    def set_note(self, text: str) -> None:
        self._note_text = text or ""
        if text:
            self.note_label.setText(text)
            self.note_label.setVisible(True)
        else:
            self.note_label.clear()
            self.note_label.setVisible(False)

    def _on_position_changed(self, pos: float) -> None:
        self.percent_label.setText(f"{int(round(pos * 100))}%")

    def _open_fullscreen(self) -> None:
        if self._a is None or self._b is None:
            return
        dlg = WipeFullscreenDialog(
            a=self._a,
            b=self._b,
            position=self.stage.position(),
            note_text=self._note_text,
            title=self._title_text,
            left_label=self._left_label,
            right_label=self._right_label,
            parent=self.window(),
        )
        # Modal exec; the dialog enters fullscreen during its own show.
        dlg.exec()
        # Sync position back to the panel.
        self.stage.set_position(dlg.stage.position())


class WipeFullscreenDialog(QDialog):
    """Modal fullscreen wipe view with header (title, %, Fit, 100%, Exit)."""

    def __init__(
        self,
        *,
        a: QPixmap,
        b: QPixmap,
        position: float,
        note_text: str = "",
        title: str = "Compare",
        left_label: str = "A",
        right_label: str = "B",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Cove Image Lab — Wipe")
        # The QDialog inherits the global app stylesheet, so card/button roles
        # match the rest of the app automatically.

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "title")

        self.percent_label = QLabel(f"{int(round(position * 100))}%")
        self.percent_label.setProperty("role", "muted")

        self.fit_btn = QPushButton("Fit")
        self.fit_btn.setProperty("role", "header")
        self.fit_btn.setCursor(Qt.PointingHandCursor)
        self.fit_btn.setCheckable(True)
        self.fit_btn.setChecked(True)

        self.native_btn = QPushButton("100%")
        self.native_btn.setProperty("role", "header")
        self.native_btn.setCursor(Qt.PointingHandCursor)
        self.native_btn.setCheckable(True)

        self.exit_btn = QPushButton("Exit")
        self.exit_btn.setProperty("role", "header")
        self.exit_btn.setCursor(Qt.PointingHandCursor)
        self.exit_btn.setShortcut("Esc")

        header = QHBoxLayout()
        header.setContentsMargins(16, 10, 16, 10)
        header.setSpacing(10)
        header.addWidget(self.title_label)
        header.addSpacing(12)
        header.addWidget(self.percent_label)
        header.addStretch(1)
        header.addWidget(self.fit_btn)
        header.addWidget(self.native_btn)
        header.addSpacing(8)
        header.addWidget(self.exit_btn)

        header_card = QFrame()
        header_card.setObjectName("card")
        header_card.setLayout(header)

        self.stage = _WipeStage(self)
        self.stage.set_corner_labels(left_label, right_label)
        self.stage.set_images(a, b)
        self.stage.set_position(position)
        self.stage.positionChanged.connect(
            lambda p: self.percent_label.setText(f"{int(round(p * 100))}%")
        )

        self.note_label = QLabel(note_text)
        self.note_label.setProperty("role", "muted")
        self.note_label.setWordWrap(True)
        self.note_label.setVisible(bool(note_text))

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        root.addWidget(header_card)
        root.addWidget(self.stage, 1)
        root.addWidget(self.note_label)

        self.fit_btn.clicked.connect(lambda: self._set_zoom("fit"))
        self.native_btn.clicked.connect(lambda: self._set_zoom("native"))
        self.exit_btn.clicked.connect(self.accept)

        # Defer fullscreen until after first show so geometry is initialized.
        self._went_fullscreen = False

    # --- behavior -----------------------------------------------------------
    def _set_zoom(self, mode: str) -> None:
        self.stage.set_zoom_mode(mode)
        self.fit_btn.setChecked(mode == "fit")
        self.native_btn.setChecked(mode == "native")
        self.stage.setFocus(Qt.OtherFocusReason)

    def showEvent(self, event) -> None:  # noqa: N802, ANN001
        super().showEvent(event)
        if not self._went_fullscreen:
            self._went_fullscreen = True
            QTimer.singleShot(0, self.showFullScreen)

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.key() == Qt.Key_Escape:
            self.accept()
            e.accept()
            return
        if e.key() == Qt.Key_F11:
            if self.isFullScreen():
                self.showNormal()
                # Re-maximize so it still fills the screen reasonably.
                self.showMaximized()
            else:
                self.showFullScreen()
            e.accept()
            return
        super().keyPressEvent(e)
