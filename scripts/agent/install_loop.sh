#!/usr/bin/env bash
# Install/update the local Jarvis autonomy loop from the versioned repo copy.
# Idempotent, no root required (files are owned by "media"). Never touches a pod.
#
# Usage:
#   ./scripts/agent/install_loop.sh --dry-run   # show diff + checks, change nothing
#   ./scripts/agent/install_loop.sh             # backup, test, install
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/scripts/agent/autonomy_loop.py"
INSTALLED="/home/media/jarvis-openhands/autonomy/autonomy_loop.py"
TARGET_DIR="$(dirname "$INSTALLED")"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    *) echo "Unknown argument: $arg (only --dry-run is supported)" >&2; exit 2 ;;
  esac
done

[ -f "$SOURCE" ] || { echo "Versioned source not found: $SOURCE" >&2; exit 1; }

echo "==> Python syntax check"
python3 -m py_compile "$SOURCE"

if [ -n "${JARVIS_REPO:-}" ]; then
  echo "==> Offline loop tests against repo root $JARVIS_REPO"
  (cd "$JARVIS_REPO" && python3 -m pytest -q tests/test_autonomy_loop.py)
else
  echo "JARVIS_REPO env not set; skipping offline pytest (set it to the checked-out repo root)." >&2
fi

if [ -f "$INSTALLED" ]; then
  echo "==> Diff (installed vs. versioned):"
  if diff -u "$INSTALLED" "$SOURCE" | head -120; then
    echo "    (identical)"
  fi
else
  echo "    installed loop missing at $INSTALLED (first install)"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "Dry run aborted: no changes made."
  exit 0
fi

mkdir -p "$TARGET_DIR"
BACKUP="$TARGET_DIR/autonomy_loop.py.bak.$(date +%Y%m%d-%H%M%S)"
if [ -f "$INSTALLED" ]; then
  cp -p "$INSTALLED" "$BACKUP"
  echo "==> Backup created: $BACKUP"
fi

install -m 0644 "$SOURCE" "$INSTALLED"
cmp -s "$SOURCE" "$INSTALLED" || { echo "Installation verify failed" >&2; exit 1; }

echo "==> Installed. Verify with:"
echo "    crontab -l | grep autonomy"
echo "    tail -20 $TARGET_DIR/autonomy-loop.log"
echo "Rollback: cp '$BACKUP' '$INSTALLED'"
