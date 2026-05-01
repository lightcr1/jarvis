#!/usr/bin/env bash
# Quick redeploy: rebuild frontend, sync to /opt/jarvis, restart service.
# Full first-time setup: use deploy_local.sh instead.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="/opt/jarvis"

fail() { echo "ERROR: $*" >&2; exit 1; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo $0"
command -v rsync >/dev/null 2>&1   || fail "rsync not found"
command -v npm   >/dev/null 2>&1   || fail "npm not found"
command -v systemctl >/dev/null 2>&1 || fail "systemctl not found"

echo "==> Building frontend…"
pushd "${REPO_DIR}/frontend" >/dev/null
npm install --silent
npm run build
popd >/dev/null

echo "==> Syncing repo to ${INSTALL_DIR}…"
rsync -a --delete \
  --exclude='.git' \
  --exclude='node_modules' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  "${REPO_DIR}/" "${INSTALL_DIR}/"

echo "==> Restarting jarvis.service…"
systemctl restart jarvis.service

echo "==> Waiting for health check…"
sleep 2
PORT="${JARVIS_PORT:-443}"
if curl -kfsS "https://localhost:${PORT}/health" >/dev/null 2>&1; then
  echo "OK — https://localhost:${PORT}/health"
elif curl -fsS "http://localhost:${PORT}/health" >/dev/null 2>&1; then
  echo "OK — http://localhost:${PORT}/health"
else
  fail "Health check failed after restart"
fi

echo ""
echo "Deploy complete."
