#!/usr/bin/env bash
set -euo pipefail

AUDIT_PATH="${JARVIS_AUDIT_LOG_PATH:-/var/lib/jarvis/audit.log}"
USERS_PATH="${JARVIS_USER_STORE_PATH:-/var/lib/jarvis/users.json}"
GROUPS_PATH="${JARVIS_GROUP_STORE_PATH:-/var/lib/jarvis/groups.json}"
MEMBERSHIPS_PATH="${JARVIS_MEMBERSHIP_STORE_PATH:-/var/lib/jarvis/memberships.json}"
PERMS_PATH="${JARVIS_PERMISSION_STORE_PATH:-/var/lib/jarvis/permissions.json}"
SETTINGS_PATH="${JARVIS_ADMIN_SETTINGS_PATH:-/var/lib/jarvis/admin_settings.json}"

for p in "$AUDIT_PATH" "$USERS_PATH" "$GROUPS_PATH" "$MEMBERSHIPS_PATH" "$PERMS_PATH" "$SETTINGS_PATH"; do
  if [[ ! -f "$p" ]]; then
    echo "Missing admin data file: $p"
    exit 2
  fi
done

python3 - <<'PY'
import json
import os
import sys
from pathlib import Path

users_path = Path(os.environ.get('JARVIS_USER_STORE_PATH', '/var/lib/jarvis/users.json'))
groups_path = Path(os.environ.get('JARVIS_GROUP_STORE_PATH', '/var/lib/jarvis/groups.json'))
memberships_path = Path(os.environ.get('JARVIS_MEMBERSHIP_STORE_PATH', '/var/lib/jarvis/memberships.json'))
permissions_path = Path(os.environ.get('JARVIS_PERMISSION_STORE_PATH', '/var/lib/jarvis/permissions.json'))
settings_path = Path(os.environ.get('JARVIS_ADMIN_SETTINGS_PATH', '/var/lib/jarvis/admin_settings.json'))
audit_path = Path(os.environ.get('JARVIS_AUDIT_LOG_PATH', '/var/lib/jarvis/audit.log'))

try:
    from jarvis_engine import VALID_ROLES as RUNTIME_VALID_ROLES
except Exception:
    RUNTIME_VALID_ROLES = {'admin', 'standard_user', 'guest_restricted', 'service_system'}

try:
    from permission_store import KNOWN_PERMISSIONS as RUNTIME_KNOWN_PERMISSIONS
except Exception:
    RUNTIME_KNOWN_PERMISSIONS = {
        'voice.use',
        'assistant.chat',
        'devices.read',
        'devices.manage',
        'calendar.read',
        'calendar.write',
        'email.read',
        'email.write',
        'actions.write.execute',
        'actions.dangerous.execute',
        'actions.dangerous.approve',
        'users.manage',
        'groups.manage',
        'permissions.manage',
        'audit.read',
        'settings.manage',
        'emergency_stop.trigger',
    }

VALID_ROLES = set(RUNTIME_VALID_ROLES)
KNOWN_PERMISSIONS = set(RUNTIME_KNOWN_PERMISSIONS)


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'Invalid JSON in {path}: {exc}')
        sys.exit(3)


users = load_json(users_path)
groups = load_json(groups_path)
memberships = load_json(memberships_path)
permissions = load_json(permissions_path)
settings = load_json(settings_path)
fail_on_orphans = (os.environ.get('JARVIS_INTEGRITY_FAIL_ON_ORPHANS', '0') or '0').strip().lower() in {'1', 'true', 'yes', 'on'}
fail_on_admin_lockout = (os.environ.get('JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT', '0') or '0').strip().lower() in {'1', 'true', 'yes', 'on'}
fail_on_duplicate_memberships = (os.environ.get('JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS', '0') or '0').strip().lower() in {'1', 'true', 'yes', 'on'}

if not isinstance(users.get('users'), dict):
    print(f'Invalid structure in {users_path}: expected users object')
    sys.exit(4)
if not isinstance(groups.get('groups'), dict):
    print(f'Invalid structure in {groups_path}: expected groups object')
    sys.exit(4)
if not isinstance(memberships.get('memberships'), list):
    print(f'Invalid structure in {memberships_path}: expected memberships list')
    sys.exit(4)
if not isinstance(permissions.get('group_permissions'), dict) or not isinstance(permissions.get('user_permissions'), dict):
    print(f'Invalid structure in {permissions_path}: expected permission objects')
    sys.exit(4)
if not isinstance(settings.get('usage_limits'), dict) or not isinstance(settings.get('voice'), dict):
    print(f'Invalid structure in {settings_path}: expected usage_limits and voice objects')
    sys.exit(4)

token_ttl_min = settings.get('usage_limits', {}).get('token_ttl_min')
max_active_tokens = settings.get('usage_limits', {}).get('max_active_tokens')
if not isinstance(token_ttl_min, int) or token_ttl_min < 1:
    print(f'Invalid token_ttl_min in {settings_path}: expected integer >= 1')
    sys.exit(4)
if not isinstance(max_active_tokens, int) or max_active_tokens < 1:
    print(f'Invalid max_active_tokens in {settings_path}: expected integer >= 1')
    sys.exit(4)

voice = settings.get('voice', {})
wakeword_enabled = voice.get('wakeword_enabled')
wakeword_phrase = voice.get('wakeword_phrase')
stt_provider = voice.get('stt_provider')
if not isinstance(wakeword_enabled, bool):
    print(f'Invalid wakeword_enabled in {settings_path}: expected boolean')
    sys.exit(4)
if not isinstance(wakeword_phrase, str) or not wakeword_phrase.strip():
    print(f'Invalid wakeword_phrase in {settings_path}: expected non-empty string')
    sys.exit(4)
if stt_provider not in {'local', 'gemini'}:
    print(f'Invalid stt_provider in {settings_path}: expected local or gemini')
    sys.exit(4)

invalid_role_user_ids = [
    uid
    for uid, u in users.get('users', {}).items()
    if not isinstance(u, dict) or (u.get('role') not in VALID_ROLES)
]
if invalid_role_user_ids:
    print(f"Invalid role assignments in {users_path}: {', '.join(sorted(invalid_role_user_ids))}")
    sys.exit(4)


def invalid_permissions(bucket: dict) -> list[str]:
    invalid = []
    for principal_id, perms in bucket.items():
        if not isinstance(perms, list):
            invalid.append(principal_id)
            continue
        for p in perms:
            if not isinstance(p, str) or (p.strip() not in KNOWN_PERMISSIONS):
                invalid.append(principal_id)
                break
    return sorted(set(invalid))


invalid_group_permission_ids = invalid_permissions(permissions.get('group_permissions', {}))
invalid_user_permission_ids = invalid_permissions(permissions.get('user_permissions', {}))
if invalid_group_permission_ids or invalid_user_permission_ids:
    print('Invalid permission assignments detected in permissions store')
    if invalid_group_permission_ids:
        print(f" - invalid group permission sets: {', '.join(invalid_group_permission_ids)}")
    if invalid_user_permission_ids:
        print(f" - invalid user permission sets: {', '.join(invalid_user_permission_ids)}")
    sys.exit(4)

user_ids = set(users.get('users', {}).keys())
group_ids = set(groups.get('groups', {}).keys())

orphan_memberships = []
seen_membership_pairs = set()
duplicate_membership_count = 0
malformed_membership_count = 0
for m in memberships.get('memberships', []):
    if not isinstance(m, dict):
        duplicate_membership_count += 1
        malformed_membership_count += 1
        continue

    user_id = m.get('user_id')
    group_id = m.get('group_id')
    if not isinstance(user_id, str) or not user_id.strip() or not isinstance(group_id, str) or not group_id.strip():
        duplicate_membership_count += 1
        malformed_membership_count += 1
        continue

    pair = (user_id, group_id)
    if pair in seen_membership_pairs:
        duplicate_membership_count += 1
    else:
        seen_membership_pairs.add(pair)

    if (user_id not in user_ids) or (group_id not in group_ids):
        orphan_memberships.append(m)

orphan_user_permission_sets = [uid for uid in permissions.get('user_permissions', {}).keys() if uid not in user_ids]
orphan_group_permission_sets = [gid for gid in permissions.get('group_permissions', {}).keys() if gid not in group_ids]

if duplicate_membership_count:
    print(f'WARNING: duplicate or malformed memberships detected: {duplicate_membership_count}')
    if fail_on_duplicate_memberships:
        sys.exit(8)

enabled_admin_count = sum(
    1
    for u in users.get('users', {}).values()
    if isinstance(u, dict) and u.get('role') == 'admin' and bool(u.get('enabled', False))
)
if enabled_admin_count == 0:
    print('WARNING: no enabled admin users found (admin lockout state: locked_out)')
    if fail_on_admin_lockout:
        sys.exit(7)
elif enabled_admin_count == 1:
    print('WARNING: only one enabled admin user found (admin lockout state: at_risk)')

if orphan_memberships or orphan_user_permission_sets or orphan_group_permission_sets or malformed_membership_count:
    print('WARNING: orphan admin data references detected')
    if orphan_memberships:
        print(f' - orphan memberships: {len(orphan_memberships)}')
    if malformed_membership_count:
        print(f' - malformed memberships: {malformed_membership_count}')
    if orphan_user_permission_sets:
        print(f' - orphan user permission sets: {len(orphan_user_permission_sets)}')
    if orphan_group_permission_sets:
        print(f' - orphan group permission sets: {len(orphan_group_permission_sets)}')
    if fail_on_orphans:
        sys.exit(6)

# Basic audit format check: each non-empty line must be JSON.
for idx, raw in enumerate(audit_path.read_text(encoding='utf-8').splitlines(), start=1):
    if not raw.strip():
        continue
    try:
        json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f'Invalid JSON line in {audit_path}:{idx}: {exc}')
        sys.exit(5)

print('Admin data integrity OK')
PY
