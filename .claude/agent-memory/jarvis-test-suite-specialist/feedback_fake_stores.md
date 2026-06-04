---
name: feedback-fake-stores
description: Fake UserStore for tests must expose .data["users"] and ._save() for backup/restore compatibility
metadata:
  type: feedback
---

The `/admin/backup/restore` endpoint directly mutates `store.data["users"]` and calls `store._save()` — these are attributes of the real `UserStore`. When using a fake `_FakeUserStore` for scenario tests, the fake must:

1. Expose `self.data = {"users": self.users}` (where `self.users` is the dict)
2. Implement `def _save(self): self.users = self.data["users"]` (no-op sync)
3. All internal methods (get_user, list_users, find_by_username, create_user, delete_user, etc.) must read from `self.data["users"]` not `self.users` directly, because restore replaces `self.data["users"]` with a new dict object.

**Why:** The backup restore endpoint does `us.data["users"] = {u["id"]: u for u in users ...}` which replaces the dict reference. If methods still point to the old `self.users` reference, they won't see the restored state.

**How to apply:** In any fake user store used with the admin backup/restore endpoint, ensure the `data` dict attribute is present and all reads go through `self.data["users"]`.
