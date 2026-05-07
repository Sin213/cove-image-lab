from __future__ import annotations

import numpy as np
import pytest

from cove_image_lab.image_loader import ImageLoadError, load_rgba


def test_load_rgb_jpeg_returns_rgba_alpha_255(rgb_jpeg_path):
    arr = load_rgba(rgb_jpeg_path)
    assert arr.dtype == np.uint8
    assert arr.shape[2] == 4
    assert (arr[..., 3] == 255).all()


def test_load_rgba_png_preserves_alpha(rgba_png_path):
    arr = load_rgba(rgba_png_path)
    assert arr.shape[2] == 4
    assert (arr[..., 3] == 200).all()


def test_load_grayscale_png_normalizes_channels(grayscale_png_path):
    arr = load_rgba(grayscale_png_path)
    assert arr.shape[2] == 4
    # R == G == B in a grayscale->RGBA convert.
    assert np.array_equal(arr[..., 0], arr[..., 1])
    assert np.array_equal(arr[..., 1], arr[..., 2])


def test_load_palette_png_returns_rgba(palette_png_path):
    arr = load_rgba(palette_png_path)
    assert arr.shape[2] == 4


def test_missing_file_raises(tmp_path):
    with pytest.raises(ImageLoadError):
        load_rgba(tmp_path / "nope.png")


def test_non_image_file_raises(non_image_path):
    with pytest.raises(ImageLoadError):
        load_rgba(non_image_path)


def test_directory_raises(tmp_path):
    with pytest.raises(ImageLoadError):
        load_rgba(tmp_path)
