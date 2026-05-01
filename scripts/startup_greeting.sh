#!/usr/bin/env bash
# J.A.R.V.I.S. startup greeting — runs at desktop login.
# Fetches a time-aware greeting from the local JARVIS API, speaks it via Piper
# (or espeak as fallback), and opens the JARVIS interface in the browser.
#
# Usage:
#   Called automatically by systemd user service or desktop autostart.
#   Can also be run manually: bash scripts/startup_greeting.sh
#
# Dependencies: curl, jq (or python3 for JSON parsing), optional: piper, espeak
# Configuration: reads /etc/jarvis/config.env for JARVIS_PORT, TLS settings, PIPER_BIN, PIPER_MODEL

set -euo pipefail

CONFIG_FILE="${JARVIS_CONFIG_FILE:-/etc/jarvis/config.env}"

# --- Load config if present ---------------------------------------------------
if [[ -f "${CONFIG_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
  set +a
fi

JARVIS_PORT="${JARVIS_PORT:-443}"
JARVIS_HOST="${JARVIS_GREETING_HOST:-127.0.0.1}"
JARVIS_URL_BASE="https://${JARVIS_HOST}:${JARVIS_PORT}"
GREETING_URL="${JARVIS_URL_BASE}/greeting"
OPEN_BROWSER="${JARVIS_GREETING_OPEN_BROWSER:-1}"
SPEAK_GREETING="${JARVIS_GREETING_SPEAK:-1}"
BROWSER_DELAY="${JARVIS_GREETING_BROWSER_DELAY:-3}"

PIPER_BIN="${PIPER_BIN:-}"
PIPER_MODEL="${PIPER_MODEL:-}"
PIPER_LENGTH_SCALE="${PIPER_LENGTH_SCALE:-1.12}"
PIPER_NOISE_SCALE="${PIPER_NOISE_SCALE:-0.55}"
PIPER_NOISE_W="${PIPER_NOISE_W:-0.75}"

log() { echo "[jarvis-greeting] $*"; }

# --- Wait for JARVIS to be reachable ------------------------------------------
wait_for_jarvis() {
  local max_attempts=20
  local attempt=0
  while [[ ${attempt} -lt ${max_attempts} ]]; do
    if curl -kfsS "${GREETING_URL}" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    attempt=$((attempt + 1))
  done
  return 1
}

# --- Fetch greeting text ------------------------------------------------------
fetch_greeting() {
  local response
  response=$(curl -kfsS --max-time 5 "${GREETING_URL}" 2>/dev/null) || {
    echo "J.A.R.V.I.S. online. Good to see you, sir."
    return
  }
  # Extract "text" field using python3 (always available) or jq
  if command -v python3 >/dev/null 2>&1; then
    python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('text','J.A.R.V.I.S. online.'))" <<< "${response}"
  elif command -v jq >/dev/null 2>&1; then
    echo "${response}" | jq -r '.text // "J.A.R.V.I.S. online."'
  else
    echo "J.A.R.V.I.S. online."
  fi
}

# --- Speak text ---------------------------------------------------------------
speak() {
  local text="$1"
  [[ "${SPEAK_GREETING}" == "1" ]] || return 0

  # Piper (high quality, same TTS as JARVIS runtime)
  if [[ -n "${PIPER_BIN}" && -x "${PIPER_BIN}" && -n "${PIPER_MODEL}" && -f "${PIPER_MODEL}" ]]; then
    echo "${text}" | "${PIPER_BIN}" \
      --model "${PIPER_MODEL}" \
      --output_raw \
      --length_scale "${PIPER_LENGTH_SCALE}" \
      --noise_scale "${PIPER_NOISE_SCALE}" \
      --noise_w "${PIPER_NOISE_W}" \
      2>/dev/null \
      | aplay -r 22050 -f S16_LE -t raw - 2>/dev/null || true
    return
  fi

  # espeak-ng fallback (always installed on Debian/Ubuntu)
  if command -v espeak-ng >/dev/null 2>&1; then
    espeak-ng -s 145 -p 40 "${text}" 2>/dev/null || true
    return
  fi

  # espeak classic fallback
  if command -v espeak >/dev/null 2>&1; then
    espeak "${text}" 2>/dev/null || true
    return
  fi

  log "No TTS engine found. Set PIPER_BIN and PIPER_MODEL in ${CONFIG_FILE} for voice greeting."
}

# --- Open browser -------------------------------------------------------------
open_browser() {
  [[ "${OPEN_BROWSER}" == "1" ]] || return 0
  sleep "${BROWSER_DELAY}" &
  local delay_pid=$!
  wait "${delay_pid}" 2>/dev/null || true

  local url="${JARVIS_URL_BASE}/"
  # Try common desktop browsers
  for browser in xdg-open chromium-browser chromium google-chrome firefox; do
    if command -v "${browser}" >/dev/null 2>&1; then
      "${browser}" "${url}" >/dev/null 2>&1 &
      log "Opened ${url} in ${browser}"
      return
    fi
  done
  log "No browser found to open ${url}"
}

# --- Main ---------------------------------------------------------------------
main() {
  log "Waiting for J.A.R.V.I.S. backend..."
  if ! wait_for_jarvis; then
    log "J.A.R.V.I.S. did not respond in time — speaking fallback."
    speak "J.A.R.V.I.S. backend not responding. Starting anyway, sir."
    open_browser &
    return 1
  fi

  log "Backend ready. Fetching greeting."
  local greeting_text
  greeting_text=$(fetch_greeting)
  log "Greeting: ${greeting_text}"

  speak "${greeting_text}" &
  open_browser &
  wait
}

main "$@"
