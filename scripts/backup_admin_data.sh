#!/usr/bin/env bash
set -euo pipefail

DEST_DIR="${1:-./backups}"
TS="$(date +%Y%m%d_%H%M%S)"
OUT_FILE="${DEST_DIR}/jarvis_admin_data_${TS}.tar.gz"

mkdir -p "$DEST_DIR"

# Resolve data files from env defaults used by stores
AUDIT_PATH="${JARVIS_AUDIT_LOG_PATH:-/var/lib/jarvis/audit.log}"
USERS_PATH="${JARVIS_USER_STORE_PATH:-/var/lib/jarvis/users.json}"
GROUPS_PATH="${JARVIS_GROUP_STORE_PATH:-/var/lib/jarvis/groups.json}"
MEMBERSHIPS_PATH="${JARVIS_MEMBERSHIP_STORE_PATH:-/var/lib/jarvis/memberships.json}"
PERMS_PATH="${JARVIS_PERMISSION_STORE_PATH:-/var/lib/jarvis/permissions.json}"
SETTINGS_PATH="${JARVIS_ADMIN_SETTINGS_PATH:-/var/lib/jarvis/admin_settings.json}"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

COPIED=0

copy_if_exists() {
  local src="$1"
  local name="$2"
  if [ -f "$src" ]; then
    cp "$src" "$TMPDIR/$name"
    COPIED=1
  fi
}

copy_if_exists "$AUDIT_PATH" "audit.log"
copy_if_exists "$USERS_PATH" "users.json"
copy_if_exists "$GROUPS_PATH" "groups.json"
copy_if_exists "$MEMBERSHIPS_PATH" "memberships.json"
copy_if_exists "$PERMS_PATH" "permissions.json"
copy_if_exists "$SETTINGS_PATH" "admin_settings.json"

if [ "$COPIED" -eq 0 ]; then
  echo "No admin data files found to back up."
  exit 1
fi

tar -czf "$OUT_FILE" -C "$TMPDIR" .

echo "Backup created: $OUT_FILE"
