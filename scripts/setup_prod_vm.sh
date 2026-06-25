#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# JARVIS — Proxmox VM Production Setup
#
# Prepares a fresh Debian 12 / Ubuntu 24.04 VM for JARVIS.
# Run this ONCE on a new VM before running scripts/install.sh.
#
# What it does:
#   - System updates + required packages (Python 3.12, Node 20, nginx, git, curl)
#   - Sets timezone to Europe/Berlin (change below if needed)
#   - Configures UFW firewall (only SSH inbound — everything else via Cloudflare tunnel)
#   - Prints next steps
#
# Usage (as root on the VM):
#   bash <(curl -fsSL https://raw.githubusercontent.com/<you>/jarvis/main/scripts/setup_prod_vm.sh)
# OR copy the repo first and run locally:
#   sudo bash scripts/setup_prod_vm.sh
# =============================================================================

TIMEZONE="Europe/Berlin"

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

log()     { echo -e "${GREEN}[✓]${RESET} $*"; }
info()    { echo -e "${CYAN}[→]${RESET} $*"; }
warn()    { echo -e "${YELLOW}[!]${RESET} $*"; }
fail()    { echo -e "${RED}[✗] ERROR: $*${RESET}" >&2; exit 1; }
section() { echo -e "\n${BOLD}${CYAN}━━━  $*  ━━━${RESET}"; }

[[ $EUID -ne 0 ]] && fail "Run as root: sudo bash scripts/setup_prod_vm.sh"

# Detect distro
if [[ -f /etc/debian_version ]]; then
    DISTRO="debian"
elif [[ -f /etc/lsb-release ]] && grep -q "Ubuntu" /etc/lsb-release; then
    DISTRO="ubuntu"
else
    warn "Unknown distro — proceeding as Debian-compatible"
    DISTRO="debian"
fi

# ── 1. System update ─────────────────────────────────────────────────────────
section "System update"
apt-get update -qq
apt-get upgrade -y -qq
log "System updated"

# ── 2. Core packages ─────────────────────────────────────────────────────────
section "Core packages"

apt-get install -y -qq \
    curl wget git unzip \
    build-essential pkg-config \
    nginx \
    ufw \
    ffmpeg \
    ca-certificates gnupg lsb-release \
    htop jq

log "Core packages installed"

# ── 3. Python 3.12 ───────────────────────────────────────────────────────────
section "Python 3.12"

if python3.12 --version &>/dev/null 2>&1; then
    log "Python 3.12 already installed: $(python3.12 --version)"
else
    info "Adding deadsnakes PPA / backport..."
    if [[ "$DISTRO" == "ubuntu" ]]; then
        add-apt-repository -y ppa:deadsnakes/ppa
    else
        apt-get install -y -qq software-properties-common
        echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list.d/bookworm.list || true
    fi
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev python3-pip
    log "Python 3.12 installed"
fi

# Always ensure venv + pip (Ubuntu 24.04 ships Python 3.12 without them)
apt-get install -y -qq python3.12-venv python3.12-dev python3-pip
log "python3.12-venv + pip ensured"

# ── 4. Node.js 20 ────────────────────────────────────────────────────────────
section "Node.js 20 (for frontend build)"

if node --version 2>/dev/null | grep -q "^v20"; then
    log "Node.js 20 already installed: $(node --version)"
else
    info "Installing Node.js 20 via NodeSource..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y -qq nodejs
    log "Node.js installed: $(node --version)"
fi

# ── 5. Timezone ──────────────────────────────────────────────────────────────
section "Timezone"
timedatectl set-timezone "${TIMEZONE}"
log "Timezone set to ${TIMEZONE}"

# ── 6. Firewall (UFW) ────────────────────────────────────────────────────────
section "Firewall — UFW"
# With Cloudflare Tunnel, we only need SSH open inbound.
# HTTP/HTTPS are NOT opened — traffic comes in via cloudflared tunnel.

ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw --force enable
log "UFW enabled: SSH only inbound (Cloudflare Tunnel handles HTTP/HTTPS)"
ufw status numbered

# ── 7. nginx base config ─────────────────────────────────────────────────────
section "nginx base config"

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Disable access log for /health checks (reduce noise)
cat > /etc/nginx/conf.d/logging.conf <<'EOF'
map $request_uri $loggable {
    ~^/health  0;
    default    1;
}
access_log /var/log/nginx/access.log combined if=$loggable;
EOF

systemctl enable nginx
systemctl start nginx
log "nginx configured and running"

# ── 8. Prepare directory for JARVIS source ───────────────────────────────────
section "JARVIS source directory"

JARVIS_OPT="/opt/jarvis"
if [[ -d "${JARVIS_OPT}" ]]; then
    warn "${JARVIS_OPT} already exists — skipping mkdir"
else
    mkdir -p "${JARVIS_OPT}"
    log "Created ${JARVIS_OPT}"
fi

# ── Done ─────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━  VM is ready  ━━━${RESET}"
echo ""
echo -e "  ${CYAN}Next: deploy JARVIS${RESET}"
echo ""
echo -e "  Option A — Clone repo and run install:"
echo -e "    ${BOLD}git clone https://github.com/<you>/jarvis /opt/jarvis${RESET}"
echo -e "    ${BOLD}sudo bash /opt/jarvis/scripts/install.sh${RESET}"
echo ""
echo -e "  Option B — If repo is already on this machine:"
echo -e "    ${BOLD}sudo bash scripts/install.sh${RESET}"
echo ""
echo -e "  After JARVIS is running:"
echo -e "    ${BOLD}sudo bash scripts/setup_cloudflare_tunnel.sh${RESET}"
