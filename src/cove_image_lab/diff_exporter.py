"""PNG export for diff heatmaps. No Qt imports."""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
from PIL import Image


class DiffExportError(Exception):
    """Raised when a heatmap cannot be written to disk."""


def export_png(heatmap: np.ndarray, path: str | os.PathLike) -> Path:
    """Write a heatmap ndarray as a PNG. Returns the resolved path."""
    if not isinstance(heatmap, np.ndarray):
        raise DiffExportError("heatmap must be a numpy ndarray.")
    if heatmap.dtype != np.uint8:
        raise DiffExportError("heatmap must be uint8.")
    if heatmap.ndim == 2:
        img = Image.fromarray(heatmap, mode="L")
    elif heatmap.ndim == 3 and heatmap.shape[2] == 3:
        img = Image.fromarray(heatmap, mode="RGB")
    elif heatmap.ndim == 3 and heatmap.shape[2] == 4:
        img = Image.fromarray(heatmap, mode="RGBA")
    else:
        raise DiffExportError(f"Unsupported heatmap shape: {heatmap.shape}")

    p = Path(path)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        img.save(p, format="PNG")
    except (OSError, ValueError) as e:
        raise DiffExportError(f"Could not write PNG to {p}: {e}") from e
    return p
