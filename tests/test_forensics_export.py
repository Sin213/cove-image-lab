"""Offscreen Qt smoke tests for the Forensics export-button lifecycle.

No file dialog is exercised — these tests only assert that the Export
Result button enables and disables in the right states. The export action
itself routes through ``QFileDialog.getSaveFileName`` and ``export_png``,
both of which are covered indirectly by other tests and manual QA.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from cove_image_lab.forensic_view import ForensicsPanel  # noqa: E402


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


def test_export_disabled_with_no_image(panel: ForensicsPanel) -> None:
    assert panel._mode == ForensicsPanel.MODE_ELA
    assert panel._image_a is None
    assert not panel.export_btn.isEnabled()


def test_export_enabled_for_ela_after_load(panel: ForensicsPanel) -> None:
    panel.set_image("a", _rgba(1), Path("/tmp/cove_test_a.png"))
    assert panel._mode == ForensicsPanel.MODE_ELA
    assert panel._last_view is not None
    assert panel.export_btn.isEnabled()


def test_export_enabled_for_noise_map(panel: ForensicsPanel) -> None:
    panel.set_image("a", _rgba(2), Path("/tmp/cove_test_a.png"))
    panel._on_mode_changed(ForensicsPanel.MODE_NOISE)
    assert panel.export_btn.isEnabled()
    assert panel._last_view is not None


def test_export_disabled_in_metadata_mode(panel: ForensicsPanel) -> None:
    panel.set_image("a", _rgba(3), Path("/tmp/cove_test_a.png"))
    assert panel.export_btn.isEnabled()  # ELA path enabled it
    panel._on_mode_changed(ForensicsPanel.MODE_METADATA)
    assert not panel.export_btn.isEnabled()


def test_export_disabled_after_clearing_active_source(panel: ForensicsPanel) -> None:
    panel.set_image("a", _rgba(4), Path("/tmp/cove_test_a.png"))
    assert panel.export_btn.isEnabled()
    panel.set_image("a", None, None)
    assert not panel.export_btn.isEnabled()
    assert panel._last_view is None


def test_export_default_filenames_match_spec() -> None:
    assert ForensicsPanel.EXPORT_FILENAMES[ForensicsPanel.MODE_ELA] == "cove_ela.png"
    assert (
        ForensicsPanel.EXPORT_FILENAMES[ForensicsPanel.MODE_NOISE]
        == "cove_noise_map.png"
    )


def test_export_layout_independent(panel: ForensicsPanel) -> None:
    """Changing layout (single / side-by-side / wipe) must not change export state."""
    panel.set_image("a", _rgba(5), Path("/tmp/cove_test_a.png"))
    assert panel.export_btn.isEnabled()

    panel._on_layout_changed(ForensicsPanel.LAYOUT_SIDE_BY_SIDE)
    assert panel.export_btn.isEnabled()

    panel._on_layout_changed(ForensicsPanel.LAYOUT_WIPE)
    assert panel.export_btn.isEnabled()

    panel._on_layout_changed(ForensicsPanel.LAYOUT_SINGLE)
    assert panel.export_btn.isEnabled()
