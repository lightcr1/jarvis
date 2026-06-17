---
name: project-admin-patterns
description: Key patterns already implemented in admin pages before polish tasks — search/filter, CSV export, auto-refresh
metadata:
  type: project
---

As of V35/V37, most "missing" features were already partially or fully implemented in admin pages:

**UsersPage** (`frontend/src/routes/admin/pages/UsersPage.tsx`):
- Search input (`search` state + `.filter()` on username/role/id) was already present in the toolbar.
- Bulk select/enable/disable/delete was fully implemented.
- Added in V37: × clear button inside the search input (positioned absolute, right-aligned, only visible when search is non-empty). Input padding shifts right when search is active to avoid text clipping under the ×.

**LogsPage** (`frontend/src/routes/admin/pages/LogsPage.tsx`):
- CSV export (`exportCsv()`) was already implemented with correct `jarvis-audit-{YYYY-MM-DD}.csv` filename.
- Auto-refresh (10s interval via `setInterval`) was already implemented with live/paused toggle.
- `lastRefresh` shown as absolute time with "auto-refreshing every 10s" annotation when active.
- Added in V37: explicit "↺ Refresh" button alongside "Apply" for manual one-shot reload.

**PermissionsPage** (`frontend/src/routes/admin/pages/PermissionsPage.tsx`):
- Checkbox persistence fix was already applied in a prior session (full dep array in useEffect, no eslint-disable).
- The save flow: `updateAdminPermissions` → `load()` → effect fires and re-reads from server → `setSelected(perms)` runs after. Server state wins on reload; `save()` value wins in-session. Both are the same if the server round-trips correctly.

**Why:** The V35 session did a lot of admin UI work that the task specification didn't account for.

**How to apply:** Always read existing files fully before assuming features are missing. Check if the task is already partially done.
