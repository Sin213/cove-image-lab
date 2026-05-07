"""Offscreen Qt smoke tests for the Human Review Notes panel.

These tests assert that the notes field exists, exposes the suggested
placeholder, and that user-typed text survives every mode/layout/source
switch and image-clear within a single session. The notes are
in-memory only — no disk I/O is exercised.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPlainTextEdit  # noqa: E402

from cove_image_lab.forensic_view import (  # noqa: E402
    NOTES_PLACEHOLDER,
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


def test_notes_field_exists(panel: ForensicsPanel) -> None:
    assert isinstance(panel.notes_edit, QPlainTextEdit)
    assert panel.notes_card is not None


def test_notes_placeholder_matches_spec(panel: ForensicsPanel) -> None:
    assert panel.notes_edit.placeholderText() == NOTES_PLACEHOLDER
    expected = (
        "Write your own observations here. "
        "Notes are local and are not an authenticity determination."
    )
    assert panel.notes_edit.placeholderText() == expected


def test_notes_set_and_read(panel: ForensicsPanel) -> None:
    panel.notes_edit.setPlainText("first observation")
    assert panel.notes_edit.toPlainText() == "first observation"


def test_notes_persist_across_mode_switch(panel: ForensicsPanel) -> None:
    panel.notes_edit.setPlainText("ELA observation")
    panel._on_mode_changed(ForensicsPanel.MODE_NOISE)
    assert panel.notes_edit.toPlainText() == "ELA observation"
    panel._on_mode_changed(ForensicsPanel.MODE_METADATA)
    assert panel.notes_edit.toPlainText() == "ELA observation"
    panel._on_mode_changed(ForensicsPanel.MODE_ELA)
    assert panel.notes_edit.toPlainText() == "ELA observation"


def test_notes_persist_across_layout_switch(panel: ForensicsPanel) -> None:
    panel.notes_edit.setPlainText("layout note")
    panel._on_layout_changed(ForensicsPanel.LAYOUT_SIDE_BY_SIDE)
    assert panel.notes_edit.toPlainText() == "layout note"
    panel._on_layout_changed(ForensicsPanel.LAYOUT_WIPE)
    assert panel.notes_edit.toPlainText() == "layout note"
    panel._on_layout_changed(ForensicsPanel.LAYOUT_SINGLE)
    assert panel.notes_edit.toPlainText() == "layout note"


def test_notes_persist_across_source_switch(panel: ForensicsPanel) -> None:
    panel.set_image("a", _rgba(1), Path("/tmp/cove_test_a.png"))
    panel.set_image("b", _rgba(2), Path("/tmp/cove_test_b.png"))
    panel.notes_edit.setPlainText("notes about A and B")
    panel._on_source_changed("b")
    assert panel.notes_edit.toPlainText() == "notes about A and B"
    panel._on_source_changed("a")
    assert panel.notes_edit.toPlainText() == "notes about A and B"


def test_notes_persist_across_image_clear(panel: ForensicsPanel) -> None:
    """Per spec: clearing images must not erase notes (no app-wide clear-session)."""
    panel.set_image("a", _rgba(3), Path("/tmp/cove_test_a.png"))
    panel.notes_edit.setPlainText("preserved across clear")
    panel.set_image("a", None, None)  # mirrors MainWindow._clear_slot path
    assert panel.notes_edit.toPlainText() == "preserved across clear"


def test_notes_field_is_readwrite(panel: ForensicsPanel) -> None:
    assert not panel.notes_edit.isReadOnly()
