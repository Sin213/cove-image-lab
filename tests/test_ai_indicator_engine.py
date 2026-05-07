"""Pure unit tests for the AI Indicator engine.

These tests do not launch Qt. They build ``Metadata`` instances directly,
or read a real on-disk fixture for the JUMBF marker test, and assert that
the engine produces the right rows with the right wording.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

from cove_image_lab.ai_indicator_engine import (
    Indicator,
    SEVERITY_POSSIBLE,
    SEVERITY_WEAK,
    SEVERITY_WORTH,
    analyze,
)
from cove_image_lab.metadata_reader import Metadata


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md(**overrides) -> Metadata:
    base = dict(
        path=Path("/dev/null"),
        format="PNG",
        size=(8, 8),
        mode="RGB",
    )
    base.update(overrides)
    return Metadata(**base)


def _labels(rows):
    return [r.label for r in rows]


# ---------------------------------------------------------------------------
# Indicator dataclass
# ---------------------------------------------------------------------------

def test_indicator_rejects_invalid_severity():
    with pytest.raises(ValueError):
        Indicator(label="x", observation="y", explanation="z", severity="bogus")


def test_indicator_accepts_known_severities():
    for s in (SEVERITY_WEAK, SEVERITY_POSSIBLE, SEVERITY_WORTH):
        Indicator(label="x", observation="y", explanation="z", severity=s)


# ---------------------------------------------------------------------------
# Per-category coverage
# ---------------------------------------------------------------------------

def test_no_metadata_yields_format_size_context_and_no_camera_row():
    rows = analyze(_md())  # PNG, 8x8, no other fields
    labels = _labels(rows)
    assert "No metadata at all" in labels
    assert "No camera metadata" in labels
    no_meta = next(r for r in rows if r.label == "No metadata at all")
    assert no_meta.severity == SEVERITY_WEAK
    assert "PNG" in no_meta.observation
    assert "8×8" in no_meta.observation


def test_software_field_is_a_possible_signal():
    rows = analyze(_md(software="Stable Diffusion 1.5"))
    sw = next(r for r in rows if r.label == "Software / editor tag")
    assert sw.severity == SEVERITY_POSSIBLE
    assert "Stable Diffusion 1.5" in sw.observation
    # Neutral framing — no verdict words.
    assert "fake" not in sw.explanation.lower()
    assert "verdict" not in sw.explanation.lower()


def test_camera_make_or_model_present_is_weak_context():
    rows = analyze(_md(camera_make="Canon", camera_model="EOS R5"))
    cam = next(r for r in rows if r.label == "Camera make/model")
    assert cam.severity == SEVERITY_WEAK
    assert "Canon" in cam.observation
    assert "EOS R5" in cam.observation
    # The "no camera metadata" row should NOT be emitted alongside it.
    assert "No camera metadata" not in _labels(rows)


def test_no_camera_metadata_emits_weak_context_row():
    rows = analyze(_md())
    miss = next(r for r in rows if r.label == "No camera metadata")
    assert miss.severity == SEVERITY_WEAK
    assert "common" in miss.explanation.lower()


def test_datetime_original_is_weak_context():
    rows = analyze(_md(datetime_original="2024:11:30 12:34:56"))
    dt = next(r for r in rows if r.label == "Capture date/time")
    assert dt.severity == SEVERITY_WEAK
    assert "2024:11:30" in dt.observation


def test_xmp_packet_is_worth_a_look():
    rows = analyze(_md(xmp="<x:xmpmeta>... generator: tool ... </x:xmpmeta>"))
    xmp = next(r for r in rows if r.label == "XMP packet")
    assert xmp.severity == SEVERITY_WORTH
    assert "XMP" in xmp.observation


def test_png_text_chunks_each_become_their_own_row():
    rows = analyze(
        _md(
            png_text={
                "parameters": "prompt: a cat",
                "Software": "Some Image Tool",
            }
        )
    )
    labels = _labels(rows)
    assert "PNG text chunk: parameters" in labels
    assert "PNG text chunk: Software" in labels
    # Sorted by key so the UI order is stable.
    png_rows = [r for r in rows if r.label.startswith("PNG text chunk:")]
    assert [r.label for r in png_rows] == sorted(r.label for r in png_rows)
    for r in png_rows:
        assert r.severity == SEVERITY_WORTH


def test_format_size_context_is_suppressed_when_any_metadata_is_present():
    rows = analyze(_md(software="Photoshop"))
    assert "No metadata at all" not in _labels(rows)


def test_no_summary_or_score_in_output():
    """No row should contain words that imply a verdict or numeric score."""
    rows = analyze(
        _md(
            software="Tool 1.0",
            camera_make="Leica",
            xmp="<x:xmpmeta/>",
            png_text={"k": "v"},
            datetime_original="2024:01:01 00:00:00",
        )
    )
    blob = " ".join(
        f"{r.label}\n{r.observation}\n{r.explanation}" for r in rows
    ).lower()
    for forbidden in (
        "fake",
        "real image",
        "authentic",
        "verified",
        "deepfake",
        "ai-generated",
        "ai generated",
        "manipulated",
        "tampered",
        "confidence",
        "verdict",
        "definitive",
        "conclusive",
    ):
        assert forbidden not in blob, f"banned phrase {forbidden!r} in engine output"


def test_proof_words_only_appear_in_negation_contexts():
    import re

    rows = analyze(
        _md(
            software="Tool",
            camera_make="Leica",
            xmp="<x:xmpmeta/>",
            png_text={"k": "v"},
            datetime_original="2024:01:01 00:00:00",
        )
    )
    pattern = re.compile(r"\b(proof|prov\w*)\b", re.IGNORECASE)
    allowed = re.compile(
        r"(does not\s+prov\w+|do not\s+prov\w+|not\s+proof|"
        r"never\s+prov\w+|cannot\s+prov\w+)",
        re.IGNORECASE,
    )
    for r in rows:
        for line in (r.label, r.observation, r.explanation):
            if pattern.search(line):
                assert allowed.search(line), (
                    f"'proof'/'prove' outside negation in: {line!r}"
                )


# ---------------------------------------------------------------------------
# C2PA / JUMBF byte sniffer
# ---------------------------------------------------------------------------

def _png_with_payload(path: Path, payload: bytes) -> Path:
    arr = np.zeros((4, 4, 3), dtype=np.uint8)
    PILImage.fromarray(arr, mode="RGB").save(path, format="PNG")
    # Append the payload after the PNG bytes — the engine sniffs the head
    # but we keep this explicit so the test never depends on writer
    # placement quirks.
    data = path.read_bytes()
    path.write_bytes(payload + data)
    return path


def test_c2pa_marker_is_emitted_when_jumb_byte_is_present(tmp_path: Path):
    p = tmp_path / "manifest.png"
    _png_with_payload(p, b"\x00\x00\x00\x20jumb\x00\x00\x00\x00")
    md = Metadata(path=p, format="PNG", size=(4, 4), mode="RGB")
    rows = analyze(md)
    cc = next(r for r in rows if r.label == "Content credential marker")
    assert cc.severity == SEVERITY_WORTH


def test_c2pa_marker_not_emitted_for_plain_image(tmp_path: Path):
    p = tmp_path / "plain.png"
    PILImage.fromarray(np.zeros((4, 4, 3), dtype=np.uint8), mode="RGB").save(
        p, format="PNG"
    )
    md = Metadata(path=p, format="PNG", size=(4, 4), mode="RGB")
    rows = analyze(md)
    assert "Content credential marker" not in _labels(rows)


def test_engine_does_not_open_network(monkeypatch):
    """Defensive: importing or running the engine must not touch sockets."""
    import socket

    def boom(*_a, **_k):
        raise AssertionError("engine attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", boom, raising=True)
    rows = analyze(_md(software="Tool", xmp="<x/>"))
    assert isinstance(rows, list)
