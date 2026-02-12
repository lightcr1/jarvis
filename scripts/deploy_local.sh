#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_DIR="/opt/jarvis"
VENV_DIR="${INSTALL_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"
SERVICE_SRC="${INSTALL_DIR}/systemd/jarvis.service"
SERVICE_DST="/etc/systemd/system/jarvis.service"
HEALTH_URL_HTTP="http://localhost:8000/health"
HEALTH_URL_HTTPS="https://localhost:8000/health"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run as root (use sudo)."
fi

command -v rsync >/dev/null 2>&1 || fail "rsync is required. Install it and retry."
command -v python3 >/dev/null 2>&1 || fail "python3 is required. Install it and retry."
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required on this host."
command -v openssl >/dev/null 2>&1 || fail "openssl is required for TLS certificate generation."

mkdir -p "${INSTALL_DIR}"
if [[ "$(realpath "${SOURCE_DIR}")" != "$(realpath "${INSTALL_DIR}")" ]]; then
  rsync -a --delete "${SOURCE_DIR}/" "${INSTALL_DIR}/" || fail "Failed to sync repo to ${INSTALL_DIR}."
else
  echo "Source already at ${INSTALL_DIR}; skipping rsync sync step."
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}" || fail "Failed to create venv at ${VENV_DIR}."
fi

[[ -x "${VENV_PYTHON}" ]] || fail "Python executable missing in venv: ${VENV_PYTHON}"

"${VENV_PYTHON}" -m pip install --upgrade pip || fail "Failed to upgrade pip in venv."
"${VENV_PYTHON}" -m pip install -r "${INSTALL_DIR}/requirements.txt" || fail "Failed to install requirements.txt"
"${VENV_PYTHON}" -m pip install "uvicorn[standard]" || fail "Failed to install uvicorn[standard]"

if [[ ! -x "${VENV_DIR}/bin/uvicorn" ]]; then
  fail "uvicorn executable missing at ${VENV_DIR}/bin/uvicorn after install."
fi

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${INSTALL_DIR}/config/jarvis.env.example" "${CONFIG_FILE}" || fail "Failed to create ${CONFIG_FILE}"
fi
chmod 600 "${CONFIG_FILE}" || fail "Failed to chmod 600 ${CONFIG_FILE}"

# Load runtime configuration from EnvironmentFile for TLS-aware deploy checks
set -a
# shellcheck disable=SC1090
source "${CONFIG_FILE}"
set +a

TLS_CERT="${JARVIS_TLS_CERT_FILE:-}"
TLS_KEY="${JARVIS_TLS_KEY_FILE:-}"
TLS_ACTIVE="0"

if [[ -n "${TLS_CERT}" || -n "${TLS_KEY}" ]]; then
  [[ -n "${TLS_CERT}" && -n "${TLS_KEY}" ]] || fail "Set both JARVIS_TLS_CERT_FILE and JARVIS_TLS_KEY_FILE (or neither)."

  TLS_DIR="/etc/jarvis/tls"
  mkdir -p "${TLS_DIR}"

  # Idempotent self-signed generation when configured files are missing
  if [[ ! -f "${TLS_CERT}" || ! -f "${TLS_KEY}" ]]; then
    echo "TLS enabled in config; generating self-signed certificate (idempotent)."
    openssl req -x509 -nodes -newkey rsa:2048       -keyout "${TLS_KEY}"       -out "${TLS_CERT}"       -days 825       -subj "/CN=$(hostname -f 2>/dev/null || hostname)"       >/dev/null 2>&1 || fail "Failed to generate self-signed TLS certificate/key."
  fi

  chmod 600 "${TLS_KEY}" || fail "Failed to chmod 600 ${TLS_KEY}"
  chmod 644 "${TLS_CERT}" || fail "Failed to chmod 644 ${TLS_CERT}"
  TLS_ACTIVE="1"
fi

[[ -f "${SERVICE_SRC}" ]] || fail "Missing service template: ${SERVICE_SRC}"
install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}" || fail "Failed to install systemd service."

systemctl daemon-reload || fail "systemctl daemon-reload failed"
systemctl enable --now jarvis.service || fail "Failed to enable/start jarvis.service"

systemctl --no-pager --full status jarvis.service || true

if [[ "${TLS_ACTIVE}" == "1" ]]; then
  echo "Health URL: ${HEALTH_URL_HTTPS}"
  curl -kfsS "${HEALTH_URL_HTTPS}" || fail "HTTPS health check failed"
else
  echo "Health URL: ${HEALTH_URL_HTTP}"
  curl -fsS "${HEALTH_URL_HTTP}" || fail "HTTP health check failed"
fi
