#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
INSTALL_DIR="/opt/jarvis"
VENV_DIR="${INSTALL_DIR}/.venv"
VENV_PYTHON="${VENV_DIR}/bin/python"
CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"
HEALTH_URL="http://127.0.0.1:8000/health"

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

mkdir -p "${INSTALL_DIR}"
if [[ "$(realpath "${SOURCE_DIR}")" != "$(realpath "${INSTALL_DIR}")" ]]; then
  rsync -a --delete "${SOURCE_DIR}/" "${INSTALL_DIR}/" || fail "Failed to sync repo to ${INSTALL_DIR}."
else
  echo "Source already at ${INSTALL_DIR}; skipping rsync sync step."
fi

id -u jarvis >/dev/null 2>&1 || useradd -m -s /bin/bash jarvis

mkdir -p /opt/jarvis/models/llm /opt/jarvis/models/stt /opt/jarvis/models/tts
chown -R jarvis:jarvis /opt/jarvis/models || true

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv "${VENV_DIR}" || fail "Failed to create venv at ${VENV_DIR}."
fi

[[ -x "${VENV_PYTHON}" ]] || fail "Python executable missing in venv: ${VENV_PYTHON}"

if [[ "${SKIP_PIP_INSTALL}" != "1" ]]; then
  "${VENV_PYTHON}" -m pip install --upgrade pip || fail "Failed to upgrade pip in venv."
  "${VENV_PYTHON}" -m pip install -r "${INSTALL_DIR}/requirements.txt" || fail "Failed to install requirements.txt"
  "${VENV_PYTHON}" -m pip install "uvicorn[standard]" || fail "Failed to install uvicorn[standard]"
else
  echo "SKIP_PIP_INSTALL=1 set; skipping dependency installation."
fi

if [[ ! -x "${VENV_DIR}/bin/uvicorn" ]]; then
  fail "uvicorn executable missing at ${VENV_DIR}/bin/uvicorn after install/prebake."
fi

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${INSTALL_DIR}/config/jarvis.env.example" "${CONFIG_FILE}" || fail "Failed to create ${CONFIG_FILE}"
fi
chmod 600 "${CONFIG_FILE}" || fail "Failed to chmod 600 ${CONFIG_FILE}"

for unit in jarvis-backend.service jarvis-kiosk.service jarvis.service first-boot-wizard.service; do
  [[ -f "${INSTALL_DIR}/systemd/${unit}" ]] || fail "Missing service template: ${INSTALL_DIR}/systemd/${unit}"
  install -m 0644 "${INSTALL_DIR}/systemd/${unit}" "/etc/systemd/system/${unit}" || fail "Failed to install ${unit}"
done

chmod +x /opt/jarvis/scripts/start_kiosk.sh /opt/jarvis/scripts/kiosk_session.sh /opt/jarvis/scripts/check_models.sh /opt/jarvis/scripts/install_models_placeholder.sh || true
install -m 0755 "${INSTALL_DIR}/scripts/first_boot_wizard.sh" /usr/local/bin/jarvis-first-boot || fail "Failed to install first boot script"

systemctl daemon-reload || fail "systemctl daemon-reload failed"
systemctl enable --now jarvis-backend.service jarvis-kiosk.service || fail "Failed to enable/start backend+kiosk services"

systemctl --no-pager --full status jarvis-backend.service || true
systemctl --no-pager --full status jarvis-kiosk.service || true
echo "Health URL: ${HEALTH_URL}"
