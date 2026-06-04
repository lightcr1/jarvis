---
name: project-permissions-bug
description: Root cause of PermissionsPage checkbox reset bug and the correct fix
metadata:
  type: project
---

**Bug:** Checkboxes in PermissionsPage reset when switching scope (users ↔ groups) or when permissions are refetched.

**Root cause:** The `useEffect([permissions, scope])` had an `// eslint-disable-next-line react-hooks/exhaustive-deps` comment to suppress the missing `target` dependency. This meant the effect captured a stale `target` value. When scope changed, `target` still held the old scope's ID, which when looked up in the new scope's permission map returned `[]`, resetting all checkboxes.

**Fix applied:** Replaced the eslint-suppressed effect with a proper effect that includes all dependencies (`permissions`, `scope`, `target`, `targetOptions`, `user?.id`). The effect now:
1. Checks if `target` is valid in the current `targetOptions` set.
2. If valid: re-reads `selected` from fresh permissions for that target (handles reload + scope-stable permission refresh).
3. If invalid (scope changed, stale target): picks the preferred/first valid target, resets status/error/effective, and reads permissions for the new target.

**Key insight:** Including `target` in deps seemed like it would cause infinite loops (effect sets target → target changes → effect fires again). But `setTarget(next)` is only called in the `else` branch when `target` is NOT in `validIds`. Once `setTarget(next)` runs, on re-fire `target = next` which IS in `validIds`, so the `if` branch runs and doesn't call `setTarget` again → stable.

**File:** `frontend/src/routes/admin/pages/PermissionsPage.tsx`, the useEffect at ~line 72.
