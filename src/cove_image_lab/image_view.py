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
            return
        self._item = scene.addPixmap(pix)
        scene.setSceneRect(QRectF(pix.rect()))
        self.resetTransform()
        self._zoom = 1.0
        self.fitInView(self._item, Qt.KeepAspectRatio)

    def fit(self) -> None:
        if self._item is not None:
            self.resetTransform()
            self._zoom = 1.0
            self.fitInView(self._item, Qt.KeepAspectRatio)

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
    """A QGraphicsView wrapped in a Cove-style card with a title strip."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "title")

        self.view = _PanZoomView(self)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 10)
        lay.setSpacing(6)
        lay.addWidget(self.title_label)
        lay.addWidget(self.view, 1)

    def set_pixmap(self, pix: QPixmap | None) -> None:
        self.view.set_pixmap(pix)


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
