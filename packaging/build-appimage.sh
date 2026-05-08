#!/usr/bin/env bash
# Wrap the existing PyInstaller --onedir bundle into an AppImage.
#
# Pre-requisite: dist/cove-image-lab/ must already exist (run
# packaging/build-linux.sh first). This script does NOT install or
# upgrade dependencies; it expects appimagetool on PATH or in
# $APPIMAGETOOL.
#
# Usage:
#   ./packaging/build-appimage.sh
#
# Environment overrides:
#   APPIMAGETOOL=/path/to/appimagetool        # explicit binary
#   OUTPUT_DIR=/somewhere/dist                # where to drop the .AppImage
#   OUTPUT_NAME=Cove-Image-Lab-x86_64.AppImage
#
# Output:
#   $OUTPUT_DIR/$OUTPUT_NAME
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/cove-image-lab"
APPDIR="$REPO_ROOT/build/AppDir"

if [[ ! -x "$DIST_DIR/cove-image-lab" ]]; then
  echo "[appimage] expected $DIST_DIR/cove-image-lab; run packaging/build-linux.sh first" >&2
  exit 1
fi

APPIMAGETOOL="${APPIMAGETOOL:-}"
if [[ -z "$APPIMAGETOOL" ]]; then
  if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGETOOL="appimagetool"
  else
    echo "[appimage] appimagetool not found on PATH. Set APPIMAGETOOL=/path/to/appimagetool" >&2
    exit 1
  fi
fi

# Reset AppDir
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy the PyInstaller bundle
cp -a "$DIST_DIR/." "$APPDIR/usr/bin/"

# Icon — required at AppDir root AND at /usr/share/icons for the .desktop ref
ICON_SRC="$REPO_ROOT/src/cove_image_lab/assets/cove_icon.png"
cp "$ICON_SRC" "$APPDIR/usr/share/icons/hicolor/256x256/apps/cove-image-lab.png"
cp "$ICON_SRC" "$APPDIR/cove-image-lab.png"

# Desktop entry (AppDir requires one at root, plus a copy under /usr/share/applications)
cat > "$APPDIR/cove-image-lab.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Cove Image Lab
Comment=Offline two-image comparison and inspection
Exec=cove-image-lab
Icon=cove-image-lab
Terminal=false
Categories=Graphics;Photography;
DESKTOP
cp "$APPDIR/cove-image-lab.desktop" "$APPDIR/usr/share/applications/"

# AppRun shim — appimagetool needs an executable AppRun at the AppDir root
cat > "$APPDIR/AppRun" <<'APPRUN'
#!/usr/bin/env bash
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/cove-image-lab" "$@"
APPRUN
chmod +x "$APPDIR/AppRun"

OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/dist}"
OUTPUT_NAME="${OUTPUT_NAME:-Cove-Image-Lab-x86_64.AppImage}"
mkdir -p "$OUTPUT_DIR"

ARCH=x86_64 "$APPIMAGETOOL" --no-appstream "$APPDIR" "$OUTPUT_DIR/$OUTPUT_NAME"
chmod +x "$OUTPUT_DIR/$OUTPUT_NAME"

echo "[appimage] OK: $OUTPUT_DIR/$OUTPUT_NAME"
