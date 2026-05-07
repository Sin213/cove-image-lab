# cove-image-lab

**Cove Image Lab** — offline desktop two-image comparison and inspection.
Two local images, side-by-side with synced zoom/pan, threshold-tunable diff
heatmap, draggable wipe slider, and PNG export. Zero network calls, no AI
APIs, no telemetry, no accounts.

## Install / run

```bash
pip install -e .[dev]
python -m cove_image_lab
# or, after install:
cove-image-lab
```

Requires Python 3.11+. Depends on PySide6, Pillow, and NumPy.

## Test

```bash
python -m pytest -q
```

## Using the app

### Loading images
- Drop a local image file into either slot (Image A or Image B).
- Or click **Load…** in either slot to open a native file picker.
- Supported: PNG, JPEG, BMP, TIFF, WebP, GIF (first frame).
- Grayscale, palette, and RGBA images are normalized to RGBA before
  comparison.
- The last directory you loaded from is remembered for the next session.

### Side-by-side view
- Both panes show the loaded images.
- Mouse wheel zooms both panes together around the cursor.
- Click-drag pans both panes together.

### Diff heatmap
- Computes once both images are loaded **and have matching dimensions**.
- Per-pixel max-channel absolute delta is rendered as a red-tinted heatmap.
- The diff and Export are disabled when dimensions differ — a clear inline
  message tells you the actual sizes.

### Threshold slider (0–100)
- Maps to a per-channel absolute tolerance: `tol = round(threshold * 255 /
  100)`. A pixel is "changed" iff `max(|A − B| per channel) > tol`.
- Raise the threshold to ignore JPEG / anti-aliasing noise.
- Threshold = 0: exact match required.
- Threshold = 100: tolerance is full range; nothing counts as changed.
- The slider is fast — moving it only re-runs the threshold mask against a
  cached delta, not a full subtraction.
- The last threshold value is remembered between sessions.

### Compare / wipe view
- Shows A under and B over with a draggable vertical handle.
- Click anywhere on the wipe (in fit mode) to jump the divider; or drag the
  handle directly.
- Arrow keys nudge the divider (Shift+Arrow for fine steps).
- Works even when dimensions differ — B is scaled to A's displayed size for
  preview only. The pixel-diff math is **not** affected; it still refuses
  mismatched sizes.

### Fullscreen wipe
- Click the small fullscreen icon in the Compare card header.
- Header shows the current wipe %, **Fit**, **100%**, and **Exit** controls.
- In **100%** mode, click near the divider to drag the handle, click
  elsewhere to pan.
- **Esc** exits fullscreen. **F11** toggles fullscreen ↔ maximized.

### Export
- **Export diff PNG…** writes the current heatmap (at the current threshold)
  to a PNG file you choose. The last-used save directory is remembered.

## Privacy / offline

- The app makes no network calls. Loading and exporting are filesystem-only.
- No analytics, telemetry, crash reporting, or cloud upload.
- Verify with the app running offline: every feature works identically.

## Project layout

```
src/cove_image_lab/
  app.py             # QApplication boot, theme, icon
  __main__.py        # python -m entry point
  main_window.py     # QMainWindow, drop slots, slider, summary, export
  image_view.py      # Synced QGraphicsView pair (zoom/pan)
  wipe_view.py       # Compare/wipe widget + fullscreen dialog
  image_loader.py    # PURE: path -> RGBA ndarray
  compare_engine.py  # PURE: (A, B, threshold) -> (mask, heatmap, stats)
  diff_exporter.py   # PURE: heatmap ndarray -> PNG file
  theme.py           # Cove colors, spacing, QSS

tests/
  test_compare_engine.py
  test_image_loader.py
  test_diff_exporter.py
```

The comparison engine has no Qt imports. UI imports the engine; the engine
never imports UI.

## Known limitations

- Comparing a 716×895 original against its 4× upscale (or any
  different-size pair) does **not** produce a diff. The wipe view still
  works for visual inspection, but the heatmap and Export require matching
  dimensions. Resize one of the images outside the app first.
- Multi-frame files (animated GIF, APNG) compare the first frame only.
- 16-bit-per-channel images are downcast to 8-bit during load.
- No perceptual diff (SSIM, LPIPS, ΔE). Use the threshold slider to ignore
  small noise.
- No PDF compare. Deferred.
