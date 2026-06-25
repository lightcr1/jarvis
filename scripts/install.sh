#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Interactive install wizard
#
# Installs JARVIS to /opt/jarvis as a systemd service running as user 'jarvis'.
# Guides you through all required config interactively.
# Must be run as root (sudo ./scripts/install.sh).
# Idempotent — safe to run multiple times.
# =============================================================================

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JARVIS_USER="jarvis"
JARVIS_DATA_DIR="/var/lib/jarvis"
JARVIS_CONFIG_DIR="/etc/jarvis"
JARVIS_ENV_FILE="${JARVIS_CONFIG_DIR}/jarvis.env"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SERVICE_FILE="/etc/systemd/system/jarvis.service"

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()     { echo -e "${GREEN}[✓]${RESET} $*"; }
info()    { echo -e "${CYAN}[→]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
fail()    { echo -e "${RED}[✗] ERROR: $*${RESET}" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${RESET}"; }

ask() {
  # ask <variable_name> <prompt> [default]
  local var="$1" prompt="$2" default="${3:-}"
  local display_default=""
  [[ -n "${default}" ]] && display_default=" [${default}]"
  echo -en "${CYAN}?${RESET} ${prompt}${display_default}: "
  read -r input
  input="${input:-${default}}"
  printf -v "${var}" '%s' "${input}"
}

ask_secret() {
  # ask_secret <variable_name> <prompt>
  local var="$1" prompt="$2"
  echo -en "${CYAN}?${RESET} ${prompt} (hidden): "
  read -rs input
  echo
  printf -v "${var}" '%s' "${input}"
}

confirm() {
  # confirm <prompt> [default: Y|N] → returns 0=yes 1=no
  local prompt="$1" default="${2:-Y}"
  local opts="Y/n"; [[ "${default}" == "N" ]] && opts="y/N"
  echo -en "${CYAN}?${RESET} ${prompt} [${opts}]: "
  read -r ans
  ans="${ans:-${default}}"
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]]
}

# =============================================================================
# Pre-flight
# =============================================================================
section "Pre-flight checks"

[[ "${EUID}" -eq 0 ]] || fail "This script must be run as root:  sudo ./scripts/install.sh"

command -v python3   >/dev/null 2>&1 || fail "python3 not found. Install Python 3.12+ and retry."
command -v npm       >/dev/null 2>&1 || fail "npm not found. Install Node.js 18+ and retry."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found. Install rsync and retry."
command -v systemctl >/dev/null 2>&1 || fail "systemd not found. Only Linux with systemd is supported."

PY_VER="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
log "Python ${PY_VER}"

[[ -f "${JARVIS_SOURCE_ROOT}/jarvisappv4.py" ]]   || fail "jarvisappv4.py not found in ${JARVIS_SOURCE_ROOT}. Run from the repo root."
[[ -f "${JARVIS_SOURCE_ROOT}/requirements.txt" ]] || fail "requirements.txt not found."

log "Source directory: ${JARVIS_SOURCE_ROOT}"
log "Deploy target:    ${JARVIS_DEPLOY_ROOT}"

# =============================================================================
# Environment file
# =============================================================================
section "Environment configuration"

WROTE_ENV=0

if [[ -f "${JARVIS_ENV_FILE}" ]]; then
  warn "${JARVIS_ENV_FILE} already exists."
  if confirm "Replace it with a fresh template (your current file will be backed up)?"; then
    BACKUP="${JARVIS_ENV_FILE}.bak.$(date +%Y%m%d_%H%M%S)"
    cp "${JARVIS_ENV_FILE}" "${BACKUP}"
    log "Backed up to ${BACKUP}"
    cp "${JARVIS_SOURCE_ROOT}/config/prod.env.example" "${JARVIS_ENV_FILE}"
    chown root:"${JARVIS_USER}" "${JARVIS_ENV_FILE}" 2>/dev/null || true
    chmod 640 "${JARVIS_ENV_FILE}"
    log "Copied fresh template to ${JARVIS_ENV_FILE}"
    WROTE_ENV=1
  else
    info "Keeping existing ${JARVIS_ENV_FILE}."
  fi
else
  mkdir -p "${JARVIS_CONFIG_DIR}"
  chmod 750 "${JARVIS_CONFIG_DIR}"
  cp "${JARVIS_SOURCE_ROOT}/config/prod.env.example" "${JARVIS_ENV_FILE}"
  chmod 640 "${JARVIS_ENV_FILE}"
  log "Created ${JARVIS_ENV_FILE} from template."
  WROTE_ENV=1
fi

# =============================================================================
# Interactive config wizard (only when we own the env file)
# =============================================================================
if [[ "${WROTE_ENV}" -eq 1 ]]; then
  section "Required settings"

  echo
  info "I'll walk you through the required values and write them into ${JARVIS_ENV_FILE}."
  info "Press Enter to skip optional items."
  echo

  # ── Passphrase ─────────────────────────────────────────────────────────────
  ask_secret PASSPHRASE "JARVIS_PASSPHRASE — unlock phrase for guest/device tokens (required)"
  while [[ -z "${PASSPHRASE}" ]]; do
    warn "Passphrase cannot be empty."
    ask_secret PASSPHRASE "JARVIS_PASSPHRASE"
  done

  # ── Admin password ──────────────────────────────────────────────────────────
  ask_secret ADMIN_PASSWORD "Admin dashboard password (JARVIS_DEFAULT_ADMIN_PASSWORD, required)"
  while [[ -z "${ADMIN_PASSWORD}" ]]; do
    warn "Admin password cannot be empty."
    ask_secret ADMIN_PASSWORD "Admin dashboard password"
  done

  section "AI Provider (choose at least one for cloud LLM)"

  echo
  info "OpenRouter is recommended — one key routes to Claude, GPT-4, Gemini, Mistral, etc."
  info "Direct keys (Anthropic, OpenAI, etc.) are optional fallbacks."
  echo

  ask OPENROUTER_KEY "OPENROUTER_API_KEY (recommended, press Enter to skip)"
  ask ANTHROPIC_KEY  "ANTHROPIC_API_KEY  (direct Anthropic, optional)"
  ask OPENAI_KEY     "OPENAI_API_KEY     (direct OpenAI, optional)"
  ask GEMINI_KEY     "GEMINI_API_KEY     (direct Gemini / STT, optional)"
  ask MISTRAL_KEY    "MISTRAL_API_KEY    (direct Mistral, optional)"
  ask DEEPSEEK_KEY   "DEEPSEEK_API_KEY   (direct DeepSeek, optional)"

  section "Encryption key (BYOK)"

  echo
  info "JARVIS_SECRET_KEY is needed to store user-provided API keys encrypted at rest."
  info "Leave blank to auto-generate one now (recommended)."
  echo

  ask SECRET_KEY "JARVIS_SECRET_KEY (32-byte Fernet key, leave blank to generate)"

  if [[ -z "${SECRET_KEY}" ]]; then
    SECRET_KEY="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || true)"
    if [[ -n "${SECRET_KEY}" ]]; then
      log "Generated JARVIS_SECRET_KEY: ${SECRET_KEY}"
      warn "Save this key somewhere safe — losing it invalidates all stored BYOK keys."
    else
      warn "Could not auto-generate key (cryptography package not installed yet). Set JARVIS_SECRET_KEY manually after install."
    fi
  fi

  section "Optional integrations"

  ask HA_URL    "Home Assistant URL (e.g. http://homeassistant.local:8123, Enter to skip)"
  ask HA_TOKEN  "Home Assistant long-lived access token (Enter to skip)"
  ask PVE_URL   "Proxmox URL (e.g. https://pve.local:8006, Enter to skip)"
  ask PVE_TOKEN "Proxmox API token (user@realm!tokenid=secret, Enter to skip)"

  # ── Write values into env file ──────────────────────────────────────────────
  section "Writing config"

  _set_env() {
    local key="$1" val="$2"
    [[ -z "${val}" ]] && return
    if grep -q "^${key}=" "${JARVIS_ENV_FILE}" 2>/dev/null; then
      sed -i "s|^${key}=.*|${key}=${val}|" "${JARVIS_ENV_FILE}"
    else
      echo "${key}=${val}" >> "${JARVIS_ENV_FILE}"
    fi
  }

  _set_env "JARVIS_PASSPHRASE"             "${PASSPHRASE}"
  _set_env "JARVIS_DEFAULT_ADMIN_PASSWORD" "${ADMIN_PASSWORD}"
  _set_env "JARVIS_SECRET_KEY"             "${SECRET_KEY}"
  _set_env "OPENROUTER_API_KEY"            "${OPENROUTER_KEY}"
  _set_env "ANTHROPIC_API_KEY"             "${ANTHROPIC_KEY}"
  _set_env "OPENAI_API_KEY"               "${OPENAI_KEY}"
  _set_env "GEMINI_API_KEY"               "${GEMINI_KEY}"
  _set_env "MISTRAL_API_KEY"              "${MISTRAL_KEY}"
  _set_env "DEEPSEEK_API_KEY"             "${DEEPSEEK_KEY}"
  _set_env "JARVIS_HA_BASE_URL"           "${HA_URL}"
  _set_env "JARVIS_HOME_ASSISTANT_TOKEN"  "${HA_TOKEN}"
  _set_env "PROXMOX_BASE_URL"             "${PVE_URL}"
  _set_env "PROXMOX_API_TOKEN"            "${PVE_TOKEN}"

  # Ensure ownership after writes
  chown root:"${JARVIS_USER}" "${JARVIS_ENV_FILE}" 2>/dev/null || true
  chmod 640 "${JARVIS_ENV_FILE}"
  log "Config written to ${JARVIS_ENV_FILE}"
fi

# =============================================================================
# System user
# =============================================================================
section "System user"

if id "${JARVIS_USER}" >/dev/null 2>&1; then
  log "User '${JARVIS_USER}' already exists."
else
  useradd --system --no-create-home --shell /usr/sbin/nologin "${JARVIS_USER}" \
    || fail "Failed to create system user '${JARVIS_USER}'."
  log "Created system user '${JARVIS_USER}'."
fi

# =============================================================================
# Data directory
# =============================================================================
section "Data directory"

mkdir -p "${JARVIS_DATA_DIR}"
chown "${JARVIS_USER}:${JARVIS_USER}" "${JARVIS_DATA_DIR}"
chmod 750 "${JARVIS_DATA_DIR}"
log "Data directory: ${JARVIS_DATA_DIR}"

# =============================================================================
# Sync project files
# =============================================================================
section "Syncing project files → ${JARVIS_DEPLOY_ROOT}"

mkdir -p "${JARVIS_DEPLOY_ROOT}"
rsync -a --delete \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/dist' \
  "${JARVIS_SOURCE_ROOT}/" "${JARVIS_DEPLOY_ROOT}/"
chown -R "${JARVIS_USER}:${JARVIS_USER}" "${JARVIS_DEPLOY_ROOT}"
log "Files synced."

# =============================================================================
# Python virtualenv + dependencies
# =============================================================================
section "Python environment"

if [[ ! -d "${VENV_DIR}" ]]; then
  info "Creating virtualenv at ${VENV_DIR}..."
  python3.12 -m venv "${VENV_DIR}" || fail "Failed to create virtualenv."
  chown -R "${JARVIS_USER}:${JARVIS_USER}" "${VENV_DIR}"
fi

# Bootstrap pip if missing (Ubuntu 24.04 ships python3.12-venv without pip)
if [[ ! -f "${VENV_DIR}/bin/pip" ]]; then
  info "Bootstrapping pip..."
  "${VENV_DIR}/bin/python3" -m ensurepip --upgrade 2>/dev/null || \
    curl -fsSL https://bootstrap.pypa.io/get-pip.py | "${VENV_DIR}/bin/python3" -
fi

info "Installing Python dependencies (this may take a minute)..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${JARVIS_DEPLOY_ROOT}/requirements.txt" --quiet \
  || fail "pip install failed."
log "Python dependencies installed."

# =============================================================================
# Frontend build
# =============================================================================
section "Frontend build"

info "Running npm ci + npm run build..."
pushd "${JARVIS_DEPLOY_ROOT}/frontend" >/dev/null
npm ci --silent  || fail "npm ci failed."
npm run build    || fail "npm run build failed."
popd >/dev/null
log "Frontend built."

# =============================================================================
# Systemd service
# =============================================================================
section "Systemd service"

# Write the service file inline (no separate deploy/ dir required)
cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=JARVIS AI Assistant
Documentation=https://github.com/lukas/jarvis
After=network.target

[Service]
Type=simple
User=${JARVIS_USER}
WorkingDirectory=${JARVIS_DEPLOY_ROOT}
EnvironmentFile=${JARVIS_ENV_FILE}
ExecStart=${VENV_DIR}/bin/uvicorn jarvisappv4:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=jarvis

[Install]
WantedBy=multi-user.target
EOF

chmod 644 "${SERVICE_FILE}"
systemctl daemon-reload
systemctl enable jarvis.service
log "Service installed and enabled."

# =============================================================================
# Start?
# =============================================================================
section "Start service"

START_NOW=0
if confirm "Start JARVIS now?"; then
  systemctl start jarvis.service || fail "systemctl start jarvis failed. Check: journalctl -u jarvis -n 50"
  sleep 3
  if systemctl is-active --quiet jarvis.service; then
    log "Service is running."
    systemctl --no-pager --lines=5 status jarvis.service || true
    START_NOW=1
  else
    warn "Service started but is not active. Check logs: journalctl -u jarvis -n 50"
  fi
else
  info "Service not started. Start manually when ready:  sudo systemctl start jarvis"
fi

# =============================================================================
# Summary
# =============================================================================
echo
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  JARVIS install complete${RESET}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
echo -e "  Config:   ${JARVIS_ENV_FILE}"
echo -e "  App:      ${JARVIS_DEPLOY_ROOT}"
echo -e "  Data:     ${JARVIS_DATA_DIR}"
echo -e "  Logs:     journalctl -u jarvis -f"
echo
if [[ "${START_NOW}" -eq 1 ]]; then
  echo -e "  ${GREEN}JARVIS is running at http://$(hostname -I | awk '{print $1}'):8000${RESET}"
else
  echo -e "  Start:    sudo systemctl start jarvis"
  echo -e "  URL:      http://$(hostname -I | awk '{print $1}' 2>/dev/null || echo 'localhost'):8000"
fi
echo
echo -e "  Edit config:  sudo nano ${JARVIS_ENV_FILE}"
echo -e "  Then restart: sudo systemctl restart jarvis"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
