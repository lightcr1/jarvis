#!/usr/bin/env bash
# JARVIS local deploy — builds frontend and syncs source → /opt/jarvis, then restarts.
# Run with: sudo bash /home/jarvis/jarvis/deploy.sh
set -euo pipefail

SRC="/home/jarvis/jarvis"
DEPLOY="/opt/jarvis"
FRONTEND="${SRC}/frontend"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[✓]${RESET} $*"; }
step() { echo -e "${CYAN}[→]${RESET} $*"; }
fail() { echo -e "${RED}[✗] $*${RESET}"; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash ${SRC}/deploy.sh"
[[ -f "${SRC}/jarvisappv4.py" ]] || fail "Source not found at ${SRC}"
[[ -d "${DEPLOY}" ]] || fail "${DEPLOY} does not exist — run install.sh first"

# 1. Build frontend
step "Building frontend..."
chown -R jarvis:jarvis "${FRONTEND}/dist" 2>/dev/null || true
cd "${FRONTEND}"
sudo -u jarvis npm run build || npm run build || fail "npm run build failed"
ok "Frontend built."

# 2. Sync source → deploy (excluding venv/git/node_modules, INCLUDE new dist)
step "Syncing ${SRC} → ${DEPLOY}..."
rsync -a --delete \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='frontend/node_modules' \
  "${SRC}/" "${DEPLOY}/"
chown -R jarvis:jarvis "${DEPLOY}"
ok "Files synced."

# 3. Install any new Python deps
step "Checking Python dependencies..."
"${DEPLOY}/.venv/bin/pip" install -q --upgrade pip
"${DEPLOY}/.venv/bin/pip" install -q -r "${DEPLOY}/requirements.txt" || fail "pip install failed"
ok "Dependencies up to date."

# 4. Restart
step "Restarting jarvis.service..."
systemctl restart jarvis.service || fail "systemctl restart failed — check: journalctl -u jarvis -n 30"
sleep 3
systemctl is-active --quiet jarvis.service || fail "Service not active after restart — check: journalctl -u jarvis -n 30"
ok "Service running."

# 5. Reload nginx if it is installed and the jarvis site is enabled
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/jarvis"
if command -v nginx >/dev/null 2>&1 && [[ -L "${NGINX_SITE_ENABLED}" || -f "${NGINX_SITE_ENABLED}" ]]; then
    step "nginx detected with jarvis site enabled — testing config..."
    nginx -t || fail "nginx config test failed — fix ${SRC}/deploy/nginx/jarvis.conf before continuing"
    systemctl reload nginx || fail "nginx reload failed — check: journalctl -u nginx -n 20"
    ok "nginx reloaded."
fi

echo
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Deploy complete${RESET}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
IP=$(hostname -I | awk '{print $1}' 2>/dev/null || echo "localhost")
if command -v nginx >/dev/null 2>&1 && [[ -L "${NGINX_SITE_ENABLED}" || -f "${NGINX_SITE_ENABLED}" ]]; then
    echo -e "  ${CYAN}https://${IP}${RESET}  (via nginx)"
else
    echo -e "  ${CYAN}http://${IP}:8000${RESET}  (direct, nginx not configured)"
fi
echo
