"""Pure NumPy image comparison. No Qt imports."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# Above this many pixels, _max_channel_delta processes the image in row
# bands so the int16 intermediate doesn't allocate the full image at once.
CHUNKED_PIXEL_THRESHOLD = 8 * 1024 * 1024  # 8 MP
CHUNK_ROWS = 512


class DimensionMismatchError(ValueError):
    """Raised when two images have different shapes."""


@dataclass(frozen=True)
class CompareResult:
    mask: np.ndarray            # bool H x W, True where changed
    heatmap: np.ndarray         # uint8 H x W x 3, visualization of delta
    delta: np.ndarray           # uint8 H x W, per-pixel max-channel |a-b|
    changed_pixels: int
    total_pixels: int
    changed_percent: float
    threshold: int
    tolerance: int              # absolute per-channel tolerance in 0..255


def _max_channel_delta(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Per-pixel max across channels of |a-b|. Returns uint8 H x W.

    Uses a row-banded path on images above CHUNKED_PIXEL_THRESHOLD so the
    int16 intermediate doesn't allocate the full image at once. Output is
    identical to the single-shot path.
    """
    if a.shape != b.shape:
        raise DimensionMismatchError(f"Shape mismatch: {a.shape} vs {b.shape}")
    if a.dtype != np.uint8 or b.dtype != np.uint8:
        raise ValueError("Inputs must be uint8 RGBA arrays.")
    h, w = a.shape[:2]
    if h * w > CHUNKED_PIXEL_THRESHOLD:
        out = np.empty((h, w), dtype=np.uint8)
        for y in range(0, h, CHUNK_ROWS):
            y2 = min(h, y + CHUNK_ROWS)
            band = np.abs(
                a[y:y2].astype(np.int16) - b[y:y2].astype(np.int16)
            ).astype(np.uint8)
            out[y:y2] = band.max(axis=2)
        return out
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16)).astype(np.uint8)
    return diff.max(axis=2)


def _heatmap_from_delta(delta: np.ndarray, *, tint_red: bool = True) -> np.ndarray:
    """Build an H x W x 3 uint8 heatmap from a per-pixel delta map."""
    if delta.dtype != np.uint8 or delta.ndim != 2:
        raise ValueError("delta must be uint8 H x W.")
    if tint_red:
        h, w = delta.shape
        out = np.zeros((h, w, 3), dtype=np.uint8)
        out[..., 0] = delta            # red carries magnitude
        out[..., 1] = delta // 6       # faint warm tint, keeps unchanged regions black
        out[..., 2] = delta // 6
        return out
    return np.repeat(delta[..., None], 3, axis=2)


def threshold_to_tolerance(threshold: int) -> int:
    """Map slider value 0..100 to absolute per-channel tolerance 0..255."""
    if not 0 <= threshold <= 100:
        raise ValueError("threshold must be in [0, 100].")
    return int(round(threshold * 255 / 100))


def compare(
    a: np.ndarray,
    b: np.ndarray,
    threshold: int,
    *,
    tint_red: bool = True,
) -> CompareResult:
    """Compare two RGBA uint8 images at a given threshold (0..100).

    A pixel is 'changed' iff its max-channel absolute delta is strictly greater
    than the tolerance derived from the threshold.
    """
    delta = _max_channel_delta(a, b)
    tol = threshold_to_tolerance(threshold)
    mask = delta > tol
    changed = int(mask.sum())
    total = int(mask.size)
    pct = (changed / total * 100.0) if total else 0.0
    heatmap = _heatmap_from_delta(delta, tint_red=tint_red)
    # Zero out heatmap where the threshold says 'unchanged' so the user sees
    # what survives the slider.
    if tol > 0:
        heatmap = heatmap * mask[..., None].astype(np.uint8)
    return CompareResult(
        mask=mask,
        heatmap=heatmap,
        delta=delta,
        changed_pixels=changed,
        total_pixels=total,
        changed_percent=pct,
        threshold=threshold,
        tolerance=tol,
    )


def reapply_threshold(
    delta: np.ndarray,
    threshold: int,
    *,
    tint_red: bool = True,
) -> CompareResult:
    """Cheap path: reuse a precomputed delta and only rerun the threshold mask.

    Used by the UI when the user moves the slider, so we don't recompute the
    full subtraction on every tick.
    """
    if delta.dtype != np.uint8 or delta.ndim != 2:
        raise ValueError("delta must be uint8 H x W.")
    tol = threshold_to_tolerance(threshold)
    mask = delta > tol
    changed = int(mask.sum())
    total = int(mask.size)
    pct = (changed / total * 100.0) if total else 0.0
    heatmap = _heatmap_from_delta(delta, tint_red=tint_red)
    if tol > 0:
        heatmap = heatmap * mask[..., None].astype(np.uint8)
    return CompareResult(
        mask=mask,
        heatmap=heatmap,
        delta=delta,
        changed_pixels=changed,
        total_pixels=total,
        changed_percent=pct,
        threshold=threshold,
        tolerance=tol,
    )
