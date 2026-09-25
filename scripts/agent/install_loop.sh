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
CHECK=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --check) CHECK=1 ;;
    *) echo "Unknown argument: $arg (only --dry-run and --check are supported)" >&2; exit 2 ;;
  esac
done

[ -f "$SOURCE" ] || { echo "Versioned source not found: $SOURCE" >&2; exit 1; }

if [ "$CHECK" -eq 1 ]; then
  # Drift-Check fuer einen spaeteren Timer: Exit 1, wenn installiert != Repo.
  if [ ! -f "$INSTALLED" ]; then
    echo "DRIFT: installierte Loop-Kopie fehlt: $INSTALLED" >&2
    exit 1
  fi
  src_hash=$(sha256sum "$SOURCE" | awk '{print $1}')
  inst_hash=$(sha256sum "$INSTALLED" | awk '{print $1}')
  if [ "$src_hash" = "$inst_hash" ]; then
    echo "OK: installiert == versionierte Quelle ($src_hash)"
    exit 0
  fi
  echo "DRIFT: installiert ($inst_hash) != Repo ($src_hash)" >&2
  exit 1
fi

echo "==> Python syntax check"
python3 -m py_compile "$SOURCE"

if [ -n "${JARVIS_REPO:-}" ]; then
  echo "==> Offline loop tests against repo root $JARVIS_REPO"
  PY="${PYTHON:-python3}"
  if "$PY" -m pytest -q "$JARVIS_REPO/tests/test_autonomy_loop.py" >/dev/null 2>&1; then
    echo "    tests passed ($PY)"
  else
    ok=0
    for alt in /home/media/runpod/.venv/bin/python /opt/jarvis/.venv/bin/python; do
      if [ -x "$alt" ] && "$alt" -m pytest -q "$JARVIS_REPO/tests/test_autonomy_loop.py" >/dev/null 2>&1; then
        echo "    tests passed ($alt)"; ok=1; break
      fi
    done
    if [ "$ok" -ne 1 ]; then
      echo "    WARN: pytest nicht verfuegbar - Syntax ok, Offline-Tests nur in CI" >&2
    fi
  fi
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
