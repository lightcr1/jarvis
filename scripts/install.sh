#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# JARVIS — Clean install script
# Installs JARVIS to /opt/jarvis as a systemd service running as user jarvis.
# Must be run as root (sudo).
# Idempotent: safe to run multiple times.
# ---------------------------------------------------------------------------

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JARVIS_USER="jarvis"
JARVIS_DATA_DIR="/var/lib/jarvis"
JARVIS_CONFIG_DIR="/etc/jarvis"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SERVICE_SRC="${JARVIS_SOURCE_ROOT}/deploy/jarvis.service"
SERVICE_DST="/etc/systemd/system/jarvis.service"

log()  { echo "[JARVIS] $*"; }
fail() { echo "[JARVIS] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Pre-flight checks
# ---------------------------------------------------------------------------
log "Starting JARVIS install — source: ${JARVIS_SOURCE_ROOT} → deploy: ${JARVIS_DEPLOY_ROOT}"

[[ "${EUID}" -eq 0 ]] || fail "This script must be run as root (sudo ./scripts/install.sh)."

command -v systemctl >/dev/null 2>&1 || fail "systemd is required. Only Linux with systemd is supported."
command -v python3   >/dev/null 2>&1 || fail "python3 is required. Install python3.12 and retry."
command -v npm       >/dev/null 2>&1 || fail "npm is required to build the frontend. Install Node.js and retry."
command -v git       >/dev/null 2>&1 || fail "git is required."

PYTHON_VERSION="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
log "Python version: ${PYTHON_VERSION}"

[[ -f "${SERVICE_SRC}" ]]                    || fail "Service file not found: ${SERVICE_SRC}"
[[ -f "${JARVIS_SOURCE_ROOT}/requirements.txt" ]] || fail "requirements.txt not found in ${JARVIS_SOURCE_ROOT}"
[[ -f "${JARVIS_SOURCE_ROOT}/jarvisappv4.py" ]]   || fail "jarvisappv4.py not found in ${JARVIS_SOURCE_ROOT}"

# ---------------------------------------------------------------------------
# 2. Create jarvis system user
# ---------------------------------------------------------------------------
if id "${JARVIS_USER}" >/dev/null 2>&1; then
  log "System user '${JARVIS_USER}' already exists — skipping creation."
else
  log "Creating system user '${JARVIS_USER}'..."
  useradd --system --no-create-home --shell /usr/sbin/nologin "${JARVIS_USER}" \
    || fail "Failed to create system user '${JARVIS_USER}'."
  log "User '${JARVIS_USER}' created."
fi

# ---------------------------------------------------------------------------
# 3. Create data and config directories
# ---------------------------------------------------------------------------
log "Creating data directory ${JARVIS_DATA_DIR}..."
mkdir -p "${JARVIS_DATA_DIR}"
chown "${JARVIS_USER}:${JARVIS_USER}" "${JARVIS_DATA_DIR}"
chmod 750 "${JARVIS_DATA_DIR}"

log "Creating config directory ${JARVIS_CONFIG_DIR}..."
mkdir -p "${JARVIS_CONFIG_DIR}"
chmod 750 "${JARVIS_CONFIG_DIR}"

if [[ ! -f "${JARVIS_CONFIG_DIR}/jarvis.env" ]]; then
  log "Copying env template to ${JARVIS_CONFIG_DIR}/jarvis.env..."
  cp "${JARVIS_SOURCE_ROOT}/config/prod.env.example" "${JARVIS_CONFIG_DIR}/jarvis.env"
  chown root:"${JARVIS_USER}" "${JARVIS_CONFIG_DIR}/jarvis.env"
  chmod 640 "${JARVIS_CONFIG_DIR}/jarvis.env"
  log "IMPORTANT: Edit /etc/jarvis/jarvis.env and set JARVIS_PASSPHRASE and API keys before starting."
else
  log "${JARVIS_CONFIG_DIR}/jarvis.env already exists — not overwriting."
fi

# ---------------------------------------------------------------------------
# 4. Copy/sync project files to /opt/jarvis
# ---------------------------------------------------------------------------
log "Syncing project files to ${JARVIS_DEPLOY_ROOT}..."
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
log "Project files synced."

# ---------------------------------------------------------------------------
# 5. Create Python virtualenv
# ---------------------------------------------------------------------------
if [[ -d "${VENV_DIR}" ]]; then
  log "Virtualenv already exists at ${VENV_DIR} — skipping creation."
else
  log "Creating Python virtualenv at ${VENV_DIR}..."
  python3 -m venv "${VENV_DIR}" || fail "Failed to create virtualenv at ${VENV_DIR}."
  chown -R "${JARVIS_USER}:${JARVIS_USER}" "${VENV_DIR}"
fi

# ---------------------------------------------------------------------------
# 6. Install Python dependencies
# ---------------------------------------------------------------------------
log "Installing Python dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${JARVIS_DEPLOY_ROOT}/requirements.txt" --quiet \
  || fail "pip install -r requirements.txt failed."
log "Python dependencies installed."

# ---------------------------------------------------------------------------
# 7. Build frontend
# ---------------------------------------------------------------------------
log "Building frontend..."
pushd "${JARVIS_DEPLOY_ROOT}/frontend" >/dev/null
npm ci --silent  || fail "npm ci failed in frontend/."
npm run build    || fail "npm run build failed in frontend/."
popd >/dev/null
log "Frontend build complete."

# ---------------------------------------------------------------------------
# 8. Install and enable systemd service
# ---------------------------------------------------------------------------
log "Installing systemd service to ${SERVICE_DST}..."
install -m 0644 "${SERVICE_SRC}" "${SERVICE_DST}" || fail "Failed to install service file."

log "Running systemctl daemon-reload..."
systemctl daemon-reload || fail "systemctl daemon-reload failed."

log "Enabling jarvis.service..."
systemctl enable jarvis.service || fail "systemctl enable failed."

# ---------------------------------------------------------------------------
# 9. Print next steps
# ---------------------------------------------------------------------------
echo ""
echo "======================================================"
echo "[JARVIS] Install complete."
echo ""
echo "Before starting the service:"
echo "  1. Edit /etc/jarvis/jarvis.env"
echo "     — Set JARVIS_PASSPHRASE (required)"
echo "     — Set OPENAI_API_KEY or GEMINI_API_KEY (required for LLM)"
echo "     — Set JARVIS_DEFAULT_ADMIN_PASSWORD (required)"
echo ""
echo "Then start and verify:"
echo "  sudo systemctl start jarvis"
echo "  sudo systemctl status jarvis"
echo "  curl http://localhost:8000/health"
echo "======================================================"
