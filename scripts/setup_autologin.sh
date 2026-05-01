#!/usr/bin/env bash
# Configure automatic login for a user via lightdm or gdm3.
# Run as root: sudo bash scripts/setup_autologin.sh <username>
#
# This means the computer boots straight to the desktop —
# J.A.R.V.I.S. then greets you automatically via jarvis-greeting.service.

set -euo pipefail

fail() { echo "ERROR: $*" >&2; exit 1; }
log()  { echo "[setup-autologin] $*"; }

[[ "${EUID}" -eq 0 ]] || fail "Run as root: sudo bash $0 <username>"
[[ -n "${1:-}" ]] || fail "Usage: sudo bash $0 <username>"

TARGET_USER="$1"
id -u "${TARGET_USER}" >/dev/null 2>&1 || fail "User '${TARGET_USER}' does not exist."

# --- lightdm (Ubuntu, Mint, Raspberry Pi OS, most Debian desktops) -----------
if command -v lightdm >/dev/null 2>&1 || [[ -f /etc/lightdm/lightdm.conf ]]; then
  LIGHTDM_CONF="/etc/lightdm/lightdm.conf"
  mkdir -p /etc/lightdm
  if [[ ! -f "${LIGHTDM_CONF}" ]]; then
    cat > "${LIGHTDM_CONF}" <<EOF
[Seat:*]
autologin-user=${TARGET_USER}
autologin-user-timeout=0
EOF
  else
    # Update or add autologin lines in [Seat:*] section
    if grep -q "^\[Seat:\*\]" "${LIGHTDM_CONF}"; then
      sed -i "/^\[Seat:\*\]/,/^\[/ s/^autologin-user=.*/autologin-user=${TARGET_USER}/" "${LIGHTDM_CONF}"
      if ! grep -q "^autologin-user=" "${LIGHTDM_CONF}"; then
        sed -i "/^\[Seat:\*\]/a autologin-user=${TARGET_USER}\nautologin-user-timeout=0" "${LIGHTDM_CONF}"
      fi
    else
      printf '\n[Seat:*]\nautologin-user=%s\nautologin-user-timeout=0\n' "${TARGET_USER}" >> "${LIGHTDM_CONF}"
    fi
  fi
  log "lightdm auto-login configured for ${TARGET_USER}"
  log "Config: ${LIGHTDM_CONF}"

# --- gdm3 (Ubuntu with GNOME, Fedora, Arch GNOME) ----------------------------
elif command -v gdm3 >/dev/null 2>&1 || [[ -f /etc/gdm3/custom.conf ]]; then
  GDM_CONF="/etc/gdm3/custom.conf"
  if [[ ! -f "${GDM_CONF}" ]]; then
    mkdir -p /etc/gdm3
    cat > "${GDM_CONF}" <<EOF
[daemon]
AutomaticLoginEnable=true
AutomaticLogin=${TARGET_USER}
EOF
  else
    if grep -q "^\[daemon\]" "${GDM_CONF}"; then
      sed -i "/^\[daemon\]/,/^\[/ s/^AutomaticLogin=.*/AutomaticLogin=${TARGET_USER}/" "${GDM_CONF}"
      sed -i "/^\[daemon\]/,/^\[/ s/^AutomaticLoginEnable=.*/AutomaticLoginEnable=true/" "${GDM_CONF}"
      if ! grep -q "^AutomaticLogin=" "${GDM_CONF}"; then
        sed -i "/^\[daemon\]/a AutomaticLoginEnable=true\nAutomaticLogin=${TARGET_USER}" "${GDM_CONF}"
      fi
    else
      printf '\n[daemon]\nAutomaticLoginEnable=true\nAutomaticLogin=%s\n' "${TARGET_USER}" >> "${GDM_CONF}"
    fi
  fi
  log "gdm3 auto-login configured for ${TARGET_USER}"
  log "Config: ${GDM_CONF}"

else
  log "WARNING: Could not detect lightdm or gdm3."
  log "Configure auto-login manually in your display manager."
  log "For lightdm: add 'autologin-user=${TARGET_USER}' under [Seat:*] in /etc/lightdm/lightdm.conf"
  log "For gdm3:    add 'AutomaticLogin=${TARGET_USER}' under [daemon] in /etc/gdm3/custom.conf"
  exit 1
fi

log ""
log "Auto-login enabled for '${TARGET_USER}'."
log "On next boot, the desktop will start automatically and J.A.R.V.I.S. will greet you."
log "To disable auto-login, remove the autologin lines from the config above."
