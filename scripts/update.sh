#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# JARVIS — In-place update script
# Pulls latest code to /opt/jarvis, reinstalls deps, rebuilds frontend,
# restarts the service, and auto-rolls back if the service fails to start.
# Must be run as root (sudo).
# ---------------------------------------------------------------------------

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SHA_FILE="/var/lib/jarvis/last_deploy_sha"
BRANCH="${JARVIS_BRANCH:-main}"

log()  { echo "[JARVIS] $*"; }
fail() { echo "[JARVIS] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
[[ "${EUID}" -eq 0 ]] || fail "This script must be run as root (sudo ./scripts/update.sh)."

command -v systemctl >/dev/null 2>&1 || fail "systemd not found."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v npm       >/dev/null 2>&1 || fail "npm not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found. Install rsync and retry."

[[ -d "${VENV_DIR}" ]]                              || fail "Virtualenv not found at ${VENV_DIR}. Run scripts/install.sh first."
[[ -f "${JARVIS_SOURCE_ROOT}/requirements.txt" ]]   || fail "requirements.txt not found in ${JARVIS_SOURCE_ROOT}."
[[ -d "${JARVIS_DEPLOY_ROOT}" ]]                    || fail "${JARVIS_DEPLOY_ROOT} does not exist. Run scripts/install.sh first."

# ---------------------------------------------------------------------------
# 1. Save current SHA for rollback
# ---------------------------------------------------------------------------
log "Capturing current SHA for rollback reference..."
mkdir -p "$(dirname "${SHA_FILE}")"
git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD > "${SHA_FILE}" \
  || fail "Failed to capture current git SHA."
PREV_SHA="$(cat "${SHA_FILE}")"
log "Previous SHA: ${PREV_SHA} → saved to ${SHA_FILE}"

# ---------------------------------------------------------------------------
# 2. Pull latest code
# ---------------------------------------------------------------------------
log "Pulling latest from origin/${BRANCH}..."
git -C "${JARVIS_SOURCE_ROOT}" pull origin "${BRANCH}" \
  || fail "git pull origin ${BRANCH} failed."
NEW_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD)"
log "New SHA: ${NEW_SHA}"

# ---------------------------------------------------------------------------
# 3. Sync project files to /opt/jarvis
# ---------------------------------------------------------------------------
log "Syncing updated files to ${JARVIS_DEPLOY_ROOT}..."
rsync -a --delete \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='frontend/node_modules' \
  --exclude='frontend/dist' \
  "${JARVIS_SOURCE_ROOT}/" "${JARVIS_DEPLOY_ROOT}/"
chown -R jarvis:jarvis "${JARVIS_DEPLOY_ROOT}"
log "Files synced."

# ---------------------------------------------------------------------------
# 4. Install Python dependencies
# ---------------------------------------------------------------------------
log "Installing Python dependencies..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${JARVIS_DEPLOY_ROOT}/requirements.txt" --quiet \
  || fail "pip install -r requirements.txt failed."
log "Python dependencies up to date."

# ---------------------------------------------------------------------------
# 5. Rebuild frontend
# ---------------------------------------------------------------------------
log "Rebuilding frontend..."
pushd "${JARVIS_DEPLOY_ROOT}/frontend" >/dev/null
npm ci --silent || fail "npm ci failed in frontend/."
npm run build   || fail "npm run build failed in frontend/."
popd >/dev/null
log "Frontend build complete."

# ---------------------------------------------------------------------------
# 6. Restart service
# ---------------------------------------------------------------------------
log "Restarting jarvis.service..."
systemctl restart jarvis.service || fail "systemctl restart jarvis failed."

# ---------------------------------------------------------------------------
# 7. Health check — auto-rollback if service fails to come up
# ---------------------------------------------------------------------------
log "Waiting 5 seconds for service to stabilise..."
sleep 5

if ! systemctl is-active --quiet jarvis.service; then
  log "Service is not active after restart — triggering auto-rollback to ${PREV_SHA}..."
  echo "${PREV_SHA}" > "${SHA_FILE}"
  bash "${JARVIS_SOURCE_ROOT}/scripts/rollback.sh" "${PREV_SHA}" || true
  fail "Update failed: service did not come up. Rolled back to ${PREV_SHA}."
fi

systemctl --no-pager --full status jarvis.service || true

echo ""
echo "======================================================"
echo "[JARVIS] Update complete."
echo "  Previous SHA : ${PREV_SHA}"
echo "  Current SHA  : ${NEW_SHA}"
echo "======================================================"
