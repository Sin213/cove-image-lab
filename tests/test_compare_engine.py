from __future__ import annotations

import numpy as np
import pytest

from cove_image_lab.compare_engine import (
    CompareResult,
    DimensionMismatchError,
    compare,
    reapply_threshold,
    threshold_to_tolerance,
)


def test_same_image_zero_percent(solid_red, solid_red_copy):
    res = compare(solid_red, solid_red_copy, threshold=0)
    assert isinstance(res, CompareResult)
    assert res.changed_pixels == 0
    assert res.changed_percent == 0.0
    assert res.total_pixels == solid_red.shape[0] * solid_red.shape[1]


def test_one_pixel_diff_threshold_zero(one_pixel_diff):
    a, b = one_pixel_diff
    res = compare(a, b, threshold=0)
    assert res.changed_pixels == 1


def test_small_noise_ignored_at_threshold_50(small_noise):
    a, b = small_noise
    res = compare(a, b, threshold=50)
    assert res.changed_pixels == 0
    assert res.changed_percent == 0.0


def test_all_different_full_percent(solid_red, solid_blue):
    res = compare(solid_red, solid_blue, threshold=0)
    assert res.changed_pixels == res.total_pixels
    assert res.changed_percent == pytest.approx(100.0)


def test_threshold_100_zero_percent(solid_red, solid_blue):
    res = compare(solid_red, solid_blue, threshold=100)
    # At max threshold, tolerance is 255; nothing exceeds it.
    assert res.changed_pixels == 0
    assert res.changed_percent == 0.0


def test_dimension_mismatch_raises(mismatched):
    a, b = mismatched
    with pytest.raises(DimensionMismatchError):
        compare(a, b, threshold=0)


def test_threshold_monotonicity(solid_red):
    rng = np.random.default_rng(0)
    a = solid_red.copy()
    b = solid_red.copy()
    b[..., :3] = rng.integers(0, 256, size=b[..., :3].shape, dtype=np.uint8)
    pcts = [compare(a, b, t).changed_percent for t in (0, 25, 50, 75, 100)]
    for prev, curr in zip(pcts, pcts[1:]):
        assert curr <= prev + 1e-9


def test_alpha_counts_in_diff(alpha_only_diff):
    a, b = alpha_only_diff
    res = compare(a, b, threshold=0)
    assert res.changed_pixels == res.total_pixels


def test_threshold_to_tolerance_bounds():
    assert threshold_to_tolerance(0) == 0
    assert threshold_to_tolerance(100) == 255
    with pytest.raises(ValueError):
        threshold_to_tolerance(-1)
    with pytest.raises(ValueError):
        threshold_to_tolerance(101)


def test_heatmap_shape_and_dtype(solid_red, solid_blue):
    res = compare(solid_red, solid_blue, threshold=0)
    assert res.heatmap.dtype == np.uint8
    assert res.heatmap.shape == (solid_red.shape[0], solid_red.shape[1], 3)


def test_reapply_threshold_matches_compare(solid_red, solid_blue):
    res0 = compare(solid_red, solid_blue, threshold=0)
    res2 = reapply_threshold(res0.delta, threshold=50)
    expected = compare(solid_red, solid_blue, threshold=50)
    assert res2.changed_pixels == expected.changed_pixels
    assert res2.changed_percent == pytest.approx(expected.changed_percent)


def test_compare_rejects_non_uint8(solid_red):
    f = solid_red.astype(np.float32)
    with pytest.raises(ValueError):
        compare(f, f, threshold=0)


def test_chunked_path_matches_single_shot(monkeypatch):
    """Force the row-banded path on a small image and confirm bit-identity."""
    from cove_image_lab import compare_engine as ce

    rng = np.random.default_rng(123)
    a = rng.integers(0, 256, size=(64, 48, 4), dtype=np.uint8)
    b = rng.integers(0, 256, size=(64, 48, 4), dtype=np.uint8)

    single = compare(a, b, threshold=10)
    monkeypatch.setattr(ce, "CHUNKED_PIXEL_THRESHOLD", 0)
    monkeypatch.setattr(ce, "CHUNK_ROWS", 7)  # awkward stride to expose off-by-one
    chunked = compare(a, b, threshold=10)

    assert np.array_equal(single.delta, chunked.delta)
    assert np.array_equal(single.mask, chunked.mask)
    assert np.array_equal(single.heatmap, chunked.heatmap)
    assert single.changed_pixels == chunked.changed_pixels
