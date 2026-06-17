#!/usr/bin/env bash
# scripts/setup-https-letsencrypt.sh — Switch JARVIS to Let's Encrypt HTTPS for a public domain
#
# Usage: sudo bash scripts/setup-https-letsencrypt.sh <your-domain.com>
#
# What this script does:
#   1. Validates that a domain argument is provided
#   2. Installs certbot with the nginx plugin (if not present)
#   3. Obtains a Let's Encrypt certificate via the nginx plugin
#   4. Patches the nginx config ssl_certificate paths to the new cert
#   5. Tests and reloads nginx
#   6. Installs a systemd timer (or cron) for auto-renewal
#
# Prerequisites:
#   - DNS A record for <domain> pointing to this server's public IP
#   - Port 80 open to the internet (certbot HTTP-01 challenge)
#   - scripts/setup-https.sh must have been run first (creates /etc/jarvis/ssl/ structure)
#
# Idempotent: running again re-issues or renews the cert and re-patches paths.
set -euo pipefail

JARVIS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGINX_CONF="${JARVIS_ROOT}/deploy/nginx/jarvis.conf"
NGINX_SITE_ENABLED="/etc/nginx/sites-enabled/jarvis"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; RESET='\033[0m'
ok()   { echo -e "${GREEN}[JARVIS]${RESET} $*"; }
step() { echo -e "${CYAN}[JARVIS]${RESET} $*"; }
fail() { echo -e "${RED}[JARVIS] ERROR:${RESET} $*" >&2; exit 1; }

# -------------------------------------------------------
# 1. Require root
# -------------------------------------------------------
[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash ${BASH_SOURCE[0]} <domain>"

# -------------------------------------------------------
# 2. Require domain argument
# -------------------------------------------------------
[[ "${#}" -ge 1 ]] || fail "Usage: sudo bash ${BASH_SOURCE[0]} <domain>  (e.g. jarvis.example.com)"
DOMAIN="${1}"
[[ "${DOMAIN}" =~ ^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z]{2,})+$ ]] \
    || fail "Invalid domain: ${DOMAIN}"

# -------------------------------------------------------
# 3. Require nginx
# -------------------------------------------------------
command -v nginx >/dev/null 2>&1 || fail "nginx is not installed"
[[ -f "${NGINX_CONF}" ]]         || fail "Nginx config not found at ${NGINX_CONF}"

# -------------------------------------------------------
# 4. Install certbot + nginx plugin
# -------------------------------------------------------
if command -v certbot >/dev/null 2>&1; then
    ok "certbot already installed at $(command -v certbot)"
else
    step "Installing certbot and python3-certbot-nginx..."
    apt-get update -qq
    apt-get install -y certbot python3-certbot-nginx \
        || fail "apt install certbot failed"
    ok "certbot installed."
fi

# -------------------------------------------------------
# 5. Update nginx server_name to include the public domain
#    (certbot needs to see the domain in the config)
# -------------------------------------------------------
step "Patching server_name in ${NGINX_CONF} to include ${DOMAIN}..."
# Use sed to add domain if it's not already listed.
# Match the server_name line inside the SSL server block (the one with listen 443).
# Strategy: replace the existing server_name line with one that includes the new domain.
if grep -q "${DOMAIN}" "${NGINX_CONF}"; then
    ok "Domain ${DOMAIN} already in nginx config — skipping server_name patch."
else
    sed -i "s|server_name jarvissrv01 jarvissrv01.local localhost;|server_name jarvissrv01 jarvissrv01.local localhost ${DOMAIN};|g" "${NGINX_CONF}"
    ok "Added ${DOMAIN} to server_name."
fi

# Ensure the site symlink exists
if [[ ! -L "${NGINX_SITE_ENABLED}" ]]; then
    ln -sf "${NGINX_CONF}" "${NGINX_SITE_ENABLED}"
    ok "Nginx site symlink created."
fi

nginx -t || fail "nginx config test failed before certbot run"
systemctl reload nginx

# -------------------------------------------------------
# 6. Obtain Let's Encrypt certificate
# -------------------------------------------------------
LETSENCRYPT_CERT="/etc/letsencrypt/live/${DOMAIN}/fullchain.pem"
LETSENCRYPT_KEY="/etc/letsencrypt/live/${DOMAIN}/privkey.pem"

step "Requesting Let's Encrypt certificate for ${DOMAIN}..."
certbot --nginx -d "${DOMAIN}" --non-interactive --agree-tos \
    --email "admin@${DOMAIN}" --redirect \
    || fail "certbot failed — check DNS and port 80 accessibility"
ok "Certificate issued."

# -------------------------------------------------------
# 7. Patch nginx config to point at Let's Encrypt cert paths
# -------------------------------------------------------
step "Patching ssl_certificate paths in ${NGINX_CONF}..."
sed -i "s|ssl_certificate     /etc/jarvis/ssl/cert.pem;|ssl_certificate     ${LETSENCRYPT_CERT};|g" "${NGINX_CONF}"
sed -i "s|ssl_certificate_key /etc/jarvis/ssl/key.pem;|ssl_certificate_key ${LETSENCRYPT_KEY};|g" "${NGINX_CONF}"
ok "Cert paths updated."

# -------------------------------------------------------
# 8. Final nginx reload
# -------------------------------------------------------
step "Testing and reloading nginx..."
nginx -t || fail "nginx config test failed after cert path patch"
systemctl reload nginx
ok "nginx reloaded."

# -------------------------------------------------------
# 9. Verify certbot renewal timer
# -------------------------------------------------------
step "Checking certbot auto-renewal..."
if systemctl is-active --quiet certbot.timer 2>/dev/null; then
    ok "certbot.timer is active — auto-renewal is handled by systemd."
elif crontab -l 2>/dev/null | grep -q certbot; then
    ok "certbot renewal cron job already present."
else
    step "Adding certbot renewal cron job (runs twice daily)..."
    (crontab -l 2>/dev/null; echo "0 */12 * * * certbot renew --quiet --nginx && systemctl reload nginx") | crontab -
    ok "Renewal cron job added."
fi

# -------------------------------------------------------
# 10. Success
# -------------------------------------------------------
echo
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${GREEN}  Let's Encrypt HTTPS setup complete${RESET}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo
echo -e "  ${CYAN}https://${DOMAIN}${RESET}"
echo
echo -e "  Certificate will auto-renew — no manual action needed."
echo -e "  To test renewal: certbot renew --dry-run"
echo
