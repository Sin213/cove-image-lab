"""Pure image loading: file path -> RGBA uint8 ndarray. No Qt imports."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image, UnidentifiedImageError


class ImageLoadError(Exception):
    """Raised when a file cannot be read as an image."""


def load_rgba(path: str | os.PathLike) -> np.ndarray:
    """Load an image and return an H x W x 4 uint8 RGBA ndarray.

    Grayscale, palette, RGB, and 16-bit images are normalized to RGBA.
    Multi-frame files yield the first frame.
    """
    p = Path(path)
    if not p.exists():
        raise ImageLoadError(f"File not found: {p}")
    if not p.is_file():
        raise ImageLoadError(f"Not a file: {p}")
    try:
        with Image.open(p) as img:
            img.load()
            rgba = img.convert("RGBA")
            arr = np.asarray(rgba, dtype=np.uint8)
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ImageLoadError(f"Could not decode image: {p} ({e})") from e

    if arr.ndim != 3 or arr.shape[2] != 4:
        raise ImageLoadError(f"Unexpected array shape after RGBA convert: {arr.shape}")
    return arr
