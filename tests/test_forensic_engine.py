from __future__ import annotations

import numpy as np
import pytest

from cove_image_lab.forensic_engine import (
    ForensicError,
    error_level_analysis,
    noise_map,
)


def _solid(h: int, w: int, rgba: tuple[int, int, int, int]) -> np.ndarray:
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :] = np.array(rgba, dtype=np.uint8)
    return arr


def _gradient_rgb(h: int = 16, w: int = 16) -> np.ndarray:
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[..., 0] = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    arr[..., 1] = np.tile(np.linspace(0, 255, h, dtype=np.uint8)[:, None], (1, w))
    arr[..., 2] = 128
    return arr


# --- ELA -----------------------------------------------------------------

def test_ela_returns_uint8_rgb_same_hw_for_rgb():
    img = _gradient_rgb(20, 24)
    out = error_level_analysis(img, quality=75, scale=10.0, brightness=0.0)
    assert isinstance(out, np.ndarray)
    assert out.dtype == np.uint8
    assert out.shape == (20, 24, 3)


def test_ela_returns_uint8_rgb_for_rgba_input():
    img = _solid(12, 14, (10, 200, 50, 200))
    # add some structure so JPEG actually loses info
    img[3:7, 4:10, :3] = (240, 30, 90)
    out = error_level_analysis(img, quality=80)
    assert out.dtype == np.uint8
    assert out.shape == (12, 14, 3)


def test_ela_solid_image_does_not_crash_and_is_dark():
    img = _solid(8, 8, (120, 120, 120, 255))
    out = error_level_analysis(img, quality=90, scale=10.0)
    assert out.shape == (8, 8, 3)
    # A solid image survives JPEG round-trip with very small error; amplified
    # output should still be on the dark side (well below saturation).
    assert out.mean() < 64


def test_ela_higher_scale_increases_brightness_on_lossy_image():
    img = _gradient_rgb(20, 20)
    low = error_level_analysis(img, quality=40, scale=1.0)
    high = error_level_analysis(img, quality=40, scale=20.0)
    assert high.mean() > low.mean()


def test_ela_brightness_shifts_output_up():
    img = _gradient_rgb(16, 16)
    base = error_level_analysis(img, quality=50, scale=4.0, brightness=0.0)
    bright = error_level_analysis(img, quality=50, scale=4.0, brightness=80.0)
    assert bright.mean() > base.mean()


def test_ela_quality_100_is_quieter_than_quality_30():
    img = _gradient_rgb(24, 24)
    quiet = error_level_analysis(img, quality=100, scale=10.0)
    loud = error_level_analysis(img, quality=30, scale=10.0)
    assert loud.mean() >= quiet.mean()


def test_ela_rejects_invalid_quality():
    img = _gradient_rgb(8, 8)
    with pytest.raises(ForensicError):
        error_level_analysis(img, quality=0)
    with pytest.raises(ForensicError):
        error_level_analysis(img, quality=101)


def test_ela_rejects_non_uint8():
    img = np.zeros((8, 8, 3), dtype=np.float32)
    with pytest.raises(ForensicError):
        error_level_analysis(img)


def test_ela_rejects_grayscale_2d():
    img = np.zeros((8, 8), dtype=np.uint8)
    with pytest.raises(ForensicError):
        error_level_analysis(img)


# --- Noise map -----------------------------------------------------------

def test_noise_map_returns_uint8_rgb_same_hw_for_rgb():
    img = _gradient_rgb(20, 24)
    out = noise_map(img, scale=4.0, brightness=0.0)
    assert out.dtype == np.uint8
    assert out.shape == (20, 24, 3)


def test_noise_map_returns_uint8_rgb_for_rgba_input():
    img = _solid(12, 14, (40, 80, 160, 255))
    out = noise_map(img)
    assert out.dtype == np.uint8
    assert out.shape == (12, 14, 3)


def test_noise_map_solid_image_is_near_black():
    img = _solid(16, 16, (90, 90, 90, 255))
    out = noise_map(img, scale=8.0)
    # A perfectly flat image has no high-frequency content.
    assert out.mean() < 8


def test_noise_map_noisy_image_brighter_than_flat():
    flat = _solid(32, 32, (128, 128, 128, 255))
    rng = np.random.default_rng(seed=7)
    noisy = flat.copy()
    noisy[..., :3] = np.clip(
        flat[..., :3].astype(np.int16) + rng.integers(-30, 31, size=(32, 32, 3)),
        0,
        255,
    ).astype(np.uint8)
    a = noise_map(flat, scale=4.0)
    b = noise_map(noisy, scale=4.0)
    assert b.mean() > a.mean() + 4


def test_noise_map_brightness_shifts_output_up():
    img = _gradient_rgb(16, 16)
    base = noise_map(img, scale=2.0, brightness=0.0)
    bright = noise_map(img, scale=2.0, brightness=60.0)
    assert bright.mean() > base.mean()


def test_noise_map_rejects_non_uint8():
    img = np.zeros((8, 8, 3), dtype=np.float32)
    with pytest.raises(ForensicError):
        noise_map(img)
