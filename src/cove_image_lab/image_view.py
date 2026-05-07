"""SyncedImageView: two QGraphicsView panes with shared zoom/pan."""
from __future__ import annotations

from typing import Iterable

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

import numpy as np


def ndarray_to_qimage(arr: np.ndarray) -> QImage:
    """Convert an H x W x {3,4} uint8 ndarray to a QImage that owns its data."""
    if arr.dtype != np.uint8 or arr.ndim != 3 or arr.shape[2] not in (3, 4):
        raise ValueError(f"Unsupported array for QImage: {arr.shape} {arr.dtype}")
    arr = np.ascontiguousarray(arr)
    h, w, c = arr.shape
    fmt = QImage.Format_RGBA8888 if c == 4 else QImage.Format_RGB888
    qi = QImage(arr.data, w, h, c * w, fmt)
    return qi.copy()  # detach from numpy buffer


class _PanZoomView(QGraphicsView):
    """A QGraphicsView that emits zoom/pan changes for syncing."""

    zoomChanged = Signal(float, QPointF)        # factor, scene-space focal point
    scrollChanged = Signal(int, int)            # h_value, v_value
    transformChanged = Signal()                 # any zoom/fit transform update

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(
            QPainter.Antialiasing | QPainter.SmoothPixmapTransform
        )
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setFrameShape(QFrame.NoFrame)
        self._suppress_emit = False
        self._item: QGraphicsPixmapItem | None = None
        self._zoom = 1.0

        self.horizontalScrollBar().valueChanged.connect(self._on_scroll)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def set_pixmap(self, pix: QPixmap | None) -> None:
        scene = self.scene()
        scene.clear()
        self._item = None
        if pix is None or pix.isNull():
            scene.setSceneRect(QRectF())
            self.resetTransform()
            self._zoom = 1.0
            self.transformChanged.emit()
            return
        self._item = scene.addPixmap(pix)
        scene.setSceneRect(QRectF(pix.rect()))
        self.resetTransform()
        self._zoom = 1.0
        self.fitInView(self._item, Qt.KeepAspectRatio)
        self.transformChanged.emit()

    def fit(self) -> None:
        if self._item is not None:
            self.resetTransform()
            self._zoom = 1.0
            self.fitInView(self._item, Qt.KeepAspectRatio)
            self.transformChanged.emit()

    def actual_size(self) -> None:
        """Reset to native pixel size (zoom = 1.0) and clear pan."""
        if self._item is not None:
            self.resetTransform()
            self._zoom = 1.0
            self.transformChanged.emit()

    def current_zoom_percent(self) -> int:
        """Effective on-screen scale, in percent. 100 = native pixel size."""
        if self._item is None:
            return 0
        return int(round(self.transform().m11() * 100))

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 - Qt name
        if self._item is None:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        focal_scene = self.mapToScene(event.position().toPoint())
        self.scale(factor, factor)
        self._zoom *= factor
        if not self._suppress_emit:
            self.zoomChanged.emit(factor, focal_scene)
        self.transformChanged.emit()
        event.accept()

    def apply_zoom(self, factor: float, focal_scene: QPointF) -> None:
        if self._item is None:
            return
        self._suppress_emit = True
        try:
            old_focal_view = self.mapFromScene(focal_scene)
            self.scale(factor, factor)
            self._zoom *= factor
            new_focal_scene = self.mapToScene(old_focal_view)
            delta = new_focal_scene - focal_scene
            self.translate(delta.x(), delta.y())
        finally:
            self._suppress_emit = False
        self.transformChanged.emit()

    def _on_scroll(self, _value: int) -> None:
        if self._suppress_emit:
            return
        self.scrollChanged.emit(
            self.horizontalScrollBar().value(),
            self.verticalScrollBar().value(),
        )

    def apply_scroll(self, h: int, v: int) -> None:
        self._suppress_emit = True
        try:
            self.horizontalScrollBar().setValue(h)
            self.verticalScrollBar().setValue(v)
        finally:
            self._suppress_emit = False


class LabeledView(QFrame):
    """A QGraphicsView wrapped in a Cove-style card with a title strip.

    When ``with_zoom_toolbar`` is True, a compact Fit / 100% / zoom-percent
    strip sits to the right of the title. Defaults to False so existing
    callers are unchanged.
    """

    def __init__(
        self,
        title: str,
        parent: QWidget | None = None,
        *,
        with_zoom_toolbar: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "title")

        self.view = _PanZoomView(self)

        self.fit_btn: QPushButton | None = None
        self.actual_btn: QPushButton | None = None
        self.zoom_label: QLabel | None = None

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title_row.addWidget(self.title_label)
        title_row.addStretch(1)

        if with_zoom_toolbar:
            self.zoom_label = QLabel("—")
            self.zoom_label.setProperty("role", "muted")
            self.zoom_label.setMinimumWidth(48)
            self.zoom_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            self.fit_btn = QPushButton("Fit")
            self.fit_btn.setProperty("role", "header")
            self.fit_btn.setCursor(Qt.PointingHandCursor)
            self.fit_btn.setToolTip("Fit image to view")
            self.fit_btn.clicked.connect(self.view.fit)

            self.actual_btn = QPushButton("100%")
            self.actual_btn.setProperty("role", "header")
            self.actual_btn.setCursor(Qt.PointingHandCursor)
            self.actual_btn.setToolTip("Show at native pixel size")
            self.actual_btn.clicked.connect(self.view.actual_size)

            title_row.addWidget(self.zoom_label)
            title_row.addWidget(self.fit_btn)
            title_row.addWidget(self.actual_btn)

            self.view.transformChanged.connect(self._update_zoom_readout)
            self.set_toolbar_enabled(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lay.addLayout(title_row)
        lay.addWidget(self.view, 1)

    def set_pixmap(self, pix: QPixmap | None) -> None:
        self.view.set_pixmap(pix)

    def set_toolbar_enabled(self, enabled: bool) -> None:
        """Enable or disable the optional zoom toolbar (no-op if absent)."""
        if self.fit_btn is None:
            return
        self.fit_btn.setEnabled(enabled)
        self.actual_btn.setEnabled(enabled)
        self.zoom_label.setEnabled(enabled)
        if not enabled:
            self.zoom_label.setText("—")
        else:
            self._update_zoom_readout()

    def _update_zoom_readout(self) -> None:
        if self.zoom_label is None:
            return
        if not self.zoom_label.isEnabled():
            return
        pct = self.view.current_zoom_percent()
        self.zoom_label.setText(f"{pct}%" if pct > 0 else "—")


class SyncedImageView(QWidget):
    """Two LabeledView panes whose zoom and pan stay in sync."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.left = LabeledView("Image A", self)
        self.right = LabeledView("Image B", self)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(self.left, 1)
        lay.addWidget(self.right, 1)

        self._wire(self.left.view, self.right.view)
        self._wire(self.right.view, self.left.view)

    def _wire(self, src: _PanZoomView, dst: _PanZoomView) -> None:
        src.zoomChanged.connect(dst.apply_zoom)
        src.scrollChanged.connect(dst.apply_scroll)

    def set_images(self, left: QPixmap | None, right: QPixmap | None) -> None:
        self.left.set_pixmap(left)
        self.right.set_pixmap(right)

    def fit_both(self) -> None:
        self.left.view.fit()
        self.right.view.fit()
