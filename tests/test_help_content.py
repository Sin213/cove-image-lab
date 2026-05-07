"""Content-only tests for the in-app help.

These tests do not launch Qt. They import the section data tuples and assert
that the required topics are present and that no banned conclusive wording
slips in. The HelpDialog widget itself is exercised by the offscreen smoke
launch and by manual verification.
"""
from __future__ import annotations

import re

from cove_image_lab.help_dialog import (
    COMPARE_SECTIONS,
    FORENSICS_SECTIONS,
    REDACTION_SECTIONS,
)


def _flatten(sections):
    parts = []
    for heading, bullets in sections:
        parts.append(heading)
        parts.extend(bullets)
    return " ".join(parts).lower()


# --- required-topic coverage -----------------------------------------------

def test_compare_help_covers_threshold_and_changed_percent():
    text = _flatten(COMPARE_SECTIONS)
    assert "threshold" in text
    assert "changed %" in text
    # The cheat sheet markers.
    assert "0 — exact" in " ".join(b for _, bs in COMPARE_SECTIONS for b in bs)
    assert "100 — ignores" in " ".join(b for _, bs in COMPARE_SECTIONS for b in bs)


def test_compare_help_covers_mismatched_dimensions_rules():
    text = _flatten(COMPARE_SECTIONS)
    assert "mismatched dimensions" in text or "dimensions do not match" in text
    assert "strict diff" in text and "export" in text and "disabled" in text
    assert "scaled wipe preview never affects strict diff math" in text


def test_compare_help_lists_common_examples():
    text = _flatten(COMPARE_SECTIONS)
    for keyword in ("screenshot", "pdf", "compressed", "edited"):
        assert keyword in text, f"missing example keyword: {keyword!r}"


def test_forensics_help_covers_ela_noise_metadata():
    text = _flatten(FORENSICS_SECTIONS)
    assert "error level analysis" in text
    assert "noise map" in text
    assert "metadata" in text


def test_forensics_help_repeats_indicator_only_framing():
    text = _flatten(FORENSICS_SECTIONS)
    assert "indicators only" in text
    assert "do not prove authenticity or manipulation" in text
    # ELA and Noise Map both must include "does not prove" in some form.
    assert "ela does not prove an edit" in text
    assert "noise map does not prove an edit" in text


def test_forensics_help_explains_metadata_caveats_and_local_only_gps():
    text = _flatten(FORENSICS_SECTIONS)
    assert "metadata can be missing" in text
    assert "missing metadata does not prove anything by itself" in text
    assert "gps is displayed locally only" in text
    assert "no online lookups" in text


def test_forensics_help_documents_zoom_controls():
    text = _flatten(FORENSICS_SECTIONS)
    assert "fit" in text
    assert "100%" in text
    assert "native pixel size" in text
    assert "percentage readout" in text


def test_forensics_help_documents_human_review_notes():
    text = _flatten(FORENSICS_SECTIONS)
    assert "human review notes" in text
    assert "user-written" in text
    assert "local to the current session" in text
    assert "not an authenticity determination" in text


def test_forensics_help_documents_review_report_export():
    text = _flatten(FORENSICS_SECTIONS)
    assert "review report" in text
    assert "export review report" in text
    assert "cove_review_report.txt" in text
    assert "utf-8" in text
    assert "verbatim notes" in text
    assert "not an authenticity determination" in text


def test_forensics_help_documents_export():
    text = _flatten(FORENSICS_SECTIONS)
    assert "export result" in text
    assert "ela" in text and "noise map" in text
    assert "png" in text
    assert "cove_ela.png" in text
    assert "cove_noise_map.png" in text
    assert "visual inspection aids only" in text


def test_forensics_help_documents_layout_options():
    text = _flatten(FORENSICS_SECTIONS)
    assert "single" in text
    assert "side-by-side" in text
    assert "labeled original" in text
    assert "labeled forensic" in text
    assert "stay in sync" in text
    assert "wipe" in text
    assert "visual inspection only" in text
    assert "not a strict diff" in text


def test_forensics_help_explains_ela_and_noise_sliders():
    text = _flatten(FORENSICS_SECTIONS)
    # ELA controls
    assert "jpeg quality" in text
    assert "error scale" in text
    # Noise Map controls
    assert "scale — controls" in text
    # Both views document a brightness slider.
    assert text.count("brightness") >= 2


# --- banned wording lockdown ------------------------------------------------

_BANNED_PHRASES = [
    "fake detected",
    "real image",
    "authentic image",
    "ai generated",
    "photoshopped",
    "confidence",
    "fraud",
]


def _assert_no_banned(sections, label):
    text = _flatten(sections)
    for phrase in _BANNED_PHRASES:
        assert phrase not in text, (
            f"{label}: banned phrase {phrase!r} appears in help content"
        )


def test_compare_help_has_no_banned_wording():
    _assert_no_banned(COMPARE_SECTIONS, "COMPARE_SECTIONS")


def test_forensics_help_has_no_banned_wording():
    _assert_no_banned(FORENSICS_SECTIONS, "FORENSICS_SECTIONS")


def test_redaction_help_has_no_banned_wording():
    _assert_no_banned(REDACTION_SECTIONS, "REDACTION_SECTIONS")


def test_redaction_help_documents_manual_redaction_workflow():
    text = _flatten(REDACTION_SECTIONS)
    assert "redaction" in text
    assert "manual" in text
    assert "opaque" in text and "black" in text
    assert "original image files on disk are never modified" in text
    assert "auto-detected" in text or "not auto-saved" in text
    assert "cove_redacted_a.png" in text
    assert "cove_redacted_b.png" in text
    # Defensive: blur is explicitly NOT the chosen mechanism.
    assert "blur is not a reliable redaction" in text


def test_proof_appears_only_in_negation_contexts():
    """The word "proof" / "prove" is allowed only inside a negation phrase."""
    pattern = re.compile(r"\b(proof|prov\w*)\b", re.IGNORECASE)
    allowed_negations = re.compile(
        r"(does not\s+prov\w+|do not\s+prov\w+|not\s+proof|"
        r"never\s+prov\w+|cannot\s+prov\w+)",
        re.IGNORECASE,
    )
    for label, sections in (
        ("COMPARE_SECTIONS", COMPARE_SECTIONS),
        ("FORENSICS_SECTIONS", FORENSICS_SECTIONS),
        ("REDACTION_SECTIONS", REDACTION_SECTIONS),
    ):
        for _, bullets in sections:
            for line in bullets:
                if pattern.search(line):
                    assert allowed_negations.search(line), (
                        f"{label}: 'proof'/'prove' appears outside a negation "
                        f"context in: {line!r}"
                    )
