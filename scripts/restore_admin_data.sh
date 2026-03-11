#!/usr/bin/env bash
set -euo pipefail

ARCHIVE_PATH="${1:-}"
if [ -z "$ARCHIVE_PATH" ] || [ ! -f "$ARCHIVE_PATH" ]; then
  echo "Usage: $0 <backup_archive.tar.gz>"
  exit 2
fi

AUDIT_PATH="${JARVIS_AUDIT_LOG_PATH:-/var/lib/jarvis/audit.log}"
USERS_PATH="${JARVIS_USER_STORE_PATH:-/var/lib/jarvis/users.json}"
GROUPS_PATH="${JARVIS_GROUP_STORE_PATH:-/var/lib/jarvis/groups.json}"
MEMBERSHIPS_PATH="${JARVIS_MEMBERSHIP_STORE_PATH:-/var/lib/jarvis/memberships.json}"
PERMS_PATH="${JARVIS_PERMISSION_STORE_PATH:-/var/lib/jarvis/permissions.json}"

mkdir -p "$(dirname "$AUDIT_PATH")" "$(dirname "$USERS_PATH")" "$(dirname "$GROUPS_PATH")" "$(dirname "$MEMBERSHIPS_PATH")" "$(dirname "$PERMS_PATH")"

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

ALLOWED_FILES_REGEX='^(\./)?(audit\.log|users\.json|groups\.json|memberships\.json|permissions\.json)$'

while IFS= read -r entry; do
  if [ "$entry" = "./" ] || [ "$entry" = "." ]; then
    continue
  fi
  if [[ ! "$entry" =~ $ALLOWED_FILES_REGEX ]]; then
    echo "Refusing to restore unexpected archive entry: $entry"
    exit 3
  fi
done < <(tar -tzf "$ARCHIVE_PATH")

tar -xzf "$ARCHIVE_PATH" -C "$TMPDIR"

restore_if_exists() {
  local src="$1"
  local dst="$2"
  if [ -f "$src" ]; then
    cp "$src" "$dst"
  fi
}

restore_if_exists "$TMPDIR/audit.log" "$AUDIT_PATH"
restore_if_exists "$TMPDIR/users.json" "$USERS_PATH"
restore_if_exists "$TMPDIR/groups.json" "$GROUPS_PATH"
restore_if_exists "$TMPDIR/memberships.json" "$MEMBERSHIPS_PATH"
restore_if_exists "$TMPDIR/permissions.json" "$PERMS_PATH"

echo "Restore completed from: $ARCHIVE_PATH"
