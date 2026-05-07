#!/usr/bin/env bash
# Build a one-folder Linux bundle of Cove Image Lab using PyInstaller.
#
# This script does NOT install or upgrade any dependencies. It assumes
# the Python environment is already provisioned with the project and
# PyInstaller. See packaging/README.md for the one-time setup commands.
#
# Usage:
#   ./packaging/build-linux.sh
#
# Environment overrides (in priority order):
#   PYTHON=/path/to/python   # exact interpreter to use
#   VENV=/path/to/venv       # use $VENV/bin/python
#                            # default: build/.venv/bin/python, then python3
#
# Output:
#   dist/cove-image-lab/                 # runnable bundle
#   dist/cove-image-lab/cove-image-lab   # ELF launcher
#
# Both build/ and dist/ are gitignored.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Resolve the Python interpreter to use, in order of preference.
if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -n "${VENV:-}" && -x "$VENV/bin/python" ]]; then
  PY="$VENV/bin/python"
elif [[ -x "$REPO_ROOT/build/.venv/bin/python" ]]; then
  PY="$REPO_ROOT/build/.venv/bin/python"
else
  PY="python3"
fi

SPEC="$REPO_ROOT/packaging/cove-image-lab.spec"

setup_help() {
  cat >&2 <<'EOF'

This script does not install dependencies. It expects PyInstaller and
the cove_image_lab package to already be importable from the chosen
Python interpreter.

One-time setup (creates a build venv at build/.venv/):

  python3 -m venv build/.venv
  build/.venv/bin/python -m pip install -e .
  build/.venv/bin/python -m pip install "pyinstaller>=6"

Then re-run:

  ./packaging/build-linux.sh

To use a different Python or venv:

  PYTHON=/path/to/python ./packaging/build-linux.sh
  VENV=/path/to/venv      ./packaging/build-linux.sh

EOF
}

# Verify the interpreter exists.
if ! command -v "$PY" >/dev/null 2>&1 && [[ ! -x "$PY" ]]; then
  echo "[build] Python interpreter not found: $PY" >&2
  setup_help
  exit 1
fi

# Verify the project is importable from this Python.
if ! "$PY" -c "import cove_image_lab" >/dev/null 2>&1; then
  echo "[build] cannot import 'cove_image_lab' from $PY" >&2
  setup_help
  exit 1
fi

# Verify PyInstaller is installed.
if ! "$PY" -c "import PyInstaller" >/dev/null 2>&1; then
  echo "[build] cannot import 'PyInstaller' from $PY" >&2
  setup_help
  exit 1
fi

echo "[build] python:  $PY"
echo "[build] running PyInstaller against $SPEC"

"$PY" -m PyInstaller \
  --noconfirm \
  --workpath "$REPO_ROOT/build" \
  --distpath "$REPO_ROOT/dist" \
  "$SPEC"

OUT="$REPO_ROOT/dist/cove-image-lab"
if [[ -x "$OUT/cove-image-lab" ]]; then
  echo "[build] OK"
  echo "[build] bundle:   $OUT"
  echo "[build] launcher: $OUT/cove-image-lab"
else
  echo "[build] FAILED — expected $OUT/cove-image-lab to exist" >&2
  exit 1
fi
