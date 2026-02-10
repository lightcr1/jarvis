#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="/etc/jarvis"
CONFIG_FILE="${CONFIG_DIR}/config.env"
STATE_FILE="/var/lib/jarvis/first-boot.done"

mkdir -p "${CONFIG_DIR}" /var/lib/jarvis

if [[ -f "${STATE_FILE}" ]]; then
  exit 0
fi

cat > "${CONFIG_FILE}" <<'EOF'
# Jarvis first-boot config (edit as needed)
JARVIS_PASSPHRASE=change-me
ALLOWED_TARGETS=local
COOLDOWN_RESTART_SECONDS=60
COOLDOWN_CRITICAL_SECONDS=90

# Optional: Proxmox
# PROXMOX_BASE_URL=https://pve.local:8006
# PROXMOX_API_TOKEN=insert_here

# Optional: Cloud LLM
# OPENAI_API_KEY=insert_here
# GEMINI_API_KEY=insert_here
EOF

chmod 600 "${CONFIG_FILE}"

if [[ -x "/opt/jarvis/scripts/deploy_local.sh" ]]; then
  SOURCE_DIR="/opt/jarvis" /opt/jarvis/scripts/deploy_local.sh
fi

touch "${STATE_FILE}"

echo "Jarvis first-boot config created at ${CONFIG_FILE}."
