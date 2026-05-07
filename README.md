# cove-image-lab

**Cove Image Lab** — offline desktop two-image comparison and inspection.
Three tabs:

- **Compare** — synced side-by-side view, threshold-tunable strict pixel
  diff, draggable wipe, fullscreen wipe, diff PNG export.
- **Forensics** — single-image visual inspection: Error Level Analysis
  (ELA), Noise Map, and Metadata, with Single / Side-by-side / Wipe
  layouts, Human Review Notes, Export Result PNG, and a local plain-text
  Review Report. Visual inspection only — not an authenticity
  determination.
- **Redaction** — draw opaque black rectangles over private regions on
  Image A or Image B, then export a redacted PNG. Manual only; nothing is
  auto-detected; original files on disk are never modified.

Zero network calls, no AI APIs, no telemetry, no accounts. Everything is
local.

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

## Forensics tab

The Forensics tab inspects **one** loaded image (Image A or Image B). All
views are visual indicators only and do not prove authenticity or
manipulation. Compression, screenshots, recompression, sharp edges, line
art, and repeated resaves can all create suspicious-looking patterns.

### Views
- **Error Level Analysis (ELA)** — recompresses the image internally as
  JPEG and shows where the recompressed copy differs from the original.
  Sliders: JPEG quality, error scale, brightness.
- **Noise Map** — emphasizes fine detail and noise patterns by suppressing
  smoother content. Sliders: scale, brightness.
- **Metadata** — format, size, mode, camera/software tags, dates, GPS,
  XMP, and PNG text when present. GPS is displayed locally only; no
  online lookups. Missing or stripped metadata does not prove anything.

### Layout
- **Single** — the forensic view alone.
- **Side-by-side** — Original on the left, Forensic on the right; mouse
  wheel zoom and drag-pan stay in sync between panes.
- **Wipe** — overlay the source and the forensic view in one frame; drag
  the divider to reveal more of either side. Captioned "Visual inspection
  only — not a strict diff."

The layout choice does not change ELA or Noise Map calculations. The
layout toggle is hidden in Metadata view.

### Zoom (ELA / Noise Map)
- **Fit** scales the view to fill the area; **100%** shows native pixel
  size for close inspection.
- Mouse wheel zooms; drag pans when zoomed in. A percentage readout
  shows the current on-screen scale.

### Human Review Notes
- A free-text box for your own observations during inspection.
- Notes are user-written; the app never adds, edits, or interprets them.
- Notes are not auto-saved and are not persisted between app runs.
  They are written to disk only when you explicitly use **Export Review
  Report** below.
- Notes are not an authenticity determination.

### Exporting forensic results
- **Export Result** writes the current ELA or Noise Map view as a PNG.
  Default filenames are `cove_ela.png` and `cove_noise_map.png`.
- The button is disabled in Metadata view (no generated image).
- Exported PNGs are visual inspection aids only and do not prove
  authenticity or manipulation.

### Exporting a Review Report
- **Export Review Report** writes a local plain-text UTF-8 file
  summarizing the active source, view mode, layout, loaded filenames,
  and your verbatim notes. Default filename is `cove_review_report.txt`.
- The button is disabled until at least one image is loaded.
- Review reports are visual inspection aids only and are not an
  authenticity determination. Nothing is auto-saved.

## Redaction tab

The Redaction tab covers private regions on a chosen source before you
share it. It is **manual only** — nothing is auto-detected.

- Pick **Image A** or **Image B** with the Source toggle. Each source
  keeps its own list of redaction rectangles for the session.
- Click and drag on the preview to draw an opaque black rectangle.
- **Undo Redaction** removes the most recent rectangle; **Clear
  Redactions** removes every rectangle on the active source. Both
  buttons are disabled until at least one rectangle exists.
- **Export Redacted PNG…** saves a new PNG with the rectangles burned in
  as solid opaque black pixels (not blurred — blur is not a reliable
  redaction). Default filenames are `cove_redacted_a.png` and
  `cove_redacted_b.png`.
- The export is destructive in the **exported copy only**. Original
  image files on disk are never modified, and the export is blocked from
  overwriting either loaded source — including hard-link aliases.
- Redaction rectangles are not saved between app runs; nothing is
  auto-saved.

## Privacy / offline

- The app makes no network calls. Loading and exporting are filesystem-only.
- No analytics, telemetry, crash reporting, or cloud upload.
- No AI, OCR, or remote inference. Forensics views and Redaction are
  fully local computations.
- Every export writes a new file at the path you choose in the save
  dialog; nothing is auto-saved. Only the **Redaction** export actively
  guards against overwriting a loaded source file (including hard-link
  aliases). For **Compare** and **Forensics** exports, the app does not
  block you from picking a loaded source's own path in the save dialog
  — if you do, that file will be overwritten, so choose a different
  filename to keep originals intact.
- Verify with the app running offline: every feature works identically.

## Build a local Linux distributable

For a self-contained one-folder bundle (Python + Qt + assets):

```bash
./packaging/build-linux.sh
./dist/cove-image-lab/cove-image-lab
```

See [`packaging/README.md`](packaging/README.md) for spec details, the
optional `.desktop` launcher template, and environment overrides.
Windows and macOS packaging are not yet scaffolded.

## Project layout

```
src/cove_image_lab/
  __init__.py            # version
  __main__.py            # python -m entry point
  app.py                 # QApplication boot, theme, icon
  main_window.py         # QMainWindow, drop slots, tabs, slider, export
  image_loader.py        # PURE: path -> RGBA ndarray
  image_view.py          # Synced QGraphicsView pair (zoom/pan)
  wipe_view.py           # Compare/wipe widget + fullscreen dialog
  compare_engine.py      # PURE: (A, B, threshold) -> (mask, heatmap, stats)
  diff_exporter.py       # PURE: heatmap ndarray -> PNG file
  forensic_engine.py     # PURE: ELA / Noise Map computations
  forensic_view.py       # Forensics tab UI: views, layout, notes, exports
  metadata_reader.py     # PURE: image file -> structured metadata dict
  redaction_view.py      # Redaction tab UI + redacted-PNG render/export
  help_dialog.py         # In-app "How to use" dialogs (data + widget)
  theme.py               # Cove colors, spacing, QSS
  assets/
    cove_icon.png        # Window/app icon (shipped as package data)

tests/
  test_compare_engine.py
  test_diff_exporter.py
  test_forensic_engine.py
  test_forensics_export.py
  test_forensics_notes.py
  test_forensics_review_report.py
  test_help_content.py
  test_image_loader.py
  test_metadata_reader.py
  test_redaction_panel.py
  test_redaction_render.py

packaging/
  build-linux.sh           # one-folder Linux build wrapper
  cove-image-lab.spec      # PyInstaller spec (uses repo-relative paths)
  launcher.py              # absolute-import entry for the frozen binary
  cove-image-lab.desktop   # .desktop launcher template
  README.md                # build instructions + output layout
```

The comparison engine, forensic engine, image loader, metadata reader, and
diff exporter have no Qt imports. UI imports the engines; the engines
never import UI.

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
