"""Pure forensic image transforms.

Error Level Analysis (ELA) and a simple high-pass noise map. Both functions
take a uint8 H x W x {3,4} ndarray and return a uint8 H x W x 3 RGB ndarray
suitable for display or PNG export.

No Qt imports. No network. No AI. Forensic outputs are visual indicators
only and never imply that an image is fake, real, or manipulated.
"""
from __future__ import annotations

import io

import numpy as np
from PIL import Image


class ForensicError(ValueError):
    """Invalid input or runtime failure inside a forensic transform."""


def _to_rgb_uint8(img: np.ndarray) -> np.ndarray:
    if not isinstance(img, np.ndarray):
        raise ForensicError(f"expected ndarray, got {type(img).__name__}")
    if img.dtype != np.uint8:
        raise ForensicError(f"expected uint8, got {img.dtype}")
    if img.ndim != 3 or img.shape[2] not in (3, 4):
        raise ForensicError(
            f"expected H x W x 3 or 4 array, got shape {img.shape}"
        )
    if img.shape[2] == 4:
        return np.ascontiguousarray(img[..., :3])
    return np.ascontiguousarray(img)


def _apply_brightness(arr: np.ndarray, brightness: float) -> np.ndarray:
    if brightness == 0.0:
        return arr
    shifted = arr.astype(np.int16) + int(round(float(brightness)))
    return np.clip(shifted, 0, 255).astype(np.uint8)


def error_level_analysis(
    img: np.ndarray,
    quality: int = 75,
    scale: float = 10.0,
    brightness: float = 0.0,
) -> np.ndarray:
    """Recompress the image as JPEG and amplify the per-pixel difference.

    Returns an H x W x 3 uint8 RGB ndarray. ``quality`` is the recompression
    quality (1-100). ``scale`` multiplies the absolute per-channel error.
    ``brightness`` is added to the result before clipping to 0-255.

    Raises:
        ForensicError: on invalid input or quality outside 1-100.
    """
    rgb = _to_rgb_uint8(img)
    q = int(quality)
    if q < 1 or q > 100:
        raise ForensicError(f"quality must be in 1..100, got {quality}")

    pil = Image.fromarray(rgb, mode="RGB")
    buf = io.BytesIO()
    try:
        pil.save(buf, format="JPEG", quality=q)
        buf.seek(0)
        recompressed = np.asarray(Image.open(buf).convert("RGB"))
    except Exception as e:  # malformed Pillow / encoder failure
        raise ForensicError(f"JPEG round-trip failed: {e}") from e

    diff = np.abs(rgb.astype(np.int16) - recompressed.astype(np.int16))
    amplified = diff.astype(np.float32) * float(scale)
    out = np.clip(amplified, 0, 255).astype(np.uint8)
    return _apply_brightness(out, brightness)


def _box_blur_3x3(rgb: np.ndarray) -> np.ndarray:
    """3x3 box blur with edge padding. RGB uint8 in, RGB uint8 out."""
    pad = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge").astype(np.int32)
    s = (
        pad[0:-2, 0:-2] + pad[0:-2, 1:-1] + pad[0:-2, 2:]
        + pad[1:-1, 0:-2] + pad[1:-1, 1:-1] + pad[1:-1, 2:]
        + pad[2:,   0:-2] + pad[2:,   1:-1] + pad[2:,   2:]
    )
    return (s // 9).astype(np.uint8)


def noise_map(
    img: np.ndarray,
    scale: float = 4.0,
    brightness: float = 0.0,
) -> np.ndarray:
    """Visualize high-frequency content as a brightness map.

    Computes ``|img - blur3x3(img)|`` per channel, multiplies by ``scale``,
    optionally adds ``brightness``, and clips to uint8.

    Returns an H x W x 3 uint8 RGB ndarray.
    """
    rgb = _to_rgb_uint8(img)
    blurred = _box_blur_3x3(rgb)
    diff = np.abs(rgb.astype(np.int16) - blurred.astype(np.int16))
    amplified = diff.astype(np.float32) * float(scale)
    out = np.clip(amplified, 0, 255).astype(np.uint8)
    return _apply_brightness(out, brightness)
