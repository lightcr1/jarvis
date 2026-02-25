#!/usr/bin/env bash
set -euo pipefail

KIOSK_USER="jarvis"
KIOSK_HOME="/home/${KIOSK_USER}"
KIOSK_URL="${KIOSK_URL:-http://localhost:8000/}"
MODEL_DIR="${LOCAL_LLM_MODEL_DIR:-/var/lib/jarvis/local-ai/models}"

if ! id -u "${KIOSK_USER}" >/dev/null 2>&1; then
  useradd -m -s /bin/bash "${KIOSK_USER}"
fi

usermod -aG audio,video,input,plugdev "${KIOSK_USER}" || true

mkdir -p "${KIOSK_HOME}"/.config/openbox
cat > "${KIOSK_HOME}/.xinitrc" <<EOT
#!/usr/bin/env bash
xset -dpms
xset s off
xset s noblank
openbox-session &
exec chromium-browser \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --incognito \
  "${KIOSK_URL}"
EOT
chmod +x "${KIOSK_HOME}/.xinitrc"

cat > "${KIOSK_HOME}/.bash_profile" <<'EOT'
if [[ -z "${DISPLAY:-}" ]] && [[ "$(tty)" == "/dev/tty1" ]]; then
  exec startx
fi
EOT

mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf <<'EOT'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin jarvis --noclear %I $TERM
EOT

mkdir -p /var/lib/jarvis/local-ai
mkdir -p "${MODEL_DIR}"
chown -R "${KIOSK_USER}:${KIOSK_USER}" "${KIOSK_HOME}"
chmod 755 /var/lib/jarvis/local-ai "${MODEL_DIR}"

systemctl daemon-reload
systemctl enable getty@tty1.service

echo "Kiosk setup done. URL=${KIOSK_URL}"
