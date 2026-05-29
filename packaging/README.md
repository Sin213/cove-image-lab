# Packaging

Local-only build scaffold for **Cove Image Lab**. Produces a Linux
one-folder bundle, an AppImage, a `.deb`, a Windows `Portable.exe`, and
a Windows `Setup.exe`. No auto-update, no telemetry.

Release artifacts are also produced automatically by
`.github/workflows/release.yml` whenever a `v*` tag is pushed; see the
**CI release flow** section at the bottom.

macOS is not yet scaffolded.

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
- expose the four expected tabs: Compare, Forensics, Redaction, AI
  Indicator

## Build an AppImage

Run after the one-folder bundle in `dist/cove-image-lab/` exists:

```bash
# appimagetool must be on PATH or pointed at via APPIMAGETOOL=
./packaging/build-appimage.sh
```

Output: `dist/Cove-Image-Lab-x86_64.AppImage`. The script constructs an
AppDir, drops the PyInstaller bundle into `AppDir/usr/bin/`, copies the
icon, writes a minimal `.desktop` and `AppRun`, and invokes
`appimagetool --no-appstream`.

## Build a `.deb`

Also runs against the existing `dist/cove-image-lab/`:

```bash
./packaging/build-deb.sh
```

Output: `dist/cove-image-lab_<version>_amd64.deb`. Layout: bundle
installed at `/opt/cove-image-lab/`, a `/usr/bin/cove-image-lab` shim
on PATH, plus `.desktop` + icon under `/usr/share`.

`VERSION` is read from `pyproject.toml` unless overridden:
`VERSION=1.2.3 ./packaging/build-deb.sh`.

## Build the Windows Portable.exe (locally)

PyInstaller `--onefile` from any Windows host with Python and the
project installed:

```powershell
python -m pip install -e .
python -m pip install "pyinstaller>=6" "Pillow>=10"

# Convert PNG -> ICO so the .exe carries a proper icon
python -c "from PIL import Image; Image.open('src/cove_image_lab/assets/cove_icon.png').convert('RGBA').save('src/cove_image_lab/assets/cove_icon.ico', sizes=[(256,256),(128,128),(64,64),(48,48),(32,32),(16,16)])"

python -m PyInstaller --noconfirm `
  --onefile --windowed `
  --name "Cove-Image-Lab-Portable" `
  --icon "src/cove_image_lab/assets/cove_icon.ico" `
  --add-data "src/cove_image_lab/assets/cove_icon.png;cove_image_lab/assets" `
  --paths src `
  packaging/launcher.py
```

Output: `dist/Cove-Image-Lab-Portable.exe`.

## Build the Windows Setup.exe (locally)

Requires [Inno Setup 6](https://jrsoftware.org/isinfo.php) installed.
First produce the `--onedir` bundle (the same `cove-image-lab.spec`
works on Windows once `cove_icon.ico` exists), then run ISCC:

```powershell
python -m PyInstaller --noconfirm packaging/cove-image-lab.spec
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=1.1.0 packaging\cove-image-lab.iss
```

Output: `dist/Cove-Image-Lab-Setup-1.1.0.exe`.

## CI release flow

`.github/workflows/release.yml` runs on push of any `v*` tag (or via
manual `workflow_dispatch`). It produces, hashes, and uploads:

| Artifact                              | Job     | Tooling                              |
| ------------------------------------- | ------- | ------------------------------------ |
| `Cove-Image-Lab-x86_64.AppImage`      | linux   | PyInstaller + appimagetool           |
| `cove-image-lab_<v>_amd64.deb`        | linux   | PyInstaller + dpkg-deb               |
| `Cove-Image-Lab-Portable-<v>.exe`     | windows | PyInstaller `--onefile`              |
| `Cove-Image-Lab-Setup-<v>.exe`        | windows | PyInstaller `--onedir` + Inno Setup  |

Each artifact ships with a `<asset>.sha256` sidecar. After both build
jobs complete, a `release` job creates / updates the GitHub release
named after the tag and uploads every file. To cut a release locally:

```bash
git tag v1.2.3
git push origin v1.2.3
```
