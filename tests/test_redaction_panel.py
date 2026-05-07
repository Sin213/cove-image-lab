"""Qt smoke tests for RedactionPanel.

Exercises the lifecycle, button gating, per-source rect persistence,
and the export flow with a mocked QFileDialog so we never open a
real picker.
"""
from __future__ import annotations

import errno
import os
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from PIL import Image as PILImage

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QPushButton  # noqa: E402

from cove_image_lab.redaction_view import RedactionPanel  # noqa: E402


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def panel(qapp: QApplication):
    p = RedactionPanel()
    yield p
    p.deleteLater()


def _rgba(seed: int, h: int = 32, w: int = 48) -> np.ndarray:
    rng = np.random.default_rng(seed)
    arr = rng.integers(0, 256, size=(h, w, 4), dtype=np.uint8)
    arr[..., 3] = 255
    return arr


def _load_a(panel: RedactionPanel, name: str = "alpha.jpg") -> np.ndarray:
    arr = _rgba(1)
    panel.set_image("a", arr, Path(f"/tmp/cove_test_{name}"))
    return arr


def _load_b(panel: RedactionPanel, name: str = "bravo.jpg") -> np.ndarray:
    arr = _rgba(2)
    panel.set_image("b", arr, Path(f"/tmp/cove_test_{name}"))
    return arr


# ---------- structure ----------------------------------------------------

def test_panel_constructs_with_expected_buttons(panel: RedactionPanel) -> None:
    assert isinstance(panel.undo_btn, QPushButton)
    assert isinstance(panel.clear_btn, QPushButton)
    assert isinstance(panel.export_btn, QPushButton)
    assert panel.undo_btn.text() == "Undo Redaction"
    assert panel.clear_btn.text() == "Clear Redactions"
    assert panel.export_btn.text() == "Export Redacted PNG…"


def test_initial_state_is_empty_and_disabled(panel: RedactionPanel) -> None:
    assert panel.undo_btn.isEnabled() is False
    assert panel.clear_btn.isEnabled() is False
    assert panel.export_btn.isEnabled() is False
    assert panel._rects_a == []
    assert panel._rects_b == []


# ---------- gating -------------------------------------------------------

def test_export_enabled_after_loading_a(panel: RedactionPanel) -> None:
    _load_a(panel)
    assert panel.export_btn.isEnabled() is True


def test_export_disabled_after_clearing_active_source(panel: RedactionPanel) -> None:
    _load_a(panel)
    panel.set_image("a", None, None)
    assert panel.export_btn.isEnabled() is False
    assert panel._rects_a == []


def test_clearing_inactive_source_does_not_touch_active(panel: RedactionPanel) -> None:
    _load_a(panel)
    _load_b(panel)
    # Source defaults to A, draw a rect on A
    panel.stage._rects.append((1, 2, 5, 6))
    panel.stage.rectsChanged.emit()
    assert panel._rects_a == [(1, 2, 5, 6)]
    # Now clear B (inactive). A's rects must stay.
    panel.set_image("b", None, None)
    assert panel._rects_a == [(1, 2, 5, 6)]
    assert panel._rects_b == []


# ---------- per-source rect persistence ---------------------------------

def test_rects_persist_across_source_switch(panel: RedactionPanel) -> None:
    _load_a(panel)
    _load_b(panel)
    # Append a rect on A
    panel.stage._rects.append((3, 4, 5, 6))
    panel.stage.rectsChanged.emit()
    assert panel._rects_a == [(3, 4, 5, 6)]
    # Switch to B; A's rect is saved
    panel._on_source_changed("b")
    assert panel.stage.rects() == []
    panel.stage._rects.append((7, 8, 9, 10))
    panel.stage.rectsChanged.emit()
    assert panel._rects_b == [(7, 8, 9, 10)]
    # Switch back to A; A's rect comes back
    panel._on_source_changed("a")
    assert panel.stage.rects() == [(3, 4, 5, 6)]


def test_undo_removes_only_last(panel: RedactionPanel) -> None:
    _load_a(panel)
    panel.stage._rects.extend([(0, 0, 4, 4), (10, 10, 5, 5)])
    panel.stage.rectsChanged.emit()
    panel._on_undo()
    assert panel._rects_a == [(0, 0, 4, 4)]
    panel._on_undo()
    assert panel._rects_a == []
    assert panel.undo_btn.isEnabled() is False


def test_clear_removes_all_rects_for_source(panel: RedactionPanel) -> None:
    _load_a(panel)
    _load_b(panel)
    panel.stage._rects.extend([(1, 1, 2, 2), (3, 3, 4, 4)])
    panel.stage.rectsChanged.emit()
    panel._on_source_changed("b")
    panel.stage._rects.append((5, 5, 1, 1))
    panel.stage.rectsChanged.emit()
    panel._on_source_changed("a")
    panel._on_clear()
    assert panel._rects_a == []
    # B's rects are untouched.
    panel._on_source_changed("b")
    assert panel.stage.rects() == [(5, 5, 1, 1)]


# ---------- default filenames -------------------------------------------

def test_default_filename_for_a(panel: RedactionPanel) -> None:
    _load_a(panel)
    panel._on_source_changed("a")
    assert panel._default_export_name() == "cove_redacted_a.png"


def test_default_filename_for_b(panel: RedactionPanel) -> None:
    _load_b(panel)
    panel._on_source_changed("b")
    assert panel._default_export_name() == "cove_redacted_b.png"


# ---------- save flow ---------------------------------------------------

def test_export_writes_png_with_redaction(
    panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _load_a(panel)
    panel.stage._rects.append((4, 5, 10, 8))
    panel.stage.rectsChanged.emit()
    target = tmp_path / "out.png"
    captured: dict[str, str] = {}

    def fake_dialog(parent, caption, default_path, filt):
        captured["caption"] = caption
        captured["default"] = default_path
        captured["filter"] = filt
        return (str(target), filt)

    with patch.object(QFileDialog, "getSaveFileName", side_effect=fake_dialog):
        panel._on_export()

    assert target.exists()
    assert captured["default"].endswith("cove_redacted_a.png")
    assert captured["filter"] == "PNG (*.png)"

    saved = np.array(PILImage.open(target))
    # Inside rect must be black.
    assert np.all(saved[5:13, 4:14, :3] == 0)
    # Outside rect must equal source pixels.
    mask = np.zeros(saved.shape[:2], dtype=bool)
    mask[5:13, 4:14] = True
    assert np.array_equal(saved[~mask, :3], arr[~mask, :3])


def test_export_appends_png_extension(
    panel: RedactionPanel, tmp_path: Path
) -> None:
    _load_b(panel)
    panel._on_source_changed("b")
    no_ext = tmp_path / "redacted_b_noext"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(no_ext), "PNG (*.png)"),
    ):
        panel._on_export()
    assert (tmp_path / "redacted_b_noext.png").exists()


def test_export_noop_without_image(panel: RedactionPanel, tmp_path: Path) -> None:
    target = tmp_path / "should_not_appear.png"
    opened = {"flag": False}

    def fake_dialog(*_a, **_k):
        opened["flag"] = True
        return (str(target), "PNG (*.png)")

    with patch.object(QFileDialog, "getSaveFileName", side_effect=fake_dialog):
        panel._on_export()

    assert opened["flag"] is False
    assert not target.exists()


def test_export_cancelled_writes_nothing(
    panel: RedactionPanel, tmp_path: Path
) -> None:
    _load_a(panel)
    target = tmp_path / "cancel.png"
    with patch.object(
        QFileDialog, "getSaveFileName", return_value=("", "")
    ):
        panel._on_export()
    assert not target.exists()


# ---------- privacy invariants ------------------------------------------

def test_export_does_not_mutate_source_array(
    panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _load_a(panel)
    pristine = arr.copy()
    panel.stage._rects.append((0, 0, 8, 8))
    panel.stage.rectsChanged.emit()
    target = tmp_path / "out.png"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(target), "PNG (*.png)"),
    ):
        panel._on_export()
    # The panel must not have mutated the array we handed it.
    assert np.array_equal(panel._image_a, pristine)
    assert np.array_equal(arr, pristine)


# ---------- Issue #1 regression: never overwrite a loaded source ---------

def _write_real_png(p: Path, rgba: np.ndarray) -> None:
    PILImage.fromarray(rgba).save(p, format="PNG")


def test_export_refuses_to_overwrite_image_a(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1)
    src = tmp_path / "loaded_a.png"
    _write_real_png(src, arr)
    src_bytes_before = src.read_bytes()
    panel.set_image("a", arr, src)
    panel.stage._rects.append((1, 1, 5, 5))
    panel.stage.rectsChanged.emit()
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(src), "PNG (*.png)"),
    ):
        panel._on_export()
    # Original bytes must be untouched.
    assert src.read_bytes() == src_bytes_before
    # Friendly status message is shown.
    assert "Image A" in panel.status.text()
    assert "different filename" in panel.status.text().lower()


def test_export_refuses_to_overwrite_image_b(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    a_arr = _rgba(1)
    b_arr = _rgba(2)
    src_a = tmp_path / "loaded_a.png"
    src_b = tmp_path / "loaded_b.png"
    _write_real_png(src_a, a_arr)
    _write_real_png(src_b, b_arr)
    panel.set_image("a", a_arr, src_a)
    panel.set_image("b", b_arr, src_b)
    # Active source is A; we still must refuse to overwrite B.
    panel._on_source_changed("a")
    panel.stage._rects.append((0, 0, 4, 4))
    panel.stage.rectsChanged.emit()
    src_b_bytes_before = src_b.read_bytes()
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(src_b), "PNG (*.png)"),
    ):
        panel._on_export()
    assert src_b.read_bytes() == src_b_bytes_before
    assert "Image B" in panel.status.text()


def test_export_refuses_after_png_suffix_normalization(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1)
    src = tmp_path / "loaded.png"
    _write_real_png(src, arr)
    src_bytes_before = src.read_bytes()
    panel.set_image("a", arr, src)
    panel.stage._rects.append((1, 1, 4, 4))
    panel.stage.rectsChanged.emit()
    # User types the source path WITHOUT the .png extension; the panel
    # appends ".png" and the result equals the source. Must still be blocked.
    typed = str(src.with_suffix(""))
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(typed, "PNG (*.png)"),
    ):
        panel._on_export()
    assert src.read_bytes() == src_bytes_before
    assert "Image A" in panel.status.text()


def _make_hardlink_or_skip(src: Path, dst: Path) -> None:
    """Create ``dst`` as a hard link to ``src`` or pytest.skip cleanly.

    Hard-link support is filesystem-dependent (FAT32, some network mounts,
    and certain Windows configurations refuse). Skipping instead of failing
    keeps CI green on those filesystems while still exercising the guard
    everywhere POSIX-style links work.
    """
    if not hasattr(os, "link"):
        pytest.skip("os.link not available on this platform")
    try:
        os.link(src, dst)
    except (OSError, NotImplementedError) as e:
        # EPERM/EXDEV/ENOSYS all show up depending on the filesystem.
        skip_reasons = {errno.EPERM, errno.EXDEV, errno.ENOSYS, errno.EACCES}
        if isinstance(e, OSError) and e.errno not in skip_reasons:
            raise
        pytest.skip(f"hard links not supported on this filesystem: {e}")


def test_export_refuses_to_overwrite_hardlink_to_image_a(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1)
    src = tmp_path / "loaded_a.png"
    _write_real_png(src, arr)
    src_bytes_before = src.read_bytes()
    panel.set_image("a", arr, src)
    panel.stage._rects.append((1, 1, 5, 5))
    panel.stage.rectsChanged.emit()

    alias = tmp_path / "alias_a.png"
    _make_hardlink_or_skip(src, alias)
    # Sanity: the alias and the original share an inode but have different paths.
    assert alias.samefile(src)
    assert alias.resolve() != src.resolve() or alias != src

    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(alias), "PNG (*.png)"),
    ):
        panel._on_export()

    # Either path reads the original bytes — the export must have been blocked.
    assert src.read_bytes() == src_bytes_before
    assert alias.read_bytes() == src_bytes_before
    assert "Image A" in panel.status.text()
    assert "different filename" in panel.status.text().lower()


def test_export_refuses_to_overwrite_hardlink_to_image_b(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    a_arr = _rgba(1)
    b_arr = _rgba(2)
    src_a = tmp_path / "loaded_a.png"
    src_b = tmp_path / "loaded_b.png"
    _write_real_png(src_a, a_arr)
    _write_real_png(src_b, b_arr)
    panel.set_image("a", a_arr, src_a)
    panel.set_image("b", b_arr, src_b)
    panel._on_source_changed("a")  # active = A; export must still protect B
    panel.stage._rects.append((0, 0, 4, 4))
    panel.stage.rectsChanged.emit()

    alias_b = tmp_path / "alias_b.png"
    _make_hardlink_or_skip(src_b, alias_b)
    src_b_bytes_before = src_b.read_bytes()

    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(alias_b), "PNG (*.png)"),
    ):
        panel._on_export()

    assert src_b.read_bytes() == src_b_bytes_before
    assert alias_b.read_bytes() == src_b_bytes_before
    assert "Image B" in panel.status.text()


def test_export_to_nonexistent_target_still_works(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    """Regression: samefile raises FileNotFoundError when the export path
    does not exist yet. The fallback resolved-path comparison must let
    the export proceed in that (very common) case.
    """
    arr = _rgba(1)
    src = tmp_path / "loaded.png"
    _write_real_png(src, arr)
    panel.set_image("a", arr, src)
    panel.stage._rects.append((1, 1, 4, 4))
    panel.stage.rectsChanged.emit()
    new_target = tmp_path / "redacted_brand_new.png"
    assert not new_target.exists()
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(new_target), "PNG (*.png)"),
    ):
        panel._on_export()
    assert new_target.exists()


def test_export_with_different_path_still_works(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1)
    src = tmp_path / "loaded.png"
    _write_real_png(src, arr)
    panel.set_image("a", arr, src)
    panel.stage._rects.append((2, 2, 4, 4))
    panel.stage.rectsChanged.emit()
    target = tmp_path / "redacted_copy.png"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(target), "PNG (*.png)"),
    ):
        panel._on_export()
    assert target.exists()
    # Different file from the source.
    assert target.resolve() != src.resolve()


# ---------- Issue #2 regression: half-open widget→image mapping ---------

def _send(stage, evt_type, qp, btn, btns):
    QApplication.sendEvent(
        stage,
        QMouseEvent(evt_type, QPointF(qp), btn, btns, Qt.NoModifier),
    )


def _drag(stage, start: QPoint, end: QPoint) -> None:
    _send(stage, QEvent.MouseButtonPress, start, Qt.LeftButton, Qt.LeftButton)
    _send(stage, QEvent.MouseMove, end, Qt.NoButton, Qt.LeftButton)
    _send(stage, QEvent.MouseButtonRelease, end, Qt.LeftButton, Qt.NoButton)


def test_widget_to_image_inclusive_right_edge_returns_iw(
    qapp: QApplication, panel: RedactionPanel
) -> None:
    arr = _rgba(1, h=10, w=20)
    panel.set_image("a", arr, Path("/tmp/x.jpg"))
    panel.stage.resize(400, 200)
    qapp.processEvents()
    target = panel.stage._image_rect()
    assert not target.isEmpty()
    pt = QPoint(target.right(), target.bottom())
    assert panel.stage._widget_to_image(pt) == (20, 10)


def test_widget_to_image_top_left_returns_zero(
    qapp: QApplication, panel: RedactionPanel
) -> None:
    arr = _rgba(1, h=10, w=20)
    panel.set_image("a", arr, Path("/tmp/x.jpg"))
    panel.stage.resize(400, 200)
    qapp.processEvents()
    target = panel.stage._image_rect()
    pt = QPoint(target.left(), target.top())
    assert panel.stage._widget_to_image(pt) == (0, 0)


def test_drag_to_right_edge_redacts_final_column(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1, h=10, w=20)
    panel.set_image("a", arr, Path("/tmp/x.jpg"))
    panel.stage.resize(400, 200)
    qapp.processEvents()
    target = panel.stage._image_rect()
    _drag(
        panel.stage,
        QPoint(target.left(), target.top()),
        QPoint(target.right(), target.bottom()),
    )
    rects = panel.stage.rects()
    assert rects, "drag must produce a rectangle"
    x, y, w, h = rects[0]
    # Half-open rect must reach iw and ih so the renderer covers the last
    # column and last row via [x:x+w] / [y:y+h] slicing.
    assert (x, y, w, h) == (0, 0, 20, 10)

    # Pixel-level proof: render and check.
    out_path = tmp_path / "edge.png"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(out_path), "PNG (*.png)"),
    ):
        panel._on_export()
    saved = np.array(PILImage.open(out_path))
    # Final column and final row are entirely black.
    assert np.all(saved[:, -1, :3] == 0)
    assert np.all(saved[-1, :, :3] == 0)


def test_drag_to_bottom_edge_redacts_final_row(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1, h=8, w=12)
    panel.set_image("a", arr, Path("/tmp/x.jpg"))
    panel.stage.resize(360, 240)
    qapp.processEvents()
    target = panel.stage._image_rect()
    # Drag from the vertical midpoint to the inclusive bottom edge so the
    # release lands on target.bottom(); confirms that the inclusive edge
    # maps to ih (and so the final image row gets covered).
    _drag(
        panel.stage,
        QPoint(target.left(), target.top() + target.height() // 2),
        QPoint(target.right(), target.bottom()),
    )
    rects = panel.stage.rects()
    assert rects
    x, y, w, h = rects[0]
    # The drag must reach iw on the right and ih on the bottom.
    assert x + w == 12
    assert y + h == 8
    out_path = tmp_path / "bottom.png"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(out_path), "PNG (*.png)"),
    ):
        panel._on_export()
    saved = np.array(PILImage.open(out_path))
    # The last row is fully black.
    assert np.all(saved[-1, :, :3] == 0)


def test_full_image_drag_blacks_out_every_pixel(
    qapp: QApplication, panel: RedactionPanel, tmp_path: Path
) -> None:
    arr = _rgba(1, h=10, w=14)
    panel.set_image("a", arr, Path("/tmp/x.jpg"))
    panel.stage.resize(420, 300)
    qapp.processEvents()
    target = panel.stage._image_rect()
    _drag(
        panel.stage,
        QPoint(target.left(), target.top()),
        QPoint(target.right(), target.bottom()),
    )
    out_path = tmp_path / "full.png"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(out_path), "PNG (*.png)"),
    ):
        panel._on_export()
    saved = np.array(PILImage.open(out_path))
    assert np.all(saved[..., :3] == 0)


def test_export_does_not_persist_metadata_about_rects(
    panel: RedactionPanel, tmp_path: Path
) -> None:
    """Sanity: exported PNG file bytes should not contain a tag/marker
    string that would reveal redaction details. We ensure no obvious
    custom marker leaked from our code."""
    _load_a(panel)
    panel.stage._rects.append((1, 1, 4, 4))
    panel.stage.rectsChanged.emit()
    target = tmp_path / "out.png"
    with patch.object(
        QFileDialog,
        "getSaveFileName",
        return_value=(str(target), "PNG (*.png)"),
    ):
        panel._on_export()
    blob = target.read_bytes()
    # No app-name / tool-name leakage in PNG bytes.
    for token in (b"cove_image_lab", b"RedactionPanel", b"redaction_view"):
        assert token not in blob, f"unexpected marker {token!r} in exported PNG"
