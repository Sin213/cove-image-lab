# Packaging

Local-only build scaffold for **Cove Image Lab**. Linux-first; no CI, no
installer, no auto-update, no telemetry. Windows and macOS are not yet
scaffolded.

## One-time environment setup (manual)

The build script itself does **not** install anything — it expects a
provisioned Python environment. Run these commands once on a machine
with network access to set up the default build venv at `build/.venv/`:

```bash
python3 -m venv build/.venv
build/.venv/bin/python -m pip install -e .
build/.venv/bin/python -m pip install "pyinstaller>=6"
```

You can use any Python ≥ 3.11 and any venv location — see
**Environment overrides** below.

To upgrade pip first (optional):

```bash
build/.venv/bin/python -m pip install --upgrade pip
```

These commands are explicit and manual on purpose, so the default build
path stays offline-reproducible. If you skip this step, the build
script will exit nonzero with a friendly message describing what's
missing.

## Build a Linux one-folder bundle

Once the environment is provisioned:

```bash
./packaging/build-linux.sh
```

What the script does:

1. Resolves a Python interpreter (see priority order below).
2. Verifies that `cove_image_lab` and `PyInstaller` are importable from
   it. If either is missing, prints setup help and exits nonzero.
3. Runs PyInstaller against `packaging/cove-image-lab.spec`.
4. Drops the bundle at `dist/cove-image-lab/`.

Run the built app:

```bash
./dist/cove-image-lab/cove-image-lab
```

Both `build/` and `dist/` are gitignored, so the script never dirties
the working tree.

### Environment overrides

The script picks the Python interpreter in this order:

1. `$PYTHON`               — exact path you set
2. `$VENV/bin/python`      — when `VENV` is set
3. `build/.venv/bin/python` — the default scaffold venv (above)
4. `python3` on `$PATH`    — fallback

```bash
PYTHON=/usr/bin/python3.12 ./packaging/build-linux.sh    # pick a Python
VENV=/some/where/.venv     ./packaging/build-linux.sh    # custom venv
```

## What the spec does

`cove-image-lab.spec` is a hand-written PyInstaller spec. It uses
`SPECPATH` to derive `PROJECT_ROOT`, then bundles:

- `packaging/launcher.py` as the frozen entry point
- `src/cove_image_lab/assets/cove_icon.png` at
  `cove_image_lab/assets/cove_icon.png` inside the bundle, which is
  exactly where `cove_image_lab.app._icon_path()` looks via
  `importlib.resources.files("cove_image_lab")`

`packaging/launcher.py` is needed because
`src/cove_image_lab/__main__.py` uses a relative import
(`from .app import main`) — correct for `python -m cove_image_lab`, but
PyInstaller invokes the entry script as top-level `__main__` where
relative imports do not work.

## Output layout

```
dist/cove-image-lab/
├── cove-image-lab            # ELF launcher
└── _internal/                # frozen Python + Qt + PIL + NumPy + assets
    ├── cove_image_lab/
    │   └── assets/
    │       └── cove_icon.png
    ├── PySide6/
    ├── shiboken6/
    ├── PIL/
    └── numpy/
```

Bundle is roughly 270 MB on disk (most of which is PySide6 / Qt).

## Optional: install a `.desktop` launcher

`cove-image-lab.desktop` in this directory is a **template**. Two fields
need to be replaced with absolute paths on your machine:

- `Exec={EXEC_PATH}` — full path to `dist/cove-image-lab/cove-image-lab`
- `Icon={ICON_PATH}` — full path to a real PNG (you can copy
  `src/cove_image_lab/assets/cove_icon.png` into your icon theme, or
  reference an absolute path directly)

Then:

```bash
cp packaging/cove-image-lab.desktop ~/.local/share/applications/
update-desktop-database ~/.local/share/applications 2>/dev/null || true
```

Most desktop environments will pick the entry up after a relog. If your
session does not, run the `update-desktop-database` line above.

## Validation

The bundle was verified to:

- launch headlessly (`QT_QPA_PLATFORM=offscreen`) without tracebacks
- launch on a real X display, reaching the Qt event loop
- ship the icon resource at the path
  `cove_image_lab/assets/cove_icon.png`
- expose the three expected tabs: Compare, Forensics, Redaction
