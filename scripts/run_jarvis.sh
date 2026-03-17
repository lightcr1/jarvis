#!/usr/bin/env bash
set -euo pipefail

HOST="${JARVIS_HOST:-0.0.0.0}"
PORT="${JARVIS_PORT:-443}"
APP="jarvisappv4:app"

ARGS=("${APP}" "--host" "${HOST}" "--port" "${PORT}" "--proxy-headers" "--forwarded-allow-ips" "*")

TLS_CERT="${JARVIS_TLS_CERT_FILE:-}"
TLS_KEY="${JARVIS_TLS_KEY_FILE:-}"

if [[ -n "${TLS_CERT}" && -n "${TLS_KEY}" && -f "${TLS_CERT}" && -f "${TLS_KEY}" ]]; then
  ARGS+=("--ssl-certfile" "${TLS_CERT}" "--ssl-keyfile" "${TLS_KEY}")
fi

exec /opt/jarvis/.venv/bin/uvicorn "${ARGS[@]}"
