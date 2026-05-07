# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Cove Image Lab — Linux one-folder bundle.
#
# Run from the repo root:
#   pyinstaller packaging/cove-image-lab.spec
#
# Or via the wrapper script:
#   ./packaging/build-linux.sh
#
# All paths are derived from SPECPATH (the directory of this .spec file)
# so the build is reproducible regardless of the caller's cwd.
import os

PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))
SRC = os.path.join(PROJECT_ROOT, "src")
LAUNCHER = os.path.join(SPECPATH, "launcher.py")
ICON = os.path.join(SRC, "cove_image_lab", "assets", "cove_icon.png")


a = Analysis(
    [LAUNCHER],
    pathex=[SRC],
    binaries=[],
    datas=[(ICON, "cove_image_lab/assets")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="cove-image-lab",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="cove-image-lab",
)
