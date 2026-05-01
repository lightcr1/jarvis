#!/usr/bin/env bash
# Set up Tailscale for remote JARVIS access from any device.
# Run as root: sudo bash scripts/setup_tailscale.sh
#
# After this you can reach JARVIS from your phone, tablet, or any laptop
# via https://<tailscale-ip>/ — no port forwarding, no public IP needed.
#
# On each other device: install Tailscale (https://tailscale.com/download),
# sign in with the same account, and JARVIS is reachable immediately.

set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
log()  { echo "[setup-tailscale] $*"; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash $0"

# --- Install Tailscale --------------------------------------------------------
if ! command -v tailscale >/dev/null 2>&1; then
  log "Installing Tailscale..."
  if command -v apt-get >/dev/null 2>&1; then
    curl -fsSL https://pkgs.tailscale.com/stable/debian/bullseye.noarmor.gpg \
      | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
    curl -fsSL https://pkgs.tailscale.com/stable/debian/bullseye.tailscale-keyring.list \
      | tee /etc/apt/sources.list.d/tailscale.list
    apt-get update -qq
    apt-get install -y tailscale
  else
    fail "Auto-install only supports apt (Debian/Ubuntu). See https://tailscale.com/download for other distros."
  fi
else
  log "Tailscale already installed: $(tailscale version 2>/dev/null | head -1)"
fi

# --- Enable & start -----------------------------------------------------------
systemctl enable --now tailscaled || fail "Failed to start tailscaled"

# --- Authenticate -------------------------------------------------------------
log ""
log "Starting Tailscale authentication..."
log "A URL will appear below — open it on any device to sign in."
log ""
tailscale up --accept-routes || true

# --- Show Tailscale IP --------------------------------------------------------
TAILSCALE_IP=$(tailscale ip -4 2>/dev/null || echo "")
log ""
if [[ -n "${TAILSCALE_IP}" ]]; then
  log "======================================================"
  log "Tailscale IP: ${TAILSCALE_IP}"
  log ""
  log "Access JARVIS from any device at:"
  log "  https://${TAILSCALE_IP}/"
  log ""
  log "Add this to your config (/etc/jarvis/config.env):"
  log "  JARVIS_HOST=0.0.0.0"
  log "  JARVIS_PORT=443"
  log ""
  log "On your phone/tablet/laptop:"
  log "  1. Install Tailscale: https://tailscale.com/download"
  log "  2. Sign in with the same account"
  log "  3. Open https://${TAILSCALE_IP}/ in your browser"
  log "  4. On iPhone/Android: tap Share → Add to Home Screen"
  log "     for a native-app-like icon"
  log "======================================================"
else
  log "Tailscale IP not yet assigned. Run 'tailscale ip -4' after authentication."
fi
