#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/jarvis"
CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root (use sudo)." >&2
  exit 1
fi

mkdir -p "${INSTALL_DIR}"
rm -rf "${INSTALL_DIR:?}/"*
cp -a "${ROOT_DIR}/." "${INSTALL_DIR}/"

python3 -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/pip" install --upgrade pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

mkdir -p "${CONFIG_DIR}"
if [[ ! -f "${CONFIG_FILE}" ]]; then
  cp "${INSTALL_DIR}/config/jarvis.env.example" "${CONFIG_FILE}"
  chmod 600 "${CONFIG_FILE}"
fi

cp "${INSTALL_DIR}/systemd/jarvis.service" /etc/systemd/system/jarvis.service
cp "${INSTALL_DIR}/systemd/first-boot-wizard.service" /etc/systemd/system/first-boot-wizard.service
cp "${INSTALL_DIR}/scripts/first_boot_wizard.sh" /usr/local/bin/jarvis-first-boot
chmod +x /usr/local/bin/jarvis-first-boot

systemctl daemon-reload
systemctl enable jarvis
systemctl enable first-boot-wizard

echo "Installed. Start with: sudo systemctl start jarvis"
