#!/usr/bin/env bash
# JARVIS quick update — rebuilds frontend + backend, syncs to /opt/jarvis, restarts service.
#
# Usage:
#   bash update.sh              — full update (may prompt for sudo password)
#   bash update.sh --setup-sudo — do this ONCE to never type a password again
#   bash update.sh --frontend   — rebuild and deploy frontend only (faster)
#   bash update.sh --help

set -euo pipefail

# ── Colours ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then
  BOLD='\033[1m'; RESET='\033[0m'
  GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; DIM='\033[2m'
else
  BOLD=''; RESET=''; GREEN=''; YELLOW=''; RED=''; CYAN=''; DIM=''
fi

ok()   { echo -e "  ${GREEN}✓${RESET}  $*"; }
info() { echo -e "  ${DIM}→${RESET}  $*"; }
warn() { echo -e "  ${YELLOW}!${RESET}  $*"; }
fail() { echo -e "\n${RED}${BOLD}✗ $*${RESET}" >&2; exit 1; }
header() { echo -e "\n${BOLD}${CYAN}▶${RESET} ${BOLD}$*${RESET}"; }

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/jarvis"
CURRENT_USER="${SUDO_USER:-${USER}}"
FRONTEND_ONLY=0

# ── Argument handling ─────────────────────────────────────────────────────────
case "${1:-}" in
  --help|-h)
    echo ""
    echo "  ${BOLD}JARVIS update script${RESET}"
    echo ""
    echo "  ${BOLD}bash update.sh${RESET}              Full update (frontend + backend)"
    echo "  ${BOLD}bash update.sh --frontend${RESET}   Frontend-only rebuild (quicker)"
    echo "  ${BOLD}bash update.sh --setup-sudo${RESET} One-time: enable passwordless updates"
    echo ""
    exit 0
    ;;
  --setup-sudo)
    [[ "${EUID}" -eq 0 ]] || fail "Run as root for sudoers setup: sudo bash update.sh --setup-sudo"
    RULE_FILE="/etc/sudoers.d/jarvis-update"
    DEPLOY_CMD="${REPO_DIR}/scripts/deploy.sh"
    SYSTEMCTL_BIN="$(command -v systemctl 2>/dev/null || echo '/usr/bin/systemctl')"
    RSYNC_BIN="$(command -v rsync 2>/dev/null || echo '/usr/bin/rsync')"
    cat > "${RULE_FILE}" << EOF
# Allows ${CURRENT_USER} to update and restart JARVIS without a password
${CURRENT_USER} ALL=(ALL) NOPASSWD: ${DEPLOY_CMD}
${CURRENT_USER} ALL=(ALL) NOPASSWD: ${SYSTEMCTL_BIN} restart jarvis
${CURRENT_USER} ALL=(ALL) NOPASSWD: ${RSYNC_BIN}
${CURRENT_USER} ALL=(ALL) NOPASSWD: /bin/cp
${CURRENT_USER} ALL=(ALL) NOPASSWD: /usr/bin/cp
EOF
    chmod 440 "${RULE_FILE}"
    echo ""
    echo -e "${GREEN}${BOLD}✓ Passwordless sudo set up for ${CURRENT_USER}${RESET}"
    echo -e "  Rule written to ${RULE_FILE}"
    echo -e "  From now on: ${BOLD}bash ${REPO_DIR}/update.sh${RESET} — no password needed."
    echo ""
    exit 0
    ;;
  --frontend)
    FRONTEND_ONLY=1
    ;;
  "")
    ;;
  *)
    fail "Unknown argument: $1 — try --help"
    ;;
esac

# ── Banner ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}  J.A.R.V.I.S. — Update${RESET}"
echo -e "${DIM}  $(date '+%a %d %b %Y %H:%M')${RESET}"
echo ""

# ── Sudo helper ───────────────────────────────────────────────────────────────
# Try to run deploy commands through sudo — if passwordless sudoers is set up
# (via --setup-sudo above) this works silently; otherwise prompts once.
needs_sudo() {
  [[ "${EUID}" -ne 0 ]]
}

run_privileged() {
  if needs_sudo; then
    sudo "$@"
  else
    "$@"
  fi
}

# ── Build frontend ────────────────────────────────────────────────────────────
header "Building frontend"
cd "${REPO_DIR}/frontend"
npm install --silent 2>&1 | grep -v '^npm warn' | sed 's/^/    /' || true
START_TS=$SECONDS
npm run build 2>&1 | grep -E '(✓|✗|dist/|error|ERROR|warning TS)' | sed 's/^/    /' || fail "Frontend build failed"
ok "Built in $((SECONDS - START_TS))s"
cd "${REPO_DIR}"

if [[ "${FRONTEND_ONLY}" -eq 1 ]]; then
  # ── Fast path: copy only the three built files ──────────────────────────────
  header "Deploying frontend files"

  DIST_SRC="${REPO_DIR}/frontend/dist"
  DIST_DST="${INSTALL_DIR}/frontend/dist"

  run_privileged cp "${DIST_SRC}/assets/index.js"  "${DIST_DST}/assets/index.js"
  run_privileged cp "${DIST_SRC}/assets/index.css" "${DIST_DST}/assets/index.css"
  run_privileged cp "${DIST_SRC}/index.html"        "${DIST_DST}/index.html"
  ok "Assets copied to ${DIST_DST}"

  header "Restarting service"
  run_privileged systemctl restart jarvis
  sleep 1
  systemctl is-active --quiet jarvis && ok "jarvis.service is running" || warn "Service may not be healthy — check: journalctl -u jarvis -n 20"
else
  # ── Full path: rsync everything + restart ────────────────────────────────────
  header "Syncing to ${INSTALL_DIR}"
  run_privileged rsync -a --delete \
    --exclude='.git' \
    --exclude='node_modules' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    "${REPO_DIR}/" "${INSTALL_DIR}/" 2>&1 | sed 's/^/    /' || fail "rsync failed"
  ok "Sync complete"

  header "Restarting service"
  run_privileged systemctl restart jarvis
  sleep 2
fi

# ── Health check ─────────────────────────────────────────────────────────────
header "Health check"
PORT="${JARVIS_PORT:-443}"
for url in "https://localhost:${PORT}/health" "http://localhost:${PORT}/health" "http://localhost:8000/health"; do
  if curl -kfsS "${url}" >/dev/null 2>&1; then
    ok "Service healthy at ${url}"
    break
  fi
done

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}  Update complete.${RESET}"
echo -e "${DIM}  Tip: run ${BOLD}bash update.sh --frontend${RESET}${DIM} for frontend-only changes (faster)${RESET}"
if needs_sudo; then
  echo -e "${DIM}  Tip: run ${BOLD}sudo bash update.sh --setup-sudo${RESET}${DIM} once to never type a password again${RESET}"
fi
echo ""
