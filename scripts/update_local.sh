#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR="${INSTALL_DIR:-/opt/jarvis}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/jarvis/releases}"
TS="$(date +%Y%m%d_%H%M%S)"
SNAPSHOT_DIR="${BACKUP_DIR}/${TS}"
REPO_SNAPSHOT="${SNAPSHOT_DIR}/repo"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

if [[ "${EUID}" -ne 0 ]]; then
  fail "Run as root (use sudo)."
fi

command -v rsync >/dev/null 2>&1 || fail "rsync is required. Install it and retry."
command -v systemctl >/dev/null 2>&1 || fail "systemctl is required on this host."

mkdir -p "${BACKUP_DIR}" "${SNAPSHOT_DIR}"

if [[ -d "${INSTALL_DIR}" ]]; then
  rsync -a --delete "${INSTALL_DIR}/" "${REPO_SNAPSHOT}/" || fail "Failed to snapshot existing install dir."
fi

if [[ -x "${INSTALL_DIR}/scripts/backup_admin_data.sh" ]]; then
  "${INSTALL_DIR}/scripts/backup_admin_data.sh" "${SNAPSHOT_DIR}" || fail "Failed to snapshot admin data."
fi

LATEST_LINK="${BACKUP_DIR}/latest"
rm -rf "${LATEST_LINK}"
ln -s "${SNAPSHOT_DIR}" "${LATEST_LINK}"

"${ROOT_DIR}/scripts/deploy_local.sh"

echo "Update completed. Snapshot stored at: ${SNAPSHOT_DIR}"
