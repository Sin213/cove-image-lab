"""Shared NumPy fixtures for compare/loader/exporter tests."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _solid(h: int, w: int, color: tuple[int, int, int, int]) -> np.ndarray:
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :] = np.array(color, dtype=np.uint8)
    return arr


@pytest.fixture
def solid_red() -> np.ndarray:
    return _solid(8, 8, (255, 0, 0, 255))


@pytest.fixture
def solid_red_copy() -> np.ndarray:
    return _solid(8, 8, (255, 0, 0, 255))


@pytest.fixture
def solid_blue() -> np.ndarray:
    return _solid(8, 8, (0, 0, 255, 255))


@pytest.fixture
def one_pixel_diff(solid_red: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = solid_red.copy()
    b = solid_red.copy()
    b[0, 0] = (0, 255, 0, 255)
    return a, b


@pytest.fixture
def small_noise(solid_red: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Two images differing by tiny per-channel noise (max 4)."""
    a = solid_red.copy()
    rng = np.random.default_rng(seed=42)
    noise = rng.integers(-4, 5, size=a.shape, dtype=np.int16)
    b = np.clip(a.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    # alpha untouched
    b[..., 3] = a[..., 3]
    return a, b


@pytest.fixture
def alpha_only_diff(solid_red: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a = solid_red.copy()
    b = solid_red.copy()
    b[..., 3] = 128  # alpha differs across the whole image
    return a, b


@pytest.fixture
def mismatched(solid_red: np.ndarray, solid_blue: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    smaller = solid_blue[:4, :4, :].copy()
    return solid_red, smaller


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    d = tmp_path / "fx"
    d.mkdir()
    return d


@pytest.fixture
def rgb_jpeg_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "rgb.jpg"
    Image.fromarray(np.full((6, 6, 3), 200, dtype=np.uint8), mode="RGB").save(p, format="JPEG", quality=95)
    return p


@pytest.fixture
def rgba_png_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "rgba.png"
    arr = np.zeros((6, 6, 4), dtype=np.uint8)
    arr[..., 0] = 100
    arr[..., 3] = 200
    Image.fromarray(arr, mode="RGBA").save(p, format="PNG")
    return p


@pytest.fixture
def grayscale_png_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "gray.png"
    Image.fromarray(np.full((6, 6), 128, dtype=np.uint8), mode="L").save(p, format="PNG")
    return p


@pytest.fixture
def palette_png_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "palette.png"
    base = Image.fromarray(np.full((6, 6, 3), 50, dtype=np.uint8), mode="RGB")
    base.convert("P", palette=Image.Palette.ADAPTIVE).save(p, format="PNG")
    return p


@pytest.fixture
def non_image_path(fixtures_dir: Path) -> Path:
    p = fixtures_dir / "not_an_image.txt"
    p.write_text("this is not an image")
    return p
