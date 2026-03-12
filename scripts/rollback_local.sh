#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/jarvis}"
BACKUP_ROOT="${BACKUP_ROOT:-/var/backups/jarvis/releases}"
TARGET="${1:-${BACKUP_ROOT}/latest}"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run as root (use sudo)."
fi

command -v rsync >/dev/null 2>&1 || fail "rsync is required. Install it and retry."
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required on this host."

if [[ ! -d "${TARGET}" ]]; then
  fail "Rollback snapshot not found: ${TARGET}"
fi
if [[ ! -d "${TARGET}/repo" ]]; then
  fail "Rollback snapshot missing repo payload: ${TARGET}/repo"
fi

mkdir -p "${INSTALL_DIR}"
rsync -a --delete "${TARGET}/repo/" "${INSTALL_DIR}/" || fail "Failed to restore repo snapshot."

LATEST_ARCHIVE="$(find "${TARGET}" -maxdepth 1 -type f -name 'jarvis_admin_data_*.tar.gz' | sort | tail -n 1)"
if [[ -n "${LATEST_ARCHIVE}" && -x "${INSTALL_DIR}/scripts/restore_admin_data.sh" ]]; then
  "${INSTALL_DIR}/scripts/restore_admin_data.sh" "${LATEST_ARCHIVE}" || fail "Failed to restore admin data snapshot."
fi

if [[ -f /etc/systemd/system/jarvis.service ]]; then
  systemctl daemon-reload || fail "systemctl daemon-reload failed"
  systemctl restart jarvis.service || fail "Failed to restart jarvis.service"
  systemctl --no-pager --full status jarvis.service || true
fi

if [[ -x "${INSTALL_DIR}/scripts/check_admin_data_integrity.sh" ]]; then
  "${INSTALL_DIR}/scripts/check_admin_data_integrity.sh" || fail "Admin data integrity check failed after rollback"
fi

echo "Rollback completed from: ${TARGET}"
