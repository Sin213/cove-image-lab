#!/usr/bin/env bash
# Wrap the existing PyInstaller --onedir bundle into a .deb package.
#
# Pre-requisite: dist/cove-image-lab/ must already exist (run
# packaging/build-linux.sh first). Requires dpkg-deb on PATH (provided
# by dpkg, standard on Debian/Ubuntu CI runners).
#
# Usage:
#   ./packaging/build-deb.sh
#
# Environment overrides:
#   VERSION=1.1.0          # defaults to pyproject.toml version
#   OUTPUT_DIR=/somewhere/dist
#
# Output:
#   $OUTPUT_DIR/cove-image-lab_<version>_amd64.deb
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIST_DIR="$REPO_ROOT/dist/cove-image-lab"

if [[ ! -x "$DIST_DIR/cove-image-lab" ]]; then
  echo "[deb] expected $DIST_DIR/cove-image-lab; run packaging/build-linux.sh first" >&2
  exit 1
fi

if ! command -v dpkg-deb >/dev/null 2>&1; then
  echo "[deb] dpkg-deb not found on PATH" >&2
  exit 1
fi

# Resolve version from pyproject.toml unless overridden.
VERSION="${VERSION:-}"
if [[ -z "$VERSION" ]]; then
  VERSION="$(grep -E '^version\s*=' "$REPO_ROOT/pyproject.toml" | head -1 | cut -d'"' -f2)"
fi
if [[ -z "$VERSION" ]]; then
  echo "[deb] could not resolve version; pass VERSION=x.y.z" >&2
  exit 1
fi

DEB_NAME="cove-image-lab_${VERSION}_amd64"
DEB_ROOT="$REPO_ROOT/build/$DEB_NAME"

rm -rf "$DEB_ROOT"
mkdir -p "$DEB_ROOT/DEBIAN"
mkdir -p "$DEB_ROOT/opt/cove-image-lab"
mkdir -p "$DEB_ROOT/usr/bin"
mkdir -p "$DEB_ROOT/usr/share/applications"
mkdir -p "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps"

# Bundle goes in /opt to keep _internal/ together
cp -a "$DIST_DIR/." "$DEB_ROOT/opt/cove-image-lab/"

# /usr/bin shim so `cove-image-lab` is on PATH
cat > "$DEB_ROOT/usr/bin/cove-image-lab" <<'SHIM'
#!/usr/bin/env bash
exec /opt/cove-image-lab/cove-image-lab "$@"
SHIM
chmod 0755 "$DEB_ROOT/usr/bin/cove-image-lab"

# Icon
cp "$REPO_ROOT/src/cove_image_lab/assets/cove_icon.png" \
   "$DEB_ROOT/usr/share/icons/hicolor/256x256/apps/cove-image-lab.png"

# Desktop entry
cat > "$DEB_ROOT/usr/share/applications/cove-image-lab.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Cove Image Lab
Comment=Offline two-image comparison and inspection
Exec=cove-image-lab
Icon=cove-image-lab
Terminal=false
Categories=Graphics;Photography;
DESKTOP

# Installed-Size in KB (du reports KB by default with -k)
INSTALLED_SIZE=$(du -sk "$DEB_ROOT/opt" "$DEB_ROOT/usr" | awk '{ s += $1 } END { print s }')

# control file
cat > "$DEB_ROOT/DEBIAN/control" <<CONTROL
Package: cove-image-lab
Version: $VERSION
Section: graphics
Priority: optional
Architecture: amd64
Depends: libc6, libxcb1, libgl1, libfontconfig1, libxkbcommon0
Installed-Size: $INSTALLED_SIZE
Maintainer: Sin213
Homepage: https://github.com/Sin213/cove-image-lab
Description: Offline desktop two-image comparison and inspection
 Compare, redact, and inspect images locally with no network use.
 Includes Forensics ELA / Noise Map, an AI Indicator review aid, and
 an opaque privacy redaction tool. PySide6 frontend, NumPy diff core.
CONTROL

OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/dist}"
mkdir -p "$OUTPUT_DIR"
dpkg-deb --build --root-owner-group "$DEB_ROOT" "$OUTPUT_DIR/$DEB_NAME.deb"

echo "[deb] OK: $OUTPUT_DIR/$DEB_NAME.deb"
