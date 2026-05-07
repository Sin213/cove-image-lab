from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from cove_image_lab.metadata_reader import (
    Metadata,
    MetadataReadError,
    read_metadata,
)


def _png_path(tmp_path: Path, name: str = "plain.png") -> Path:
    p = tmp_path / name
    Image.fromarray(np.zeros((4, 4, 3), dtype=np.uint8), mode="RGB").save(p, "PNG")
    return p


def test_returns_metadata_dataclass(tmp_path):
    md = read_metadata(_png_path(tmp_path))
    assert isinstance(md, Metadata)


def test_plain_png_has_no_exif_or_camera_or_gps(tmp_path):
    md = read_metadata(_png_path(tmp_path))
    assert md.exif == {}
    assert md.camera_model is None
    assert md.gps is None
    assert md.has_thumbnail is False


def test_plain_png_records_format_and_size(tmp_path):
    md = read_metadata(_png_path(tmp_path))
    assert md.format == "PNG"
    assert md.size == (4, 4)
    assert md.has_metadata is False


def test_missing_file_raises(tmp_path):
    with pytest.raises(MetadataReadError):
        read_metadata(tmp_path / "nope.png")


def test_non_image_raises(tmp_path):
    bad = tmp_path / "not_image.txt"
    bad.write_text("hello")
    with pytest.raises(MetadataReadError):
        read_metadata(bad)


def test_directory_raises(tmp_path):
    with pytest.raises(MetadataReadError):
        read_metadata(tmp_path)


def test_jpeg_with_exif_camera_make_and_model(tmp_path):
    p = tmp_path / "with_exif.jpg"
    img = Image.fromarray(np.full((8, 8, 3), 200, dtype=np.uint8), mode="RGB")
    exif = img.getexif()
    # 0x010F = Make, 0x0110 = Model, 0x0131 = Software, 0x0132 = DateTime
    exif[0x010F] = "CoveCam"
    exif[0x0110] = "X100"
    exif[0x0131] = "Cove Image Lab Test"
    exif[0x0132] = "2026:05:06 12:00:00"
    img.save(p, "JPEG", exif=exif.tobytes(), quality=90)

    md = read_metadata(p)
    assert md.camera_make == "CoveCam"
    assert md.camera_model == "X100"
    assert md.software == "Cove Image Lab Test"
    assert md.datetime_original == "2026:05:06 12:00:00"
    assert md.has_metadata is True
    # exif dict should be populated with at least these tags
    assert "Make" in md.exif or any("Make" in k for k in md.exif)
    # Critical: regular EXIF without an actual thumbnail must NOT report
    # has_thumbnail=True. Reading ExifIFD must not be confused with IFD1.
    assert md.has_thumbnail is False
    # And there must be no GPS data when none was written.
    assert md.gps is None


def test_jpeg_with_gps_ifd_reports_decimal_degrees(tmp_path):
    p = tmp_path / "with_gps.jpg"
    img = Image.fromarray(np.full((8, 8, 3), 180, dtype=np.uint8), mode="RGB")
    exif = img.getexif()
    # Add IFD0 entries so the file looks like a normal camera JPEG.
    exif[0x010F] = "CoveCam"
    exif[0x0110] = "GPS-Test"
    # GPS tags live in the GPS IFD, accessed via the GPSInfo pointer (0x8825).
    gps_ifd = exif.get_ifd(0x8825)
    gps_ifd[1] = "N"                    # GPSLatitudeRef
    gps_ifd[2] = (37.0, 26.0, 0.0)      # GPSLatitude (D, M, S)
    gps_ifd[3] = "W"                    # GPSLongitudeRef
    gps_ifd[4] = (122.0, 5.0, 0.0)      # GPSLongitude (D, M, S)
    gps_ifd[6] = 100.0                  # GPSAltitude
    img.save(p, "JPEG", exif=exif.tobytes(), quality=90)

    md = read_metadata(p)
    assert md.gps is not None, "GPS IFD must be parsed via get_ifd(0x8825)"
    assert md.gps.get("latitude") == pytest.approx(37.0 + 26.0 / 60.0, abs=1e-5)
    # Western longitudes are negative.
    assert md.gps.get("longitude") == pytest.approx(-(122.0 + 5.0 / 60.0), abs=1e-5)
    assert md.gps.get("altitude") == pytest.approx(100.0)
    # The "Embedded thumbnail" indicator must stay False — there is no IFD1
    # thumbnail in this file, only IFD0 + GPS IFD.
    assert md.has_thumbnail is False
    # iter_rows surfaces the GPS values for the metadata table.
    keys = [k for k, _ in md.iter_rows()]
    assert "GPS latitude" in keys
    assert "GPS longitude" in keys
    assert "GPS altitude" in keys


def test_iter_rows_returns_ordered_pairs(tmp_path):
    p = tmp_path / "with_exif.jpg"
    img = Image.fromarray(np.full((8, 8, 3), 200, dtype=np.uint8), mode="RGB")
    exif = img.getexif()
    exif[0x010F] = "CoveCam"
    img.save(p, "JPEG", exif=exif.tobytes(), quality=90)

    md = read_metadata(p)
    rows = md.iter_rows()
    assert isinstance(rows, list)
    assert all(isinstance(r, tuple) and len(r) == 2 for r in rows)
    # Format and Size are always present.
    keys = [k for k, _ in rows]
    assert "Format" in keys
    assert "Size" in keys
