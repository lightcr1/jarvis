#!/usr/bin/env bash
set -euo pipefail

CHROMIUM_BIN=""
if command -v chromium-browser >/dev/null 2>&1; then
  CHROMIUM_BIN="$(command -v chromium-browser)"
elif command -v chromium >/dev/null 2>&1; then
  CHROMIUM_BIN="$(command -v chromium)"
else
  echo "Chromium binary not found (expected chromium-browser or chromium)." >&2
  exit 1
fi

export JARVIS_KIOSK_URL="${JARVIS_KIOSK_URL:-http://127.0.0.1:8000/static/static-v4-tts.html}"
export JARVIS_CHROMIUM_BIN="${CHROMIUM_BIN}"

exec xinit /opt/jarvis/scripts/kiosk_session.sh -- :0 -nolisten tcp vt7
