#!/usr/bin/env bash
set -euo pipefail

URL="${JARVIS_KIOSK_URL:-http://127.0.0.1:8000/static/static-v4-tts.html}"
CHROMIUM_BIN="${JARVIS_CHROMIUM_BIN:-chromium-browser}"

xset -dpms || true
xset s off || true
xset s noblank || true

openbox-session &
exec "${CHROMIUM_BIN}" \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --autoplay-policy=no-user-gesture-required \
  --check-for-update-interval=31536000 \
  --no-first-run \
  --disable-features=TranslateUI \
  "${URL}"
