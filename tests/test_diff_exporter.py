from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from cove_image_lab.diff_exporter import DiffExportError, export_png


def test_round_trip_rgb(tmp_path):
    arr = np.zeros((4, 5, 3), dtype=np.uint8)
    arr[1, 2] = (200, 50, 25)
    out = export_png(arr, tmp_path / "diff.png")
    assert out.exists()
    back = np.asarray(Image.open(out).convert("RGB"))
    assert back.shape == arr.shape
    assert np.array_equal(back, arr)


def test_round_trip_grayscale(tmp_path):
    arr = np.full((3, 3), 64, dtype=np.uint8)
    out = export_png(arr, tmp_path / "diff.png")
    back = np.asarray(Image.open(out).convert("L"))
    assert np.array_equal(back, arr)


def test_round_trip_rgba(tmp_path):
    arr = np.zeros((3, 3, 4), dtype=np.uint8)
    arr[..., 0] = 10
    arr[..., 3] = 200
    out = export_png(arr, tmp_path / "diff.png")
    back = np.asarray(Image.open(out).convert("RGBA"))
    assert np.array_equal(back, arr)


def test_rejects_non_uint8(tmp_path):
    with pytest.raises(DiffExportError):
        export_png(np.zeros((3, 3, 3), dtype=np.float32), tmp_path / "x.png")


def test_rejects_unsupported_shape(tmp_path):
    with pytest.raises(DiffExportError):
        export_png(np.zeros((3, 3, 5), dtype=np.uint8), tmp_path / "x.png")


def test_rejects_non_array(tmp_path):
    with pytest.raises(DiffExportError):
        export_png([[0, 0, 0]], tmp_path / "x.png")  # type: ignore[arg-type]


def test_underlying_save_failure_is_wrapped_as_diff_export_error(monkeypatch, tmp_path):
    """A failing Pillow save must surface as DiffExportError on every platform.

    Cross-platform replacement for the previous chmod(0o500)-based test, which
    could behave differently on Windows and in privileged environments.
    Forces a deterministic OSError from Image.save and asserts that
    export_png converts it to DiffExportError without leaking the raw error.
    """
    arr = np.zeros((2, 2, 3), dtype=np.uint8)

    def fail_save(self, *args, **kwargs):
        raise OSError("simulated disk full")

    monkeypatch.setattr(Image.Image, "save", fail_save)

    with pytest.raises(DiffExportError) as exc_info:
        export_png(arr, tmp_path / "diff.png")
    assert "simulated disk full" in str(exc_info.value)
