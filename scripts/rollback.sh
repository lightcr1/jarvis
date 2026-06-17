#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Rollback script
#
# Usage:
#   sudo ./scripts/rollback.sh              # roll back to last saved SHA
#   sudo ./scripts/rollback.sh <git-sha>    # roll back to a specific commit
#   sudo ./scripts/rollback.sh HEAD~1       # roll back one commit
#
# Must be run as root (sudo).
# =============================================================================

JARVIS_DEPLOY_ROOT="/opt/jarvis"
JARVIS_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${JARVIS_DEPLOY_ROOT}/.venv"
SHA_FILE="/var/lib/jarvis/last_deploy_sha"
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

[[ "${EUID}" -eq 0 ]] || fail "Must be run as root (sudo ./scripts/rollback.sh)."
command -v systemctl >/dev/null 2>&1 || fail "systemd not found."
command -v git       >/dev/null 2>&1 || fail "git not found."
command -v npm       >/dev/null 2>&1 || fail "npm not found."
command -v rsync     >/dev/null 2>&1 || fail "rsync not found."
[[ -d "${VENV_DIR}" ]]           || fail "Virtualenv not found at ${VENV_DIR}. Run scripts/install.sh first."
[[ -d "${JARVIS_DEPLOY_ROOT}" ]] || fail "${JARVIS_DEPLOY_ROOT} does not exist. Run scripts/install.sh first."

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

# =============================================================================
# Confirm
# =============================================================================
if confirm "Roll back from ${CURRENT_SHORT} → ${TARGET_SHORT}?"; then
  info "Proceeding with rollback..."
else
  info "Rollback cancelled."
  exit 0
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
# Summary
# =============================================================================
echo
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  JARVIS rollback complete${RESET}"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
echo -e "  Rolled back from : ${CURRENT_SHORT}"
echo -e "  Now running      : ${TARGET_SHORT}"
echo
warn "Source repo is in detached HEAD state."
echo -e "  To return to main: git -C ${JARVIS_SOURCE_ROOT} checkout main"
echo -e "${BOLD}${GREEN}══════════════════════════════════════════════════${RESET}"
echo
