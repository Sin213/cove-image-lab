"""Local metadata extraction for forensic inspection.

Reads EXIF (and where available, XMP / PNG textual metadata) from a local
image file using Pillow only. No network calls. No GPS lookups. Missing or
malformed metadata never raises — the call returns a Metadata instance with
the relevant fields set to None / {}.

The only error raised is :class:`MetadataReadError`, which is reserved for
"the file itself is not a readable image" (missing, directory, malformed).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import ExifTags, Image, UnidentifiedImageError

_log = logging.getLogger(__name__)


class MetadataReadError(ValueError):
    """The path could not be opened as an image."""


@dataclass
class Metadata:
    path: Path
    format: str | None = None
    size: tuple[int, int] | None = None
    mode: str | None = None

    camera_make: str | None = None
    camera_model: str | None = None
    software: str | None = None
    datetime_original: str | None = None

    gps: dict[str, Any] | None = None
    has_thumbnail: bool = False

    exif: dict[str, Any] = field(default_factory=dict)
    xmp: str | None = None
    png_text: dict[str, str] = field(default_factory=dict)

    @property
    def has_metadata(self) -> bool:
        return bool(
            self.exif
            or self.xmp
            or self.png_text
            or self.camera_make
            or self.camera_model
            or self.software
            or self.datetime_original
            or self.gps
            or self.has_thumbnail
        )

    def iter_rows(self) -> list[tuple[str, str]]:
        """Return ordered (label, value) pairs for display in a table.

        Always includes Format and Size so a metadata-less image still has
        something to show.
        """
        rows: list[tuple[str, str]] = []
        if self.format:
            rows.append(("Format", self.format))
        if self.size:
            w, h = self.size
            rows.append(("Size", f"{w}×{h}"))
        if self.mode:
            rows.append(("Mode", self.mode))
        if self.camera_make:
            rows.append(("Camera make", str(self.camera_make)))
        if self.camera_model:
            rows.append(("Camera model", str(self.camera_model)))
        if self.software:
            rows.append(("Software", str(self.software)))
        if self.datetime_original:
            rows.append(("Date/time", str(self.datetime_original)))
        if self.has_thumbnail:
            rows.append(("Embedded thumbnail", "yes"))
        if self.gps:
            for k in ("latitude", "longitude", "altitude"):
                v = self.gps.get(k)
                if v is not None:
                    rows.append((f"GPS {k}", str(v)))
        # remaining EXIF tags, sorted, that we didn't already surface
        already = {"Make", "Model", "Software", "DateTime", "DateTimeOriginal"}
        for k in sorted(self.exif.keys()):
            if k in already:
                continue
            v = self.exif[k]
            rows.append((f"EXIF {k}", _short(v)))
        if self.xmp:
            rows.append(("XMP", _short(self.xmp)))
        for k, v in sorted(self.png_text.items()):
            rows.append((f"PNG:{k}", _short(v)))
        return rows


def _short(value: Any, limit: int = 200) -> str:
    s = repr(value) if not isinstance(value, str) else value
    s = s.replace("\r", " ").replace("\n", " ")
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _coerce(value: Any) -> Any:
    """Best-effort coercion of EXIF values to JSON-friendly Python types."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").rstrip("\x00").strip()
        except (UnicodeDecodeError, TypeError, AttributeError) as exc:
            _log.warning("_coerce: could not decode bytes value: %s", exc)
            return repr(value)
    if isinstance(value, str):
        return value.rstrip("\x00").strip()
    return value


def _read_gps_ifd(raw_exif: Any) -> dict[int, Any] | None:
    """Fetch the GPS IFD as a dict with numeric tag keys.

    Standard Pillow EXIF stores GPS data behind the GPSInfo pointer (tag
    0x8825); the nested dict must be retrieved via ``Exif.get_ifd(0x8825)``.
    A small fallback handles the rare case where some loaders expose
    GPSInfo inline via ``items()``.
    """
    if raw_exif is None:
        return None
    try:
        ifd = raw_exif.get_ifd(0x8825)
    except Exception:
        ifd = None
    if isinstance(ifd, dict) and ifd:
        return dict(ifd)
    try:
        for tag_id, value in raw_exif.items():
            if tag_id == 0x8825 and isinstance(value, dict) and value:
                return dict(value)
    except Exception:
        pass
    return None


def _gps_from_ifd(gps_ifd: dict[int, Any] | None) -> dict[str, Any] | None:
    """Convert a GPS IFD dict (numeric tag keys) into named decimal-degree fields."""
    if not gps_ifd:
        return None
    out: dict[str, Any] = {}
    try:
        gps_named = {
            ExifTags.GPSTAGS.get(tag, str(tag)): val for tag, val in gps_ifd.items()
        }
        lat = _dms_to_deg(gps_named.get("GPSLatitude"), gps_named.get("GPSLatitudeRef"))
        lon = _dms_to_deg(gps_named.get("GPSLongitude"), gps_named.get("GPSLongitudeRef"))
        alt = gps_named.get("GPSAltitude")
        if lat is not None:
            out["latitude"] = lat
        if lon is not None:
            out["longitude"] = lon
        if alt is not None:
            try:
                out["altitude"] = float(alt)
            except Exception:
                out["altitude"] = str(alt)
    except Exception:
        return None
    return out or None


def _has_embedded_thumbnail(raw_exif: Any, info: dict[str, Any]) -> bool:
    """Conservative detection of an actual embedded thumbnail.

    Returns True only with direct evidence — either a thumbnail blob exposed
    in ``Image.info`` or a populated IFD1 (the JPEG thumbnail IFD) carrying a
    non-empty JPEGInterchangeFormat / JPEGInterchangeFormatLength entry.
    Reading the ExifIFD pointer (0x8769) is **not** thumbnail evidence and
    is no longer used.
    """
    if info.get("thumbnail") or info.get("ThumbnailImage"):
        return True
    if raw_exif is None:
        return False
    ifd_enum = getattr(ExifTags, "IFD", None)
    ifd1_key = getattr(ifd_enum, "IFD1", None) if ifd_enum is not None else None
    if ifd1_key is None:
        return False
    try:
        ifd1 = raw_exif.get_ifd(ifd1_key)
    except Exception:
        return False
    if not isinstance(ifd1, dict) or not ifd1:
        return False
    # JPEGInterchangeFormat = 0x0201, JPEGInterchangeFormatLength = 0x0202.
    length = ifd1.get(0x0202)
    if length is not None:
        try:
            return int(length) > 0
        except Exception:
            return True
    return 0x0201 in ifd1


def _dms_to_deg(dms: Any, ref: Any) -> float | None:
    if not dms:
        return None
    try:
        d, m, s = (float(x) for x in dms)
        deg = d + m / 60.0 + s / 3600.0
        if isinstance(ref, str) and ref.upper() in ("S", "W"):
            deg = -deg
        return round(deg, 7)
    except Exception:
        return None


def read_metadata(path: str | os.PathLike) -> Metadata:
    """Read metadata from an image file. Never raises on missing fields."""
    p = Path(path)
    if not p.exists() or p.is_dir():
        raise MetadataReadError(f"not a readable file: {p}")

    try:
        img = Image.open(p)
        img.load()
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise MetadataReadError(f"could not open as image: {e}") from e

    md = Metadata(path=p, format=img.format, size=img.size, mode=img.mode)

    # --- EXIF ----------------------------------------------------------------
    try:
        raw_exif = img.getexif()
    except Exception:
        raw_exif = None

    exif_dict: dict[str, Any] = {}
    if raw_exif:
        try:
            for tag_id, value in raw_exif.items():
                name = ExifTags.TAGS.get(tag_id, f"0x{tag_id:04X}")
                if name == "GPSInfo" and isinstance(value, (dict, type(raw_exif))):
                    exif_dict["GPSInfo"] = dict(value)
                else:
                    exif_dict[name] = _coerce(value)
        except Exception:
            exif_dict = {}

    md.exif = {k: v for k, v in exif_dict.items() if k != "GPSInfo"}
    md.gps = _gps_from_ifd(_read_gps_ifd(raw_exif))

    md.camera_make = _str_or_none(exif_dict.get("Make"))
    md.camera_model = _str_or_none(exif_dict.get("Model"))
    md.software = _str_or_none(exif_dict.get("Software"))
    md.datetime_original = _str_or_none(
        exif_dict.get("DateTimeOriginal") or exif_dict.get("DateTime")
    )

    # --- XMP / PNG text ------------------------------------------------------
    info = getattr(img, "info", {}) or {}
    xmp = info.get("XML:com.adobe.xmp") or info.get("xmp")
    if isinstance(xmp, bytes):
        try:
            xmp = xmp.decode("utf-8", errors="replace")
        except Exception:
            xmp = None
    if isinstance(xmp, str) and xmp.strip():
        md.xmp = xmp.strip()

    # PNG textual chunks land in info as plain strings.
    if img.format == "PNG":
        for key, val in info.items():
            if isinstance(key, str) and isinstance(val, str) and key not in {
                "xmp",
                "XML:com.adobe.xmp",
            }:
                md.png_text[key] = val

    # --- thumbnail -----------------------------------------------------------
    md.has_thumbnail = _has_embedded_thumbnail(raw_exif, info)

    return md


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None
