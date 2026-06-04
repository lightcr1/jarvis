#!/usr/bin/env bash
set -euo pipefail

# ---------------------------------------------------------------------------
# JARVIS — Rollback script
# Usage:
#   sudo ./scripts/rollback.sh              # roll back to last_deploy_sha
#   sudo ./scripts/rollback.sh <git-sha>    # roll back to a specific commit
#   sudo ./scripts/rollback.sh HEAD~1       # roll back to HEAD~1
# ---------------------------------------------------------------------------

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SHA_FILE="/var/lib/jarvis/last_deploy_sha"
TARGET_ARG="${1:-previous}"

log()  { echo "[JARVIS] $*"; }
fail() { echo "[JARVIS] ERROR: $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
[[ "${EUID}" -eq 0 ]] || fail "This script must be run as root (sudo ./scripts/rollback.sh)."

command -v systemctl >/dev/null 2>&1 || fail "systemd not found."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v npm       >/dev/null 2>&1 || fail "npm not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found. Install rsync and retry."

[[ -d "${VENV_DIR}" ]]       || fail "Virtualenv not found at ${VENV_DIR}. Run scripts/install.sh first."
[[ -d "${JARVIS_DEPLOY_ROOT}" ]] || fail "${JARVIS_DEPLOY_ROOT} does not exist. Run scripts/install.sh first."

# ---------------------------------------------------------------------------
# 1. Resolve target SHA
# ---------------------------------------------------------------------------
if [[ "${TARGET_ARG}" == "previous" ]]; then
  [[ -f "${SHA_FILE}" ]] || fail "No previous deploy SHA found at ${SHA_FILE}. Provide a commit SHA explicitly."
  TARGET_SHA="$(cat "${SHA_FILE}")"
  log "Rolling back to previous deploy SHA from ${SHA_FILE}: ${TARGET_SHA}"
elif [[ "${TARGET_ARG}" == "HEAD~1" ]]; then
  TARGET_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD~1)" \
    || fail "Failed to resolve HEAD~1. Are there at least two commits?"
  log "Rolling back to HEAD~1: ${TARGET_SHA}"
else
  TARGET_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse --verify "${TARGET_ARG}")" \
    || fail "Git SHA not found: ${TARGET_ARG}"
  log "Rolling back to specified SHA: ${TARGET_SHA}"
fi

CURRENT_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD)"
log "Current SHA: ${CURRENT_SHA}"

if [[ "${TARGET_SHA}" == "${CURRENT_SHA}" ]]; then
  fail "Target SHA ${TARGET_SHA} is already the current HEAD. Nothing to roll back to."
fi

# ---------------------------------------------------------------------------
# 2. Check out target commit in source repo
# ---------------------------------------------------------------------------
log "Checking out ${TARGET_SHA} in source repo..."
git -C "${JARVIS_SOURCE_ROOT}" checkout "${TARGET_SHA}" \
  || fail "git checkout ${TARGET_SHA} failed."

# ---------------------------------------------------------------------------
# 3. Sync rolled-back files to /opt/jarvis
# ---------------------------------------------------------------------------
log "Syncing rolled-back files to ${JARVIS_DEPLOY_ROOT}..."
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
# 4. Reinstall Python dependencies
# ---------------------------------------------------------------------------
log "Reinstalling Python dependencies for ${TARGET_SHA}..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${JARVIS_DEPLOY_ROOT}/requirements.txt" --quiet \
  || fail "pip install -r requirements.txt failed."
log "Python dependencies installed."

# ---------------------------------------------------------------------------
# 5. Rebuild frontend
# ---------------------------------------------------------------------------
log "Rebuilding frontend for ${TARGET_SHA}..."
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
# 7. Verify service is active
# ---------------------------------------------------------------------------
log "Waiting 5 seconds for service to stabilise..."
sleep 5

if ! systemctl is-active --quiet jarvis.service; then
  fail "Service is not active after rollback to ${TARGET_SHA}. Check: journalctl -u jarvis -n 50"
fi

systemctl --no-pager --full status jarvis.service || true

echo ""
echo "======================================================"
echo "[JARVIS] Rollback complete."
echo "  Rolled back from : ${CURRENT_SHA}"
echo "  Now running      : ${TARGET_SHA}"
echo ""
echo "Note: the source repo is now in detached HEAD state."
echo "  To return to the main branch: git -C ${JARVIS_SOURCE_ROOT} checkout main"
echo "======================================================"
