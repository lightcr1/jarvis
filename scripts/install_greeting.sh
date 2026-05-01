#!/usr/bin/env bash
# Install the J.A.R.V.I.S. startup greeting for the current user.
# Run as the user who should receive the greeting (NOT as root).
#
# What this does:
#   1. Installs the systemd user service (fires at graphical login)
#   2. Installs the XDG desktop autostart entry (fallback for non-systemd desktops)
#   3. Optionally configures auto-login via lightdm/gdm3
#
# Usage:
#   bash /opt/jarvis/scripts/install_greeting.sh [--autologin]

set -euo pipefail

INSTALL_DIR="/opt/jarvis"
AUTOLOGIN=0

for arg in "$@"; do
  [[ "${arg}" == "--autologin" ]] && AUTOLOGIN=1
done

fail() { echo "ERROR: $*" >&2; exit 1; }
log()  { echo "[install-greeting] $*"; }

[[ "${EUID}" -ne 0 ]] || fail "Run this script as the login user, not root."
[[ -f "${INSTALL_DIR}/scripts/startup_greeting.sh" ]] || fail "JARVIS not found at ${INSTALL_DIR}. Run deploy_local.sh first."

CURRENT_USER="${USER}"
XDG_AUTOSTART="${HOME}/.config/autostart"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

# --- systemd user service -----------------------------------------------------
mkdir -p "${SYSTEMD_USER_DIR}"
cp "${INSTALL_DIR}/systemd/jarvis-greeting.service" "${SYSTEMD_USER_DIR}/jarvis-greeting.service"
systemctl --user daemon-reload
systemctl --user enable --now jarvis-greeting.service
log "Systemd user service enabled: jarvis-greeting.service"

# --- XDG desktop autostart (GNOME/KDE/XFCE fallback) -------------------------
mkdir -p "${XDG_AUTOSTART}"
cp "${INSTALL_DIR}/config/autostart/jarvis-greeting.desktop" "${XDG_AUTOSTART}/jarvis-greeting.desktop"
log "Desktop autostart entry installed: ${XDG_AUTOSTART}/jarvis-greeting.desktop"

# --- Optional: auto-login via display manager ---------------------------------
if [[ "${AUTOLOGIN}" -eq 1 ]]; then
  if [[ "${EUID}" -eq 0 ]]; then
    fail "--autologin must be configured as root. Re-run: sudo bash ${0} --autologin-system ${CURRENT_USER}"
  fi
  log "For auto-login, run the following as root:"
  log "  sudo bash ${INSTALL_DIR}/scripts/setup_autologin.sh ${CURRENT_USER}"
fi

log ""
log "Done. J.A.R.V.I.S. will greet you at every login."
log "To test immediately: bash ${INSTALL_DIR}/scripts/startup_greeting.sh"
log ""
log "To disable:  systemctl --user disable jarvis-greeting.service"
log "To uninstall: rm ${XDG_AUTOSTART}/jarvis-greeting.desktop"
