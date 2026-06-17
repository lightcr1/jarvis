#!/usr/bin/env bash
# scripts/setup-https.sh — One-time HTTPS setup for JARVIS using mkcert (LAN / self-signed CA)
#
# What this script does:
#   1. Installs mkcert (if not present) and trusts its local CA
#   2. Creates /etc/jarvis/ssl/ and generates a cert for jarvissrv01 + localhost
#   3. Enables the JARVIS nginx site and disables the nginx default site
#   4. Validates and reloads nginx
#
# Run once as root: sudo bash scripts/setup-https.sh
#
# For public-domain HTTPS, see: scripts/setup-https-letsencrypt.sh
set -euo pipefail

JARVIS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSL_DIR="/etc/jarvis/ssl"
NGINX_SITES_AVAILABLE="/etc/nginx/sites-available"
NGINX_SITES_ENABLED="/etc/nginx/sites-enabled"
JARVIS_CONF="${JARVIS_ROOT}/deploy/nginx/jarvis.conf"
MKCERT_VERSION="v1.4.4"
MKCERT_BIN="/usr/local/bin/mkcert"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[JARVIS]${RESET} $*"; }
step() { echo -e "${CYAN}[JARVIS]${RESET} $*"; }
fail() { echo -e "${RED}[JARVIS] ERROR:${RESET} $*" >&2; exit 1; }

# -------------------------------------------------------
# 1. Require root
# -------------------------------------------------------
[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash ${BASH_SOURCE[0]}"

# -------------------------------------------------------
# 2. Require nginx
# -------------------------------------------------------
command -v nginx >/dev/null 2>&1 || fail "nginx is not installed. Install it first: apt install nginx"
[[ -d "${NGINX_SITES_ENABLED}" ]] || fail "nginx sites-enabled directory not found at ${NGINX_SITES_ENABLED}"

# -------------------------------------------------------
# 3. Install mkcert if not present
# -------------------------------------------------------
if command -v mkcert >/dev/null 2>&1; then
    ok "mkcert already installed at $(command -v mkcert)"
else
    step "Downloading mkcert ${MKCERT_VERSION}..."
    MKCERT_URL="https://github.com/FiloSottile/mkcert/releases/download/${MKCERT_VERSION}/mkcert-${MKCERT_VERSION}-linux-amd64"
    curl -fsSL "${MKCERT_URL}" -o "${MKCERT_BIN}" \
        || fail "Failed to download mkcert from ${MKCERT_URL}"
    chmod +x "${MKCERT_BIN}"
    ok "mkcert installed at ${MKCERT_BIN}"
fi

# -------------------------------------------------------
# 4. Install local CA (idempotent — mkcert skips if already installed)
# -------------------------------------------------------
step "Installing mkcert local CA..."
mkcert -install
ok "Local CA trusted."

# -------------------------------------------------------
# 5. Create SSL directory
# -------------------------------------------------------
step "Creating ${SSL_DIR}..."
mkdir -p "${SSL_DIR}"
chmod 750 "${SSL_DIR}"
ok "SSL directory ready."

# -------------------------------------------------------
# 6. Generate cert (idempotent — overwrites existing cert)
# -------------------------------------------------------
step "Generating TLS certificate for jarvissrv01, jarvissrv01.local, localhost, 127.0.0.1..."
mkcert \
    -key-file  "${SSL_DIR}/key.pem" \
    -cert-file "${SSL_DIR}/cert.pem" \
    jarvissrv01 jarvissrv01.local localhost 127.0.0.1
chmod 640 "${SSL_DIR}/key.pem"
chmod 644 "${SSL_DIR}/cert.pem"
ok "Certificate written to ${SSL_DIR}/cert.pem"

# -------------------------------------------------------
# 7. Enable JARVIS nginx site
# -------------------------------------------------------
[[ -f "${JARVIS_CONF}" ]] || fail "Nginx config not found at ${JARVIS_CONF} — check that deploy/nginx/jarvis.conf exists"

step "Enabling JARVIS nginx site..."
ln -sf "${JARVIS_CONF}" "${NGINX_SITES_ENABLED}/jarvis"
ok "Symlink created: ${NGINX_SITES_ENABLED}/jarvis → ${JARVIS_CONF}"

# -------------------------------------------------------
# 8. Disable default nginx site if present
# -------------------------------------------------------
if [[ -L "${NGINX_SITES_ENABLED}/default" ]]; then
    step "Disabling default nginx site..."
    rm -f "${NGINX_SITES_ENABLED}/default"
    ok "Default site disabled."
else
    ok "Default site not present — nothing to disable."
fi

# -------------------------------------------------------
# 9. Test and reload nginx
# -------------------------------------------------------
step "Testing nginx config..."
nginx -t || fail "nginx config test failed — check the output above"
ok "nginx config valid."

step "Reloading nginx..."
systemctl reload nginx || fail "nginx reload failed — check: journalctl -u nginx -n 20"
ok "nginx reloaded."

# -------------------------------------------------------
# 10. Success
# -------------------------------------------------------
echo
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  HTTPS setup complete${RESET}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo
echo -e "  ${CYAN}https://jarvissrv01${RESET}"
echo -e "  ${CYAN}https://jarvissrv01.local${RESET}"
echo -e "  ${CYAN}https://localhost${RESET}"
echo
echo -e "  The mkcert CA cert must be trusted on each client browser."
echo -e "  Run 'mkcert -CAROOT' to find the CA cert path, then install"
echo -e "  it on your phones/laptops for the browser warning to disappear."
echo
echo -e "  For public domain HTTPS: see ${CYAN}scripts/setup-https-letsencrypt.sh${RESET}"
echo
