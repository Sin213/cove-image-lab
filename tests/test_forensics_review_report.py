"""Tests for ForensicsPanel.build_review_report and the report-export button.

Builder tests are pure (no Qt dialog). One save-flow test mocks
QFileDialog.getSaveFileName so the file write itself is exercised
without a real picker.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton  # noqa: E402

from cove_image_lab.forensic_view import (  # noqa: E402
    REVIEW_REPORT_CAUTION,
    REVIEW_REPORT_DEFAULT_NAME,
    REVIEW_REPORT_TITLE,
    ForensicsPanel,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp: QApplication) -> ForensicsPanel:
    p = ForensicsPanel()
    yield p
    p.deleteLater()


def _rgba(seed: int, h: int = 32, w: int = 48) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(h, w, 4), dtype=np.uint8)
    arr[..., 3] = 255
    return arr


def _load_a(panel: ForensicsPanel, name: str = "alpha.jpg") -> Path:
    p = Path(f"/tmp/cove_test_{name}")
    panel.set_image("a", _rgba(1), p)
    return p


def _load_b(panel: ForensicsPanel, name: str = "bravo.jpg") -> Path:
    p = Path(f"/tmp/cove_test_{name}")
    panel.set_image("b", _rgba(2), p)
    return p


# ---------- button gating --------------------------------------------------

def test_button_exists_with_correct_label(panel: ForensicsPanel) -> None:
    assert isinstance(panel.export_report_btn, QPushButton)
    assert panel.export_report_btn.text() == "Export Review Report"


def test_button_disabled_when_no_image(panel: ForensicsPanel) -> None:
    assert panel.export_report_btn.isEnabled() is False


def test_button_enabled_after_loading_a(panel: ForensicsPanel) -> None:
    _load_a(panel)
    assert panel.export_report_btn.isEnabled() is True


def test_button_enabled_when_only_b_loaded(panel: ForensicsPanel) -> None:
    _load_b(panel)
    assert panel.export_report_btn.isEnabled() is True


def test_button_disabled_after_clearing_all(panel: ForensicsPanel) -> None:
    _load_a(panel)
    panel.set_image("a", None, None)
    assert panel.export_report_btn.isEnabled() is False


# ---------- builder content ------------------------------------------------

FIXED_NOW = datetime(2026, 5, 7, 12, 0, 0)


def test_report_includes_title_and_caution(panel: ForensicsPanel) -> None:
    _load_a(panel)
    text = panel.build_review_report(now=FIXED_NOW)
    assert REVIEW_REPORT_TITLE in text
    assert REVIEW_REPORT_CAUTION in text
    assert "2026-05-07 12:00:00" in text


def test_report_includes_image_filenames_not_full_paths(panel: ForensicsPanel) -> None:
    pa = _load_a(panel, "imgA.jpg")
    text = panel.build_review_report(now=FIXED_NOW)
    assert f"Image A: {pa.name}" in text       # filename present
    assert f"Image A: {pa}" not in text        # full path absent
    assert str(pa.parent) not in text          # parent dir absent
    assert "Image B: (not loaded)" in text


def test_report_marks_missing_a_as_not_loaded(panel: ForensicsPanel) -> None:
    _load_b(panel, "imgB.jpg")
    text = panel.build_review_report(now=FIXED_NOW)
    assert "Image A: (not loaded)" in text
    assert "Image B: cove_test_imgB.jpg" in text
    assert "/tmp/cove_test_imgB.jpg" not in text


def test_report_does_not_leak_parent_directory(panel: ForensicsPanel) -> None:
    """Privacy regression: shared reports must not disclose folder structure."""
    pa = Path("/home/someuser/Clients/Acme/case-7/photo.jpg")
    pb = Path("/var/private/projects/sensitive/B.png")
    panel.set_image("a", _rgba(1), pa)
    panel.set_image("b", _rgba(2), pb)
    text = panel.build_review_report(now=FIXED_NOW)
    # Filenames present
    assert "Image A: photo.jpg" in text
    assert "Image B: B.png" in text
    # No parent-directory or username leakage
    for fragment in (
        "/home/", "someuser", "Clients", "Acme", "case-7",
        "/var/", "private", "projects", "sensitive",
    ):
        assert fragment not in text, (
            f"privacy leak: report contains parent-path fragment {fragment!r}"
        )


def test_report_reflects_active_source_b(panel: ForensicsPanel) -> None:
    _load_a(panel)
    _load_b(panel)
    panel._on_source_changed("b")
    text = panel.build_review_report(now=FIXED_NOW)
    assert "Active source: B" in text


def test_report_reflects_view_modes(panel: ForensicsPanel) -> None:
    _load_a(panel)
    panel._on_mode_changed(ForensicsPanel.MODE_NOISE)
    assert "View mode: Noise Map" in panel.build_review_report(now=FIXED_NOW)
    panel._on_mode_changed(ForensicsPanel.MODE_METADATA)
    assert "View mode: Metadata" in panel.build_review_report(now=FIXED_NOW)
    panel._on_mode_changed(ForensicsPanel.MODE_ELA)
    assert "View mode: Error Level Analysis" in panel.build_review_report(now=FIXED_NOW)


def test_report_reflects_layouts(panel: ForensicsPanel) -> None:
    _load_a(panel)
    panel._on_layout_changed(ForensicsPanel.LAYOUT_SIDE_BY_SIDE)
    assert "Layout: Side-by-side" in panel.build_review_report(now=FIXED_NOW)
    panel._on_layout_changed(ForensicsPanel.LAYOUT_WIPE)
    assert "Layout: Wipe" in panel.build_review_report(now=FIXED_NOW)
    panel._on_layout_changed(ForensicsPanel.LAYOUT_SINGLE)
    assert "Layout: Single" in panel.build_review_report(now=FIXED_NOW)


def test_report_includes_user_notes_verbatim(panel: ForensicsPanel) -> None:
    _load_a(panel)
    notes = "Edges look crisp on the patch corners.\nGreen patch warrants a closer look."
    panel.notes_edit.setPlainText(notes)
    text = panel.build_review_report(now=FIXED_NOW)
    assert notes in text


def test_report_marks_empty_notes_as_none(panel: ForensicsPanel) -> None:
    _load_a(panel)
    panel.notes_edit.setPlainText("")
    text = panel.build_review_report(now=FIXED_NOW)
    assert "Human Review Notes:" in text
    assert "(none)" in text


# ---------- wording sweep --------------------------------------------------

# Words that must NOT appear in app-generated report text. Notes are
# user-written and excluded from this sweep — the test sets notes empty.
_BANNED_REPORT_WORDS = [
    "fake",
    "fraud",
    "tampered",
    "manipulated",
    "photoshopped",
    "conclusive",
    "definitive",
    "confidence",
    "proof",
    "proven",
    "verdict",
]


def test_app_generated_report_text_lacks_banned_words(panel: ForensicsPanel) -> None:
    _load_a(panel)
    _load_b(panel)
    panel.notes_edit.setPlainText("")  # only app-generated text remains
    panel._on_mode_changed(ForensicsPanel.MODE_ELA)
    panel._on_layout_changed(ForensicsPanel.LAYOUT_SIDE_BY_SIDE)
    text = panel.build_review_report(now=FIXED_NOW).lower()
    for word in _BANNED_REPORT_WORDS:
        assert word not in text, f"banned word {word!r} found in report"


def test_authenticity_appears_only_in_negation_phrase(panel: ForensicsPanel) -> None:
    _load_a(panel)
    panel.notes_edit.setPlainText("")
    text = panel.build_review_report(now=FIXED_NOW)
    matches = [m.start() for m in re.finditer(r"authenticity", text, re.IGNORECASE)]
    assert matches, "expected the disclaimer to mention authenticity"
    for idx in matches:
        snippet = text[max(0, idx - 30):idx + 50].lower()
        assert "is not an authenticity determination" in snippet, (
            f"authenticity used outside the allowed negation phrase: {snippet!r}"
        )


# ---------- save flow (mocked dialog) --------------------------------------

def test_save_flow_writes_utf8_and_uses_default_filename(
    panel: ForensicsPanel, tmp_path: Path
) -> None:
    _load_a(panel)
    panel.notes_edit.setPlainText("Café notes — résumé bullets ✓")
    target = tmp_path / "my_report.txt"
    captured: dict[str, str] = {}

    def fake_dialog(parent, caption, default_path, filt):
        captured["caption"] = caption
        captured["default"] = default_path
        captured["filter"] = filt
        return (str(target), filt)

    with patch.object(QFileDialog, "getSaveFileName", side_effect=fake_dialog):
        panel._on_export_report()

    assert target.exists()
    assert target.stat().st_size > 0
    assert captured["default"].endswith(REVIEW_REPORT_DEFAULT_NAME)
    assert captured["filter"] == "Text files (*.txt)"
    body = target.read_text(encoding="utf-8")
    assert "Café notes — résumé bullets ✓" in body
    assert REVIEW_REPORT_CAUTION in body


def test_save_flow_appends_txt_extension(
    panel: ForensicsPanel, tmp_path: Path
) -> None:
    _load_a(panel)
    target_no_ext = tmp_path / "report_without_ext"

    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(target_no_ext), "Text files (*.txt)"),
    ):
        panel._on_export_report()

    assert (tmp_path / "report_without_ext.txt").exists()


def test_save_flow_noop_without_image(panel: ForensicsPanel, tmp_path: Path) -> None:
    target = tmp_path / "should_not_be_written.txt"
    called = {"opened": False}

    def fake_dialog(*_a, **_k):
        called["opened"] = True
        return (str(target), "Text files (*.txt)")

    with patch.object(QFileDialog, "getSaveFileName", side_effect=fake_dialog):
        panel._on_export_report()

    assert called["opened"] is False
    assert not target.exists()


def test_save_flow_cancelled_writes_nothing(
    panel: ForensicsPanel, tmp_path: Path
) -> None:
    _load_a(panel)
    target = tmp_path / "cancelled.txt"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=("", ""),
    ):
        panel._on_export_report()
    assert not target.exists()
