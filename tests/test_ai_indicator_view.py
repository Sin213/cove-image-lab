"""Qt smoke tests for AIIndicatorView.

Covers empty state, A/B switching, clearing, the disclaimer label, and
banned-wording rules on rendered indicator content. The engine itself is
unit-tested in ``test_ai_indicator_engine.py``.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PILImage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel  # noqa: E402

from cove_image_lab.ai_indicator_view import (  # noqa: E402
    DISCLAIMER,
    EMPTY_HINT,
    AIIndicatorView,
)


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def view(qapp: QApplication):
    v = AIIndicatorView()
    yield v
    v.deleteLater()


def _rgba(seed: int, h: int = 8, w: int = 8) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(h, w, 4), dtype=np.uint8)
    arr[..., 3] = 255
    return arr


def _save_jpeg_with_software(path: Path, software: str) -> Path:
    arr = np.full((6, 6, 3), 200, dtype=np.uint8)
    img = PILImage.fromarray(arr, mode="RGB")
    exif = img.getexif()
    # 0x0131 = Software tag.
    exif[0x0131] = software
    img.save(path, format="JPEG", exif=exif.tobytes(), quality=92)
    return path


def _save_plain_png(path: Path) -> Path:
    arr = np.zeros((6, 6, 3), dtype=np.uint8)
    PILImage.fromarray(arr, mode="RGB").save(path, format="PNG")
    return path


def _all_label_text(view: AIIndicatorView) -> str:
    return " ".join(
        w.text() for w in view.findChildren(QLabel) if w.text()
    )


# ---------- structure ---------------------------------------------------

def test_disclaimer_is_visible_at_construction(view: AIIndicatorView) -> None:
    assert DISCLAIMER in _all_label_text(view)


def test_initial_state_is_empty_message(view: AIIndicatorView) -> None:
    assert EMPTY_HINT in _all_label_text(view)


def test_help_button_is_present(view: AIIndicatorView) -> None:
    assert view.help_btn.text() == "How to use"


# ---------- A/B lifecycle ----------------------------------------------

def test_loading_a_populates_indicators(view: AIIndicatorView, tmp_path: Path) -> None:
    p = _save_jpeg_with_software(tmp_path / "a.jpg", "ToolUnderTest 9")
    view.set_image("a", _rgba(1), p)
    text = _all_label_text(view)
    assert EMPTY_HINT not in text
    assert "ToolUnderTest 9" in text
    assert "Software / editor tag" in text


def test_switching_to_b_with_only_a_loaded_shows_empty(
    view: AIIndicatorView, tmp_path: Path
) -> None:
    p = _save_jpeg_with_software(tmp_path / "a.jpg", "ToolUnderTest 9")
    view.set_image("a", _rgba(1), p)
    view._on_source_changed("b")
    text = _all_label_text(view)
    assert EMPTY_HINT in text
    assert "ToolUnderTest 9" not in text


def test_switching_back_to_a_restores_indicators(
    view: AIIndicatorView, tmp_path: Path
) -> None:
    p = _save_jpeg_with_software(tmp_path / "a.jpg", "ToolUnderTest 9")
    view.set_image("a", _rgba(1), p)
    view._on_source_changed("b")
    view._on_source_changed("a")
    assert "ToolUnderTest 9" in _all_label_text(view)


def test_loading_b_only_keeps_a_empty(view: AIIndicatorView, tmp_path: Path) -> None:
    pb = _save_jpeg_with_software(tmp_path / "b.jpg", "BTool 1")
    view.set_image("b", _rgba(2), pb)
    # A is the default active source — should still show empty hint.
    assert EMPTY_HINT in _all_label_text(view)
    view._on_source_changed("b")
    assert "BTool 1" in _all_label_text(view)


def test_clearing_active_source_returns_to_empty(
    view: AIIndicatorView, tmp_path: Path
) -> None:
    p = _save_jpeg_with_software(tmp_path / "a.jpg", "ToolUnderTest 9")
    view.set_image("a", _rgba(1), p)
    view.set_image("a", None, None)
    assert EMPTY_HINT in _all_label_text(view)


def test_plain_png_shows_no_metadata_row(
    view: AIIndicatorView, tmp_path: Path
) -> None:
    p = _save_plain_png(tmp_path / "plain.png")
    view.set_image("a", _rgba(1), p)
    text = _all_label_text(view)
    assert "No metadata at all" in text
    # Must not imply a verdict.
    assert "fake" not in text.lower()
    assert "deepfake" not in text.lower()


def test_corrupt_file_does_not_crash(view: AIIndicatorView, tmp_path: Path) -> None:
    p = tmp_path / "broken.png"
    p.write_bytes(b"this is not a real image")
    view.set_image("a", _rgba(1), p)
    text = _all_label_text(view)
    assert "Could not read image" in text


# ---------- wording lockdown -------------------------------------------

_BANNED = (
    "fake detected",
    "real image",
    "authentic image",
    "ai generated",
    "ai-generated",
    "deepfake",
    "manipulated image",
    "tampered",
    "confidence",
    "verdict",
)


def test_no_banned_wording_in_empty_state(view: AIIndicatorView) -> None:
    text = _all_label_text(view).lower()
    for phrase in _BANNED:
        assert phrase not in text, f"banned phrase {phrase!r} in empty-state UI"


def test_no_banned_wording_with_indicators(
    view: AIIndicatorView, tmp_path: Path
) -> None:
    p = _save_jpeg_with_software(tmp_path / "a.jpg", "ToolUnderTest 9")
    view.set_image("a", _rgba(1), p)
    text = _all_label_text(view).lower()
    for phrase in _BANNED:
        assert phrase not in text, f"banned phrase {phrase!r} in rendered indicators"


def test_proof_words_only_appear_in_negation(
    view: AIIndicatorView, tmp_path: Path
) -> None:
    p = _save_jpeg_with_software(tmp_path / "a.jpg", "ToolUnderTest 9")
    view.set_image("a", _rgba(1), p)
    text = _all_label_text(view)
    pattern = re.compile(r"\b(proof|prov\w*)\b", re.IGNORECASE)
    allowed = re.compile(
        r"(does not\s+prov\w+|do not\s+prov\w+|not\s+proof|"
        r"never\s+prov\w+|cannot\s+prov\w+)",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        if pattern.search(line) and not allowed.search(line):
            pytest.fail(f"'proof/prov*' outside negation: {line!r}")
