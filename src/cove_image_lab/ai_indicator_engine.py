"""AI Indicator engine: turn local metadata into transparent indicator rows.

Rules of the road (enforced by tests in ``tests/test_ai_indicator_engine.py``):
    * Local-only. No network, no model, no SDK, no telemetry.
    * Indicators surface what was observed and explain why it may or may not
      matter. They never claim AI generation, manipulation, authenticity, or
      a verdict, and they never carry a numeric score.
    * Severity is a coarse chip — one of ``weak context``, ``possible signal``,
      ``worth a look``. There is no aggregated total or "X of Y triggered".
    * Output strings stay neutral. The banned-wording test rejects words like
      ``fake``, ``real``, ``authentic``, ``verified``, ``manipulated``,
      ``tampered``, ``deepfake``, ``ai generated``, ``confidence``, ``proof``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .metadata_reader import Metadata


SEVERITY_WEAK = "weak context"
SEVERITY_POSSIBLE = "possible signal"
SEVERITY_WORTH = "worth a look"

_VALID_SEVERITIES = frozenset({SEVERITY_WEAK, SEVERITY_POSSIBLE, SEVERITY_WORTH})

# How many bytes of the head of a file we are willing to scan for content
# credential markers. Kept small so the scan stays cheap and bounded.
_C2PA_HEAD_LIMIT = 256 * 1024


@dataclass(frozen=True)
class Indicator:
    """One transparent indicator row.

    ``label`` is a short headline. ``observation`` is what was found in the
    file. ``explanation`` is the plain-language reason it may or may not
    matter. ``severity`` is one of the three chip categories.
    """

    label: str
    observation: str
    explanation: str
    severity: str

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"invalid severity {self.severity!r}; "
                f"expected one of {sorted(_VALID_SEVERITIES)}"
            )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze(metadata: Metadata) -> list[Indicator]:
    """Return a list of Indicator rows for ``metadata``.

    The order is stable and deterministic so the UI does not jitter between
    refreshes. An empty list is a valid result and means no indicators were
    extractable from the available metadata.
    """
    rows: list[Indicator] = []

    rows.extend(_software_indicator(metadata))
    rows.extend(_camera_indicators(metadata))
    rows.extend(_datetime_indicator(metadata))
    rows.extend(_xmp_indicator(metadata))
    rows.extend(_png_text_indicators(metadata))
    rows.extend(_format_size_context(metadata))
    rows.extend(_c2pa_marker_indicator(metadata))

    return rows


# ---------------------------------------------------------------------------
# Indicator builders
# ---------------------------------------------------------------------------

def _software_indicator(md: Metadata) -> Iterable[Indicator]:
    if not md.software:
        return ()
    value = _short(md.software, 120)
    return (
        Indicator(
            label="Software / editor tag",
            observation=f'Software field is set: "{value}".',
            explanation=(
                "The Software tag records what wrote or last saved the file. "
                "It can be set by editors, exporters, and image-generation "
                "tools, and it can also be edited or removed by hand. Read "
                "it as one input among many, not as a determination."
            ),
            severity=SEVERITY_POSSIBLE,
        ),
    )


def _camera_indicators(md: Metadata) -> Iterable[Indicator]:
    if md.camera_make or md.camera_model:
        parts = [p for p in (md.camera_make, md.camera_model) if p]
        joined = " / ".join(_short(p, 80) for p in parts)
        return (
            Indicator(
                label="Camera make/model",
                observation=f"Camera fields present: {joined}.",
                explanation=(
                    "Camera make and model fields can be carried over from "
                    "the original capture, but they can also be copied from "
                    "another file or written by hand. Treat them as context, "
                    "not as a determination."
                ),
                severity=SEVERITY_WEAK,
            ),
        )
    return (
        Indicator(
            label="No camera metadata",
            observation="No camera make or model fields are present.",
            explanation=(
                "Many original photos do carry camera fields, but "
                "screenshots, social-media uploads, recompressions, and "
                "exports routinely strip them. Absence is common and is not "
                "a determination on its own."
            ),
            severity=SEVERITY_WEAK,
        ),
    )


def _datetime_indicator(md: Metadata) -> Iterable[Indicator]:
    if not md.datetime_original:
        return ()
    value = _short(md.datetime_original, 80)
    return (
        Indicator(
            label="Capture date/time",
            observation=f"DateTime field present: {value}.",
            explanation=(
                "Capture dates can be retained from the original camera, but "
                "they can also be authored, copied, or rewritten by any tool. "
                "Use as context, not as a determination."
            ),
            severity=SEVERITY_WEAK,
        ),
    )


def _xmp_indicator(md: Metadata) -> Iterable[Indicator]:
    if not md.xmp:
        return ()
    snippet = _short(md.xmp, 160)
    return (
        Indicator(
            label="XMP packet",
            observation=(
                f"XMP metadata packet present (~{len(md.xmp)} chars). "
                f"Snippet: {snippet}"
            ),
            explanation=(
                "XMP packets often carry editing-tool names, workflow tags, "
                "or generator strings. Inspect the packet for tool or "
                "history hints, while remembering metadata can be authored, "
                "copied, or removed."
            ),
            severity=SEVERITY_WORTH,
        ),
    )


def _png_text_indicators(md: Metadata) -> Iterable[Indicator]:
    if not md.png_text:
        return ()
    out: list[Indicator] = []
    for key in sorted(md.png_text.keys()):
        value = md.png_text[key]
        snippet = _short(value, 160)
        out.append(
            Indicator(
                label=f"PNG text chunk: {key}",
                observation=f'PNG text "{key}" = {snippet}',
                explanation=(
                    "PNG text chunks can be added by any tool, including "
                    "image editors and image-generation pipelines. Read the "
                    "value as one input; it can be set, copied, or removed "
                    "by hand."
                ),
                severity=SEVERITY_WORTH,
            )
        )
    return out


def _format_size_context(md: Metadata) -> Iterable[Indicator]:
    if md.has_metadata:
        return ()
    fmt = md.format or "unknown"
    if md.size is not None:
        w, h = md.size
        size_part = f"{w}×{h}"
    else:
        size_part = "unknown size"
    return (
        Indicator(
            label="No metadata at all",
            observation=(
                f"Format {fmt}, {size_part}. No EXIF, XMP, or PNG text "
                f"fields were found."
            ),
            explanation=(
                "Many normal workflows produce metadata-free files: "
                "screenshots, web uploads, recompression, format "
                "conversions, and re-saves. Absence of metadata is common "
                "and is not a determination on its own."
            ),
            severity=SEVERITY_WEAK,
        ),
    )


def _c2pa_marker_indicator(md: Metadata) -> Iterable[Indicator]:
    if not _has_c2pa_marker(md.path):
        return ()
    return (
        Indicator(
            label="Content credential marker",
            observation=(
                "Byte marker associated with C2PA / JUMBF content "
                "credentials was found in the file head."
            ),
            explanation=(
                "Content credential frameworks can be added by capture "
                "devices, editors, or image-generation tools. The marker "
                "indicates a manifest may be embedded; reading the manifest "
                "and checking its claims requires a separate verifier."
            ),
            severity=SEVERITY_WORTH,
        ),
    )


# ---------------------------------------------------------------------------
# Tiny in-repo C2PA / JUMBF byte sniffer
# ---------------------------------------------------------------------------

def _has_c2pa_marker(path: Path | None) -> bool:
    """Bounded scan: look for ``jumb`` / ``c2pa`` ASCII in the file head.

    JUMBF (the container that carries C2PA manifests) uses ``jumb`` as the
    box type. Many encoders also embed the literal ``c2pa`` namespace
    string near the manifest. We only read up to ``_C2PA_HEAD_LIMIT`` bytes
    so the scan stays cheap and never opens the network or a parser.
    """
    if path is None:
        return False
    try:
        with open(path, "rb") as fh:
            head = fh.read(_C2PA_HEAD_LIMIT)
    except OSError:
        return False
    if not head:
        return False
    return b"jumb" in head or b"c2pa" in head


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _short(value: object, limit: int) -> str:
    s = value if isinstance(value, str) else repr(value)
    s = s.replace("\r", " ").replace("\n", " ").strip()
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s
