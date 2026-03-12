# Jarvis V1 Role & Permission Matrix

This file defines the baseline RBAC model for V1.

## Roles

- `admin`: full platform control, including dangerous actions and user/security management.
- `standard_user`: normal daily assistant usage with bounded action scope.
- `guest_restricted`: read-only or minimal assistant features, no sensitive actions.
- `service_system`: non-human automation role used for trusted internal workflows.

## Permission Domains

- `voice.use` — Use voice command interface.
- `assistant.chat` — Use text chat.
- `devices.read` — View discovered/configured devices.
- `devices.manage` — Add/update/remove devices.
- `calendar.read` — Read calendar data.
- `calendar.write` — Create/update calendar events.
- `email.read` — Read inbox metadata/content per configured policy.
- `email.write` — Send/reply actions.
- `actions.dangerous.execute` — Execute dangerous actions (critical risk).
- `actions.dangerous.approve` — Approve dangerous actions triggered by others/workflows.
- `users.manage` — Create/update/deactivate users.
- `groups.manage` — Create/update groups.
- `permissions.manage` — Assign/revoke permissions.
- `audit.read` — View audit logs.
- `settings.manage` — Manage global system settings.
- `emergency_stop.trigger` — Trigger global action-disable mode.

## Role Matrix

| Permission | admin | standard_user | guest_restricted | service_system |
|---|---:|---:|---:|---:|
| `voice.use` | ✅ | ✅ | ✅* | ❌ |
| `assistant.chat` | ✅ | ✅ | ✅* | ❌ |
| `devices.read` | ✅ | ✅ | ✅ | ✅ |
| `devices.manage` | ✅ | ✅** | ❌ | ✅** |
| `calendar.read` | ✅ | ✅** | ❌ | ✅** |
| `calendar.write` | ✅ | ✅** | ❌ | ✅** |
| `email.read` | ✅ | ✅** | ❌ | ✅** |
| `email.write` | ✅ | ✅** | ❌ | ✅** |
| `actions.dangerous.execute` | ✅ | ❌*** | ❌ | ❌*** |
| `actions.dangerous.approve` | ✅ | ❌ | ❌ | ✅**** |
| `users.manage` | ✅ | ❌ | ❌ | ❌ |
| `groups.manage` | ✅ | ❌ | ❌ | ❌ |
| `permissions.manage` | ✅ | ❌ | ❌ | ❌ |
| `audit.read` | ✅ | ✅**** | ❌ | ✅**** |
| `settings.manage` | ✅ | ❌ | ❌ | ❌ |
| `emergency_stop.trigger` | ✅ | ❌ | ❌ | ✅**** |

### Notes
- `*` Guest access can be disabled globally or per-user in privacy/security settings.
- `**` Allowed only within assigned scope (own resources or approved org scope).
- `***` Can only run via explicit delegated workflow + approval path; never direct by default.
- `****` Service role permissions must be explicitly granted and tightly scoped.

## Enforcement Rules (V1)

1. **Deny by default** for all actions without explicit permission.
2. **Permission check before execution** for every action path (chat, voice, API).
3. **Step-up confirmation** required for dangerous actions.
4. **Audit log write is mandatory** for:
   - permission-denied events
   - dangerous-action requests
   - dangerous-action approvals/executions
   - emergency stop toggles
5. **Emergency stop** must block all non-read actions except recovery/admin controls.
6. **Service role credentials** must be non-interactive and rotatable.

## Suggested Implementation Mapping

- Backend permission resolver in `jarvis_engine.py` and API route guards in `jarvisappv4.py`.
- Persist users/roles/groups/permissions in a DB-backed store for V1 production use.
- Add admin UI tabs in `static/index.html` (or new admin view) for role/permission administration.
