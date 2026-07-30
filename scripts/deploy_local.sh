#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Full first-time setup (TLS)
#
# Bootstraps JARVIS on a brand-new host from scratch: system user, data dir,
# venv, Python deps, frontend build, self-signed TLS cert, and a systemd unit
# serving HTTPS on :443 via /etc/jarvis/config.env.
#
# This is the TLS counterpart to scripts/install.sh (which serves plain HTTP
# on :8000 via /etc/jarvis/jarvis.env). The two use different config
# filenames on purpose, precisely so they can coexist/be told apart on the
# same host — but both install the *same* systemd unit name (jarvis.service),
# so running this on a host that already has install.sh's HTTP setup active
# will require confirmation before switching it over.
#
# Must be run as root (sudo ./scripts/deploy_local.sh). Idempotent.
# =============================================================================

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JARVIS_USER="jarvis"
JARVIS_DATA_DIR="/var/lib/jarvis"
JARVIS_CONFIG_DIR="/etc/jarvis"
JARVIS_ENV_FILE="${JARVIS_CONFIG_DIR}/config.env"
LEGACY_ENV_FILE="${JARVIS_CONFIG_DIR}/jarvis.env"
TLS_DIR="${JARVIS_CONFIG_DIR}/tls"
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

confirm() {
  local prompt="$1" default="${2:-Y}"
  local opts="Y/n"; [[ "${default}" == "N" ]] && opts="y/N"
  echo -en "${CYAN}?${RESET} ${prompt} [${opts}]: "
  read -r ans
  ans="${ans:-${default}}"
  [[ "${ans,,}" == "y" || "${ans,,}" == "yes" ]]
}

ensure_env_default() {
  # ensure_env_default <KEY> <VALUE> — appends KEY=VALUE to the env file only
  # if KEY isn't already set (commented or not), so behavior stays explicit
  # and opt-in rather than silently changing an operator's existing value.
  local key="$1" value="$2"
  grep -q "^${key}=" "${JARVIS_ENV_FILE}" 2>/dev/null && return
  echo "${key}=${value}" >> "${JARVIS_ENV_FILE}"
}

# =============================================================================
# Pre-flight
# =============================================================================
section "Pre-flight checks"

[[ "${EUID}" -eq 0 ]] || fail "Must be run as root (sudo ./scripts/deploy_local.sh)."
command -v python3   >/dev/null 2>&1 || fail "python3 not found."
command -v npm       >/dev/null 2>&1 || fail "npm not found."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found."
command -v openssl   >/dev/null 2>&1 || fail "openssl not found."
command -v systemctl >/dev/null 2>&1 || fail "systemd not found."
[[ -f "${JARVIS_SOURCE_ROOT}/jarvisappv4.py" ]]   || fail "jarvisappv4.py not found in ${JARVIS_SOURCE_ROOT}. Run from the repo root."
[[ -f "${JARVIS_SOURCE_ROOT}/requirements.txt" ]] || fail "requirements.txt not found."

log "All checks passed."

# =============================================================================
# Guard: don't silently repurpose an existing install.sh (HTTP/jarvis.env) host
# =============================================================================
if systemctl is-active --quiet jarvis.service 2>/dev/null && [[ -f "${LEGACY_ENV_FILE}" ]] && [[ ! -f "${JARVIS_ENV_FILE}" ]]; then
  section "Existing installation detected"
  warn "jarvis.service is currently running against ${LEGACY_ENV_FILE} (the plain-HTTP scripts/install.sh scheme)."
  warn "Continuing will switch it to HTTPS on :443 via ${JARVIS_ENV_FILE} instead — a different port and protocol."
  if ! confirm "Switch this host's jarvis.service over to the TLS scheme?" "N"; then
    info "Aborted. Nothing was changed."
    exit 0
  fi
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
# Environment file
# =============================================================================
section "Environment file"

mkdir -p "${JARVIS_CONFIG_DIR}"
chmod 750 "${JARVIS_CONFIG_DIR}"

if [[ -f "${JARVIS_ENV_FILE}" ]]; then
  log "Using existing ${JARVIS_ENV_FILE}."
else
  cp "${JARVIS_SOURCE_ROOT}/config/jarvis.env.example" "${JARVIS_ENV_FILE}"
  chown root:"${JARVIS_USER}" "${JARVIS_ENV_FILE}" 2>/dev/null || true
  chmod 640 "${JARVIS_ENV_FILE}"
  log "Created ${JARVIS_ENV_FILE} from template."
  warn "Edit ${JARVIS_ENV_FILE} and set JARVIS_PASSPHRASE / JARVIS_DEFAULT_ADMIN_PASSWORD / JARVIS_SECRET_KEY, then re-run this script."
fi

info "Seeding integrity strictness + admin settings path defaults (only if not already set)..."
ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_ORPHANS" "0"
ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT" "0"
ensure_env_default "JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS" "0"
ensure_env_default "JARVIS_ADMIN_SETTINGS_PATH" "/var/lib/jarvis/admin_settings.json"
ensure_env_default "JARVIS_HOST" "0.0.0.0"
ensure_env_default "JARVIS_PORT" "443"
ensure_env_default "JARVIS_TLS_CERT_FILE" "${TLS_DIR}/fullchain.pem"
ensure_env_default "JARVIS_TLS_KEY_FILE" "${TLS_DIR}/privkey.pem"
log "Environment defaults in place."

if ! grep -q "^JARVIS_PASSPHRASE=.\+" "${JARVIS_ENV_FILE}" 2>/dev/null; then
  fail "JARVIS_PASSPHRASE is not set in ${JARVIS_ENV_FILE}. Set it, then re-run."
fi

# shellcheck disable=SC1090
set -a; source "${JARVIS_ENV_FILE}"; set +a
JARVIS_PORT="${JARVIS_PORT:-443}"
JARVIS_TLS_CERT_FILE="${JARVIS_TLS_CERT_FILE:-${TLS_DIR}/fullchain.pem}"
JARVIS_TLS_KEY_FILE="${JARVIS_TLS_KEY_FILE:-${TLS_DIR}/privkey.pem}"

# =============================================================================
# TLS certificate
# =============================================================================
section "TLS certificate"

if [[ -f "${JARVIS_TLS_CERT_FILE}" && -f "${JARVIS_TLS_KEY_FILE}" ]]; then
  log "TLS cert already present at ${JARVIS_TLS_CERT_FILE}."
else
  info "No TLS cert found — generating a self-signed one (replace with a real cert/Let's Encrypt later)..."
  mkdir -p "$(dirname "${JARVIS_TLS_CERT_FILE}")"
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "${JARVIS_TLS_KEY_FILE}" \
    -out "${JARVIS_TLS_CERT_FILE}" \
    -days 825 \
    -subj "/CN=jarvis.local" \
    || fail "openssl certificate generation failed."
  chmod 600 "${JARVIS_TLS_KEY_FILE}"
  chmod 644 "${JARVIS_TLS_CERT_FILE}"
  log "Self-signed certificate generated at ${JARVIS_TLS_CERT_FILE}."
fi

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
  python3.12 -m venv "${VENV_DIR}" 2>/dev/null || python3 -m venv "${VENV_DIR}" \
    || fail "Failed to create virtualenv."
  chown -R "${JARVIS_USER}:${JARVIS_USER}" "${VENV_DIR}"
fi

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
# Systemd service (HTTPS via EnvironmentFile-driven host/port/TLS paths)
# =============================================================================
section "Systemd service"

cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=JARVIS AI Assistant (TLS)
Documentation=https://github.com/lukas/jarvis
After=network.target

[Service]
Type=simple
User=${JARVIS_USER}
WorkingDirectory=${JARVIS_DEPLOY_ROOT}
EnvironmentFile=${JARVIS_ENV_FILE}
AmbientCapabilities=CAP_NET_BIND_SERVICE
CapabilityBoundingSet=CAP_NET_BIND_SERVICE
ExecStart=${VENV_DIR}/bin/uvicorn jarvisappv4:app --host \${JARVIS_HOST} --port \${JARVIS_PORT} --ssl-certfile \${JARVIS_TLS_CERT_FILE} --ssl-keyfile \${JARVIS_TLS_KEY_FILE}
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
# Start + health check
# =============================================================================
section "Start service"

systemctl restart jarvis.service || fail "systemctl restart jarvis.service failed. Check: journalctl -u jarvis -n 50"

info "Waiting for service to come up..."
sleep 3

if ! systemctl is-active --quiet jarvis.service; then
  fail "Service is not active. Check: journalctl -u jarvis -n 50"
fi
log "Service is running."

if curl -kfsS "https://localhost:${JARVIS_PORT}/health" >/dev/null 2>&1; then
  log "Health check OK — https://localhost:${JARVIS_PORT}/health"
else
  warn "Health check did not respond yet at https://localhost:${JARVIS_PORT}/health — check: journalctl -u jarvis -n 50"
fi

systemctl --no-pager --lines=5 status jarvis.service || true

# =============================================================================
# Summary
# =============================================================================
echo
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  JARVIS deploy_local complete${RESET}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
echo -e "  Config:   ${JARVIS_ENV_FILE}"
echo -e "  App:      ${JARVIS_DEPLOY_ROOT}"
echo -e "  Data:     ${JARVIS_DATA_DIR}"
echo -e "  TLS cert: ${JARVIS_TLS_CERT_FILE}"
echo -e "  URL:      https://$(hostname -I | awk '{print $1}' 2>/dev/null || echo 'localhost'):${JARVIS_PORT}"
echo -e "  Logs:     journalctl -u jarvis -f"
echo
echo -e "  Update:   sudo ./scripts/update_local.sh"
echo -e "  Rollback: sudo ./scripts/rollback_local.sh"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
