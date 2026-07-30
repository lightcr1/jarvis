#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Rollback script (TLS / config.env flow)
#
# Companion to scripts/deploy_local.sh / update_local.sh.
#
# Usage:
#   sudo ./scripts/rollback_local.sh              # roll back to last saved SHA
#   sudo ./scripts/rollback_local.sh <git-sha>    # roll back to a specific commit
#   sudo ./scripts/rollback_local.sh HEAD~1       # roll back one commit
#
# Optionally restores the most recent admin-data backup taken by
# update_local.sh (via restore_admin_data.sh), then runs
# check_admin_data_integrity.sh against the result — which itself honors
# JARVIS_INTEGRITY_FAIL_ON_ORPHANS / _ADMIN_LOCKOUT / _DUPLICATE_MEMBERSHIPS
# from /etc/jarvis/config.env, so a rollback onto known-bad data can be made
# to fail loudly instead of quietly succeeding.
#
# Must be run as root (sudo).
# =============================================================================

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JARVIS_ENV_FILE="/etc/jarvis/config.env"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SHA_FILE="/var/lib/jarvis/last_deploy_sha_local"
BACKUP_DIR="/var/lib/jarvis/update_backups"
TARGET_ARG="${1:-previous}"

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

[[ "${EUID}" -eq 0 ]] || fail "Must be run as root (sudo ./scripts/rollback_local.sh)."
command -v systemctl >/dev/null 2>&1 || fail "systemd not found."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v npm       >/dev/null 2>&1 || fail "npm not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found."
[[ -d "${VENV_DIR}" ]]           || fail "Virtualenv not found at ${VENV_DIR}. Run scripts/deploy_local.sh first."
[[ -d "${JARVIS_DEPLOY_ROOT}" ]] || fail "${JARVIS_DEPLOY_ROOT} does not exist. Run scripts/deploy_local.sh first."

log "All checks passed."

# =============================================================================
# Resolve target SHA
# =============================================================================
section "Resolving target commit"

CURRENT_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse HEAD)"
CURRENT_SHORT="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse --short HEAD)"

if [[ "${TARGET_ARG}" == "previous" ]]; then
  [[ -f "${SHA_FILE}" ]] || fail "No previous SHA saved at ${SHA_FILE}. Provide a commit SHA explicitly."
  TARGET_SHA="$(cat "${SHA_FILE}")"
  info "Rolling back to last saved SHA from ${SHA_FILE}."
else
  TARGET_SHA="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse --verify "${TARGET_ARG}")" \
    || fail "Could not resolve '${TARGET_ARG}' to a valid commit."
fi

TARGET_SHORT="$(git -C "${JARVIS_SOURCE_ROOT}" rev-parse --short "${TARGET_SHA}")"

echo
echo -e "  Current : ${CURRENT_SHORT} (${CURRENT_SHA})"
echo -e "  Target  : ${TARGET_SHORT} (${TARGET_SHA})"
echo

if [[ "${TARGET_SHA}" == "${CURRENT_SHA}" ]]; then
  warn "Already at ${TARGET_SHORT}. Nothing to roll back."
  exit 0
fi

if confirm "Roll back from ${CURRENT_SHORT} → ${TARGET_SHORT}?"; then
  info "Proceeding with rollback..."
else
  info "Rollback cancelled."
  exit 0
fi

# =============================================================================
# Optionally restore the most recent admin-data backup
# =============================================================================
section "Admin data"

LATEST_BACKUP="$(ls -t "${BACKUP_DIR}"/jarvis_admin_data_*.tar.gz 2>/dev/null | head -n1 || true)"
if [[ -n "${LATEST_BACKUP}" ]]; then
  if confirm "Restore admin data from most recent backup (${LATEST_BACKUP})?" "N"; then
    bash "${JARVIS_SOURCE_ROOT}/scripts/restore_admin_data.sh" "${LATEST_BACKUP}" \
      || fail "restore_admin_data.sh failed."
    log "Admin data restored from ${LATEST_BACKUP}."
  else
    info "Keeping current admin data as-is."
  fi
else
  info "No admin data backups found at ${BACKUP_DIR} — skipping restore."
fi

# =============================================================================
# Check out target commit
# =============================================================================
section "Checking out ${TARGET_SHORT}"

git -C "${JARVIS_SOURCE_ROOT}" checkout "${TARGET_SHA}" \
  || fail "git checkout ${TARGET_SHA} failed."
log "Checked out ${TARGET_SHORT}."

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

"${VENV_DIR}/bin/pip" install --upgrade pip --quiet
"${VENV_DIR}/bin/pip" install -r "${JARVIS_DEPLOY_ROOT}/requirements.txt" --quiet \
  || fail "pip install failed."
log "Dependencies installed for ${TARGET_SHORT}."

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
# Restart + verify
# =============================================================================
section "Service restart"

info "Restarting jarvis.service..."
systemctl restart jarvis.service || fail "systemctl restart failed. Check: journalctl -u jarvis -n 50"

info "Waiting 5s for service to stabilise..."
sleep 5

if ! systemctl is-active --quiet jarvis.service; then
  fail "Service is not active after rollback to ${TARGET_SHORT}. Check: journalctl -u jarvis -n 50"
fi

log "Service is running."
systemctl --no-pager --lines=5 status jarvis.service || true

# =============================================================================
# Admin data integrity check
# =============================================================================
section "Admin data integrity"

if [[ -f "${JARVIS_ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  set -a; source "${JARVIS_ENV_FILE}"; set +a
fi

info "Running check_admin_data_integrity.sh (honors JARVIS_INTEGRITY_FAIL_ON_* from ${JARVIS_ENV_FILE})..."
bash "${JARVIS_SOURCE_ROOT}/scripts/check_admin_data_integrity.sh"
log "Admin data integrity check passed."

# =============================================================================
# Summary
# =============================================================================
echo
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  JARVIS rollback_local complete${RESET}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
echo -e "  Rolled back from : ${CURRENT_SHORT}"
echo -e "  Now running      : ${TARGET_SHORT}"
echo
warn "Source repo is in detached HEAD state."
echo -e "  To return to main: git -C ${JARVIS_SOURCE_ROOT} checkout main"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
