#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Update script (TLS / config.env flow)
#
# Companion to scripts/deploy_local.sh. First-time setup: run
# scripts/deploy_local.sh instead — this script assumes that has already
# been done (system user, venv, TLS cert, /etc/jarvis/config.env, systemd
# unit all in place).
#
# Backs up admin data, pulls the latest code, reinstalls deps, rebuilds
# frontend, restarts the service, and auto-rolls back (via
# scripts/rollback_local.sh) if the service fails to come back up.
# Must be run as root (sudo ./scripts/update_local.sh).
# =============================================================================

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JARVIS_CONFIG_DIR="/etc/jarvis"
JARVIS_ENV_FILE="${JARVIS_CONFIG_DIR}/config.env"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SHA_FILE="/var/lib/jarvis/last_deploy_sha_local"
BACKUP_DIR="/var/lib/jarvis/update_backups"
BRANCH="${JARVIS_BRANCH:-main}"

# --local flag: skip git pull, just sync source dir + rebuild + restart
LOCAL_ONLY=0
for arg in "$@"; do [[ "${arg}" == "--local" ]] && LOCAL_ONLY=1; done

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

# =============================================================================
# Pre-flight
# =============================================================================
section "Pre-flight checks"

[[ "${EUID}" -eq 0 ]] || fail "Must be run as root (sudo ./scripts/update_local.sh)."
command -v systemctl >/dev/null 2>&1 || fail "systemd not found."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v npm       >/dev/null 2>&1 || fail "npm not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found."
[[ -d "${VENV_DIR}" ]]           || fail "Virtualenv not found at ${VENV_DIR}. Run scripts/deploy_local.sh first."
[[ -d "${JARVIS_DEPLOY_ROOT}" ]] || fail "${JARVIS_DEPLOY_ROOT} does not exist. Run scripts/deploy_local.sh first."
[[ -f "${JARVIS_ENV_FILE}" ]]    || fail "${JARVIS_ENV_FILE} not found. Run scripts/deploy_local.sh first."

log "All checks passed."

# =============================================================================
# Show current state + confirm
# =============================================================================
section "Current state"

CURRENT_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD 2>/dev/null || echo 'unknown')"
CURRENT_SHORT="${CURRENT_SHA:0:7}"
REMOTE_SHA=""
if [[ "${LOCAL_ONLY}" -eq 0 ]]; then
  REMOTE_SHA="$(sudo -u jarvis -H git -C "${JARVIS_SOURCE_ROOT}" ls-remote origin "refs/heads/${BRANCH}" 2>/dev/null | awk '{print $1}')"
fi
REMOTE_SHORT="${REMOTE_SHA:0:7}"

SERVICE_STATUS="stopped"
systemctl is-active --quiet jarvis.service 2>/dev/null && SERVICE_STATUS="running"

echo
echo -e "  Source       : ${JARVIS_SOURCE_ROOT}"
echo -e "  Current SHA  : ${CURRENT_SHORT} (${CURRENT_SHA})"
[[ "${LOCAL_ONLY}" -eq 0 ]] && echo -e "  Remote SHA   : ${REMOTE_SHORT:-unknown} (origin/${BRANCH})"
echo -e "  Service      : ${SERVICE_STATUS}"
echo

if [[ "${LOCAL_ONLY}" -eq 1 ]]; then
  info "--local mode: skipping git pull, deploying ${JARVIS_SOURCE_ROOT} as-is."
  if ! confirm "Deploy local source to ${JARVIS_DEPLOY_ROOT} and restart?"; then
    info "Aborted."
    exit 0
  fi
elif [[ -z "${REMOTE_SHA}" ]]; then
  warn "Branch '${BRANCH}' not found on remote — deploying local source as-is."
  if ! confirm "Deploy local source to ${JARVIS_DEPLOY_ROOT} and restart?"; then
    info "Aborted."
    exit 0
  fi
elif [[ "${REMOTE_SHA}" == "${CURRENT_SHA}" ]]; then
  warn "Already up to date with origin/${BRANCH}."
  if ! confirm "Deploy anyway (re-sync + restart)?"; then
    info "Nothing to do."
    exit 0
  fi
fi

# =============================================================================
# Back up admin data before touching anything
# =============================================================================
section "Backing up admin data"

mkdir -p "${BACKUP_DIR}"
JARVIS_ADMIN_SETTINGS_PATH="${JARVIS_ADMIN_SETTINGS_PATH:-}" \
  bash "${JARVIS_SOURCE_ROOT}/scripts/backup_admin_data.sh" "${BACKUP_DIR}" \
  || warn "backup_admin_data.sh found nothing to back up (fine on a brand-new install)."
log "Admin data backup step complete → ${BACKUP_DIR}"

# =============================================================================
# Save rollback SHA
# =============================================================================
section "Saving rollback checkpoint"

mkdir -p "$(dirname "${SHA_FILE}")"
echo "${CURRENT_SHA}" > "${SHA_FILE}"
log "Rollback SHA saved: ${CURRENT_SHORT} → ${SHA_FILE}"

# =============================================================================
# Pull latest (skipped in --local mode or when no remote tracking)
# =============================================================================
NEW_SHA="${CURRENT_SHA}"
NEW_SHORT="${CURRENT_SHORT}"

if [[ "${LOCAL_ONLY}" -eq 0 && -n "${REMOTE_SHA}" && "${REMOTE_SHA}" != "${CURRENT_SHA}" ]]; then
  section "Pulling origin/${BRANCH}"
  sudo -u jarvis -H git -C "${JARVIS_SOURCE_ROOT}" pull origin "${BRANCH}" \
    || fail "git pull origin ${BRANCH} failed."
  NEW_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD)"
  NEW_SHORT="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse --short HEAD)"
  log "Updated to ${NEW_SHORT}"
else
  info "Deploying local source at ${CURRENT_SHORT}."
fi

# =============================================================================
# Sync files
# =============================================================================
section "Syncing files → ${JARVIS_DEPLOY_ROOT}"

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

# =============================================================================
# Python dependencies
# =============================================================================
section "Python dependencies"

info "Running pip install..."
"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${JARVIS_DEPLOY_ROOT}/requirements.txt" --quiet \
  || fail "pip install failed."
log "Dependencies up to date."

# =============================================================================
# Frontend build
# =============================================================================
section "Frontend build"

info "Running npm ci + npm run build..."
pushd "${JARVIS_DEPLOY_ROOT}/frontend" >/dev/null
npm ci --silent || fail "npm ci failed."
npm run build   || fail "npm run build failed."
popd >/dev/null
log "Frontend built."

# =============================================================================
# Restart + health check
# =============================================================================
section "Service restart"

info "Restarting jarvis.service..."
systemctl restart jarvis.service || {
  warn "Restart failed — triggering rollback to ${CURRENT_SHORT}..."
  bash "${JARVIS_SOURCE_ROOT}/scripts/rollback_local.sh" "${CURRENT_SHA}" || true
  fail "Restart failed. Rolled back to ${CURRENT_SHORT}."
}

info "Waiting 5s for service to stabilise..."
sleep 5

if ! systemctl is-active --quiet jarvis.service; then
  warn "Service is not active — triggering rollback to ${CURRENT_SHORT}..."
  bash "${JARVIS_SOURCE_ROOT}/scripts/rollback_local.sh" "${CURRENT_SHA}" || true
  fail "Update failed: service did not come up. Rolled back to ${CURRENT_SHORT}."
fi

log "Service is running."
systemctl --no-pager --lines=5 status jarvis.service || true

# =============================================================================
# Summary
# =============================================================================
echo
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  JARVIS update_local complete${RESET}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
echo -e "  Previous : ${CURRENT_SHORT}"
echo -e "  Now      : ${NEW_SHORT}"
echo -e "  Backup   : ${BACKUP_DIR}"
echo
echo -e "  Logs:   journalctl -u jarvis -f"
echo -e "  Revert: sudo ./scripts/rollback_local.sh   (rolls back to ${CURRENT_SHORT})"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
