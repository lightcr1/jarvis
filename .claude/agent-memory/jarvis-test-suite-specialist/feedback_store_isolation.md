---
name: feedback-store-isolation
description: How to avoid disk writes in tests — GroupStore/MembershipStore/PermissionStore write to /var/lib/jarvis by default
metadata:
  type: feedback
---

`GroupStore`, `MembershipStore`, and `PermissionStore` default to writing to `/var/lib/jarvis/*.json`, which is permission-denied in CI. Two patterns work:

1. **Env var redirect** (for real store instances): set `JARVIS_GROUP_STORE_PATH`, `JARVIS_MEMBERSHIP_STORE_PATH`, `JARVIS_PERMISSION_STORE_PATH` to paths in a `tempfile.mkdtemp()` directory before instantiating the stores, then restore them afterward.

2. **Pure fake stores** (for unit tests): implement `list_group_permissions()`, `list_user_permissions()`, `set_group_permissions()`, `set_user_permissions()`, `clear_group_permissions()`, `clear_user_permissions()`, `invalid_permissions()`, `list_memberships()`, `list_user_groups()`, `add_membership()`, `remove_membership()`, `remove_user_memberships()`, `remove_group_memberships()` as in-memory dicts — no disk writes.

**Why:** `/var/lib/jarvis/` is not writable in the test environment. Without isolation, Scenario 2 and similar group-based tests throw `PermissionError`.

**How to apply:** For acceptance-level tests that need real authz resolution with `resolve_effective_permissions()`, use env var redirect pattern (pattern 1). For unit tests of individual endpoints, use pure fake stores (pattern 2). See `test_acceptance_scenarios.py::_make_stores()` for pattern 1 and `test_api_uncovered_endpoints.py::_FakePermissionStore` for pattern 2.
