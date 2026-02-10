#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_DIR="/opt/jarvis"
VENV_DIR="${INSTALL_DIR}/.venv"
CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"
SERVICE_SRC="${INSTALL_DIR}/systemd/jarvis.service"
SERVICE_DST="/etc/systemd/system/jarvis.service"
HEALTH_URL="http://localhost:8000/health"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (use sudo)." >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
if [[ "$(realpath "${SOURCE_DIR}")" != "$(realpath "${INSTALL_DIR}")" ]]; then
  rsync -a --delete "${SOURCE_DIR}/" "${INSTALL_DIR}/"
else
  echo "Source already at ${INSTALL_DIR}; skipping rsync sync step."
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}"
fi

"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"
"${VENV_DIR}/bin/pip" install "uvicorn[standard]"

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${INSTALL_DIR}/config/jarvis.env.example" "${CONFIG_FILE}"
fi
chmod 600 "${CONFIG_FILE}"

install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}"

systemctl daemon-reload
systemctl enable --now jarvis.service

systemctl --no-pager --full status jarvis.service || true
echo "Health URL: ${HEALTH_URL}"
