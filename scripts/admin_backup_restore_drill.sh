#!/usr/bin/env bash
set -euo pipefail

REPORT_PATH="${1:-./admin_backup_restore_drill_report.md}"

LIVE_AUDIT_PATH="${JARVIS_AUDIT_LOG_PATH:-/var/lib/jarvis/audit.log}"
LIVE_USERS_PATH="${JARVIS_USER_STORE_PATH:-/var/lib/jarvis/users.json}"
LIVE_GROUPS_PATH="${JARVIS_GROUP_STORE_PATH:-/var/lib/jarvis/groups.json}"
LIVE_MEMBERSHIPS_PATH="${JARVIS_MEMBERSHIP_STORE_PATH:-/var/lib/jarvis/memberships.json}"
LIVE_PERMS_PATH="${JARVIS_PERMISSION_STORE_PATH:-/var/lib/jarvis/permissions.json}"
LIVE_SETTINGS_PATH="${JARVIS_ADMIN_SETTINGS_PATH:-/var/lib/jarvis/admin_settings.json}"

for p in "$LIVE_AUDIT_PATH" "$LIVE_USERS_PATH" "$LIVE_GROUPS_PATH" "$LIVE_MEMBERSHIPS_PATH" "$LIVE_PERMS_PATH" "$LIVE_SETTINGS_PATH"; do
  if [[ ! -f "$p" ]]; then
    echo "Missing admin data file for drill: $p" >&2
    exit 2
  fi
done

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

PROBE_DIR="$WORKDIR/probe"
SNAPSHOT_DIR="$WORKDIR/snapshot"
BACKUP_DIR="$WORKDIR/backups"
mkdir -p "$PROBE_DIR" "$SNAPSHOT_DIR" "$BACKUP_DIR"

cp "$LIVE_AUDIT_PATH" "$PROBE_DIR/audit.log"
cp "$LIVE_USERS_PATH" "$PROBE_DIR/users.json"
cp "$LIVE_GROUPS_PATH" "$PROBE_DIR/groups.json"
cp "$LIVE_MEMBERSHIPS_PATH" "$PROBE_DIR/memberships.json"
cp "$LIVE_PERMS_PATH" "$PROBE_DIR/permissions.json"
cp "$LIVE_SETTINGS_PATH" "$PROBE_DIR/admin_settings.json"

cp "$PROBE_DIR/audit.log" "$SNAPSHOT_DIR/audit.log"
cp "$PROBE_DIR/users.json" "$SNAPSHOT_DIR/users.json"
cp "$PROBE_DIR/groups.json" "$SNAPSHOT_DIR/groups.json"
cp "$PROBE_DIR/memberships.json" "$SNAPSHOT_DIR/memberships.json"
cp "$PROBE_DIR/permissions.json" "$SNAPSHOT_DIR/permissions.json"
cp "$PROBE_DIR/admin_settings.json" "$SNAPSHOT_DIR/admin_settings.json"

export JARVIS_AUDIT_LOG_PATH="$PROBE_DIR/audit.log"
export JARVIS_USER_STORE_PATH="$PROBE_DIR/users.json"
export JARVIS_GROUP_STORE_PATH="$PROBE_DIR/groups.json"
export JARVIS_MEMBERSHIP_STORE_PATH="$PROBE_DIR/memberships.json"
export JARVIS_PERMISSION_STORE_PATH="$PROBE_DIR/permissions.json"
export JARVIS_ADMIN_SETTINGS_PATH="$PROBE_DIR/admin_settings.json"

BACKUP_OUTPUT="$(bash scripts/backup_admin_data.sh "$BACKUP_DIR")"
ARCHIVE_PATH="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'jarvis_admin_data_*.tar.gz' | sort | tail -n 1)"
if [[ -z "$ARCHIVE_PATH" ]]; then
  echo "Backup drill failed: archive not created" >&2
  exit 3
fi

printf 'mutated-audit\n' > "$PROBE_DIR/audit.log"
printf '{"users":{"usr-mutated":{"id":"usr-mutated","role":"guest_restricted","enabled":false}}}\n' > "$PROBE_DIR/users.json"
printf '{"groups":{"grp-mutated":{"id":"grp-mutated","name":"mutated"}}}\n' > "$PROBE_DIR/groups.json"
printf '{"memberships":[{"user_id":"usr-mutated","group_id":"grp-mutated"}]}\n' > "$PROBE_DIR/memberships.json"
printf '{"group_permissions":{"grp-mutated":["assistant.chat"]},"user_permissions":{"usr-mutated":["assistant.chat"]}}\n' > "$PROBE_DIR/permissions.json"
printf '{"usage_limits":{"token_ttl_min":1,"max_active_tokens":1},"voice":{"wakeword_enabled":true,"wakeword_phrase":"mutated","stt_provider":"gemini"}}\n' > "$PROBE_DIR/admin_settings.json"

RESTORE_OUTPUT="$(bash scripts/restore_admin_data.sh "$ARCHIVE_PATH")"
INTEGRITY_OUTPUT="$(bash scripts/check_admin_data_integrity.sh)"

cmp -s "$SNAPSHOT_DIR/audit.log" "$PROBE_DIR/audit.log"
cmp -s "$SNAPSHOT_DIR/users.json" "$PROBE_DIR/users.json"
cmp -s "$SNAPSHOT_DIR/groups.json" "$PROBE_DIR/groups.json"
cmp -s "$SNAPSHOT_DIR/memberships.json" "$PROBE_DIR/memberships.json"
cmp -s "$SNAPSHOT_DIR/permissions.json" "$PROBE_DIR/permissions.json"
cmp -s "$SNAPSHOT_DIR/admin_settings.json" "$PROBE_DIR/admin_settings.json"

mkdir -p "$(dirname "$REPORT_PATH")"
cat > "$REPORT_PATH" <<EOF
# Admin Backup Restore Drill Report

- Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")
- Live audit source: \`$LIVE_AUDIT_PATH\`
- Live users source: \`$LIVE_USERS_PATH\`
- Probe workspace: \`$PROBE_DIR\`
- Backup archive: \`$ARCHIVE_PATH\`

## Results

- PASS \`backup-created\`: $BACKUP_OUTPUT
- PASS \`probe-mutated\`: Probe copies were intentionally altered before restore.
- PASS \`restore-completed\`: $RESTORE_OUTPUT
- PASS \`files-restored\`: Restored probe files match the pre-drill snapshot byte-for-byte.
- PASS \`integrity-check\`: $INTEGRITY_OUTPUT

## Notes

- This drill never mutates the live admin data files directly.
- Evidence is produced from a probe copy seeded from the current configured admin stores.
EOF

echo "Report written: $REPORT_PATH"
