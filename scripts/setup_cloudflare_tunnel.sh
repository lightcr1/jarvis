#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Cloudflare Tunnel setup
#
# Installs cloudflared, creates a named tunnel "jarvis", writes config,
# creates the DNS CNAME, and installs the systemd service.
#
# Prerequisites:
#   - Domain already added to Cloudflare
#   - Run as root on the JARVIS VM
#   - JARVIS already deployed via scripts/install.sh
#   - nginx using deploy/nginx/jarvis-cloudflare.conf
#
# Usage:
#   sudo bash scripts/setup_cloudflare_tunnel.sh
# =============================================================================

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()     { echo -e "${GREEN}[✓]${RESET} $*"; }
info()    { echo -e "${CYAN}[→]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
fail()    { echo -e "${RED}[✗] ERROR: $*${RESET}" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${RESET}"; }
ask()     { local var="$1" prompt="$2" default="${3:-}"; local d=""; [[ -n "$default" ]] && d=" [$default]"; echo -en "${CYAN}?${RESET} ${prompt}${d}: "; read -r input; printf -v "${var}" '%s' "${input:-${default}}"; }

[[ $EUID -ne 0 ]] && fail "Run as root: sudo bash scripts/setup_cloudflare_tunnel.sh"

# ── 1. Install cloudflared ───────────────────────────────────────────────────
section "Install cloudflared"

if command -v cloudflared &>/dev/null; then
    log "cloudflared already installed: $(cloudflared --version 2>&1 | head -1)"
else
    info "Downloading cloudflared..."
    ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")
    curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${ARCH}.deb" \
        -o /tmp/cloudflared.deb
    dpkg -i /tmp/cloudflared.deb
    rm /tmp/cloudflared.deb
    log "cloudflared installed"
fi

# ── 2. Authenticate with Cloudflare ─────────────────────────────────────────
section "Cloudflare Authentication"

if [[ ! -f ~/.cloudflared/cert.pem ]]; then
    info "Opening browser to authenticate with Cloudflare..."
    info "If this is a headless server, copy the URL and open it on your local machine."
    cloudflared tunnel login
    log "Authenticated"
else
    log "Already authenticated (cert.pem found)"
fi

# ── 3. Create tunnel ─────────────────────────────────────────────────────────
section "Create Tunnel"

TUNNEL_NAME="jarvis"
if cloudflared tunnel list 2>/dev/null | grep -q "^${TUNNEL_NAME}"; then
    log "Tunnel '${TUNNEL_NAME}' already exists"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "^${TUNNEL_NAME}" | awk '{print $2}')
else
    info "Creating tunnel '${TUNNEL_NAME}'..."
    TUNNEL_ID=$(cloudflared tunnel create "${TUNNEL_NAME}" 2>/dev/null | grep -oP '[0-9a-f-]{36}' | head -1)
    log "Tunnel created: ${TUNNEL_ID}"
fi

# Copy credentials to /etc/cloudflared
mkdir -p /etc/cloudflared
CF_CRED_SRC=~/.cloudflared/${TUNNEL_ID}.json
CF_CRED_DST=/etc/cloudflared/${TUNNEL_ID}.json
if [[ -f "${CF_CRED_SRC}" ]]; then
    cp "${CF_CRED_SRC}" "${CF_CRED_DST}"
    chmod 600 "${CF_CRED_DST}"
    log "Credentials installed to ${CF_CRED_DST}"
fi

# ── 4. DNS record ────────────────────────────────────────────────────────────
section "DNS Configuration"

ask SUBDOMAIN "Subdomain for JARVIS (e.g. jarvis)" "jarvis"
ask DOMAIN    "Your root domain (e.g. example.com)"

HOSTNAME="${SUBDOMAIN}.${DOMAIN}"

info "Creating DNS CNAME for ${HOSTNAME}..."
cloudflared tunnel route dns "${TUNNEL_NAME}" "${HOSTNAME}" && log "DNS record created: ${HOSTNAME}" || warn "DNS record may already exist — continuing"

# ── 5. Write config ──────────────────────────────────────────────────────────
section "Write /etc/cloudflared/config.yml"

cat > /etc/cloudflared/config.yml <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: /etc/cloudflared/${TUNNEL_ID}.json

loglevel: info

ingress:
  - hostname: ${HOSTNAME}
    service: http://127.0.0.1:80
    originRequest:
      connectTimeout: 30s
      tcpKeepAlive: 30s
      httpHostHeader: ${HOSTNAME}
  - service: http_status:404
EOF

log "Config written to /etc/cloudflared/config.yml"

# ── 6. Install nginx Cloudflare config ───────────────────────────────────────
section "Configure nginx"

JARVIS_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NGINX_CF_CONF="${JARVIS_SOURCE}/deploy/nginx/jarvis-cloudflare.conf"

if [[ -f "${NGINX_CF_CONF}" ]]; then
    cp "${NGINX_CF_CONF}" /etc/nginx/sites-available/jarvis-cloudflare
    ln -sf /etc/nginx/sites-available/jarvis-cloudflare /etc/nginx/sites-enabled/jarvis-cloudflare
    # Disable the old HTTPS config if present
    rm -f /etc/nginx/sites-enabled/jarvis
    nginx -t && log "nginx config valid" || fail "nginx config test failed"
    systemctl reload nginx && log "nginx reloaded"
else
    warn "Cloudflare nginx config not found at ${NGINX_CF_CONF} — skipping"
fi

# ── 7. Create cloudflared system user ───────────────────────────────────────
section "cloudflared system user"

if ! id cloudflared &>/dev/null; then
    useradd --system --no-create-home --shell /usr/sbin/nologin cloudflared
    log "User 'cloudflared' created"
fi
chown -R cloudflared:cloudflared /etc/cloudflared
mkdir -p /var/log/cloudflared
chown cloudflared:cloudflared /var/log/cloudflared

# ── 8. Install systemd service ───────────────────────────────────────────────
section "systemd service"

JARVIS_SOURCE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp "${JARVIS_SOURCE}/deploy/cloudflared.service" /etc/systemd/system/cloudflared.service
systemctl daemon-reload
systemctl enable cloudflared
systemctl restart cloudflared

sleep 2
if systemctl is-active --quiet cloudflared; then
    log "cloudflared is running"
else
    fail "cloudflared failed to start — check: journalctl -u cloudflared -n 50"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━  Cloudflare Tunnel active  ━━━${RESET}"
echo ""
echo -e "  JARVIS URL  :  ${BOLD}https://${HOSTNAME}${RESET}"
echo -e "  Tunnel ID   :  ${TUNNEL_ID}"
echo -e "  Tunnel name :  ${TUNNEL_NAME}"
echo ""
echo -e "  ${CYAN}Next steps in Cloudflare dashboard:${RESET}"
echo -e "  1. SSL/TLS → mode: Full (strict)"
echo -e "  2. Security → WAF: Managed rules ON"
echo -e "  3. (Optional) Zero Trust → Access: restrict to your email"
echo ""
echo -e "  Check status:  ${CYAN}systemctl status cloudflared${RESET}"
echo -e "  View logs:     ${CYAN}journalctl -u cloudflared -f${RESET}"
