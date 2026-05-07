"""Tests for the privacy-critical render_redacted primitive.

These are pure-function tests with no Qt imports.
"""
from __future__ import annotations

import numpy as np
import pytest

from cove_image_lab.redaction_view import render_redacted


def _rgb_grad(h: int = 16, w: int = 24) -> np.ndarray:
    yy, xx = np.mgrid[:h, :w]
    return np.stack([
        (xx * 11 % 256).astype(np.uint8),
        (yy * 17 % 256).astype(np.uint8),
        ((xx + yy) * 7 % 256).astype(np.uint8),
    ], axis=2)


def _rgba_grad(h: int = 16, w: int = 24, alpha: int = 200) -> np.ndarray:
    rgb = _rgb_grad(h, w)
    a = np.full((h, w, 1), alpha, dtype=np.uint8)
    return np.concatenate([rgb, a], axis=2)


# ---------- happy path -----------------------------------------------------

def test_no_rects_returns_identical_copy():
    src = _rgb_grad()
    out = render_redacted(src, [])
    assert out.shape == src.shape
    assert out.dtype == src.dtype
    assert np.array_equal(out, src)
    assert out is not src  # must be a copy


def test_single_rect_pixels_become_black():
    src = _rgb_grad()
    out = render_redacted(src, [(2, 3, 5, 4)])
    inside = out[3:7, 2:7]
    assert np.all(inside == 0)


def test_pixels_outside_rect_unchanged():
    src = _rgb_grad()
    out = render_redacted(src, [(2, 3, 5, 4)])
    # Build mask of touched pixels, assert everything else == src
    mask = np.zeros(src.shape[:2], dtype=bool)
    mask[3:7, 2:7] = True
    assert np.array_equal(out[~mask], src[~mask])


def test_multiple_non_overlapping_rects():
    src = _rgb_grad(20, 30)
    out = render_redacted(src, [(0, 0, 4, 4), (10, 10, 6, 6), (24, 16, 5, 3)])
    assert np.all(out[0:4, 0:4] == 0)
    assert np.all(out[10:16, 10:16] == 0)
    assert np.all(out[16:19, 24:29] == 0)
    # Spot-check an untouched region
    assert np.array_equal(out[5:9, 5:9], src[5:9, 5:9])


def test_overlapping_rects_still_black():
    src = _rgb_grad()
    out = render_redacted(src, [(2, 2, 6, 6), (4, 4, 6, 6)])
    # Union of (2..7, 2..7) and (4..9, 4..9)
    assert np.all(out[2:8, 2:8] == 0)
    assert np.all(out[4:10, 4:10] == 0)


def test_rect_covering_entire_image():
    src = _rgb_grad()
    h, w = src.shape[:2]
    out = render_redacted(src, [(0, 0, w, h)])
    assert np.all(out == 0)


# ---------- edge cases -----------------------------------------------------

def test_zero_or_negative_size_rects_ignored():
    src = _rgb_grad()
    out = render_redacted(src, [(2, 2, 0, 5), (3, 3, 5, 0), (4, 4, -3, 5)])
    assert np.array_equal(out, src)


def test_out_of_bounds_rects_clamped():
    src = _rgb_grad(10, 10)
    # Extends past the right and bottom edges; only the in-bounds portion
    # should turn black.
    out = render_redacted(src, [(7, 6, 50, 50)])
    assert np.all(out[6:10, 7:10] == 0)
    # Everything left of column 7 and above row 6 stays original.
    assert np.array_equal(out[0:6, :], src[0:6, :])
    assert np.array_equal(out[:, 0:7], src[:, 0:7])


def test_negative_origin_rects_clamped():
    src = _rgb_grad(10, 10)
    out = render_redacted(src, [(-3, -2, 5, 4)])
    # Visible portion starts at (0, 0), ends at (2, 2).
    assert np.all(out[0:2, 0:2] == 0)
    assert np.array_equal(out[2:, :], src[2:, :])
    assert np.array_equal(out[:, 2:], src[:, 2:])


def test_rect_completely_off_image_is_noop():
    src = _rgb_grad(10, 10)
    out = render_redacted(src, [(20, 20, 5, 5), (-50, -50, 3, 3)])
    assert np.array_equal(out, src)


def test_rect_with_wrong_arity_raises():
    src = _rgb_grad()
    with pytest.raises(ValueError, match="4-tuple"):
        render_redacted(src, [(1, 2, 3)])


# ---------- shape / dtype contracts ----------------------------------------

def test_rgba_input_alpha_forced_to_255_inside_rect():
    src = _rgba_grad(alpha=128)
    out = render_redacted(src, [(2, 2, 4, 4)])
    # RGB inside rect = 0
    assert np.all(out[2:6, 2:6, :3] == 0)
    # Alpha inside rect = 255 (fully opaque)
    assert np.all(out[2:6, 2:6, 3] == 255)
    # Alpha outside rect unchanged
    assert np.all(out[0:2, :, 3] == 128)


def test_rgb_input_remains_3_channel():
    src = _rgb_grad()
    out = render_redacted(src, [(0, 0, 5, 5)])
    assert out.shape[2] == 3


def test_invalid_dtype_raises():
    src = _rgb_grad().astype(np.uint16)
    with pytest.raises(ValueError, match="Unsupported"):
        render_redacted(src, [(0, 0, 4, 4)])


def test_invalid_ndim_raises():
    src = np.zeros((10, 10), dtype=np.uint8)
    with pytest.raises(ValueError, match="Unsupported"):
        render_redacted(src, [(0, 0, 4, 4)])


def test_invalid_channel_count_raises():
    src = np.zeros((10, 10, 2), dtype=np.uint8)
    with pytest.raises(ValueError, match="Unsupported"):
        render_redacted(src, [(0, 0, 4, 4)])


# ---------- privacy invariants --------------------------------------------

def test_source_array_object_not_mutated():
    src = _rgb_grad()
    src_id = id(src)
    src_bytes = src.tobytes()
    out = render_redacted(src, [(0, 0, 5, 5)])
    assert id(src) == src_id
    assert src.tobytes() == src_bytes
    assert out is not src


def test_output_writes_do_not_propagate_back_to_source():
    src = _rgb_grad()
    out = render_redacted(src, [])
    out[0, 0] = (255, 255, 255)
    assert tuple(src[0, 0]) != (255, 255, 255)
