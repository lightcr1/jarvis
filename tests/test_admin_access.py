import time
import unittest

from fastapi import HTTPException

from admin_access import require_admin_access


class _Store:
    def __init__(self, users):
        self._users = users

    def get_user(self, user_id):
        return self._users.get(user_id)

    def list_users(self):
        return list(self._users.values())


class TestAdminAccess(unittest.TestCase):
    def test_accepts_enabled_admin_with_active_token_and_matching_role_header(self):
        store = _Store({"u1": {"id": "u1", "role": "admin", "enabled": True}})
        tokens = {"t1": time.time() + 60}

        user_id, role = require_admin_access(store, tokens, "u1", "admin", "Bearer t1")
        self.assertEqual(user_id, "u1")
        self.assertEqual(role, "admin")

    def test_rejects_role_header_spoof_when_user_is_not_admin(self):
        store = _Store({"u2": {"id": "u2", "role": "standard_user", "enabled": True}})
        tokens = {"t1": time.time() + 60}

        with self.assertRaises(HTTPException) as ctx:
            require_admin_access(store, tokens, "u2", "admin", "Bearer t1")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "admin role required")

    def test_rejects_mismatched_role_header_even_for_admin_user(self):
        store = _Store({"u3": {"id": "u3", "role": "admin", "enabled": True}})
        tokens = {"t1": time.time() + 60}

        with self.assertRaises(HTTPException) as ctx:
            require_admin_access(store, tokens, "u3", "guest_restricted", "Bearer t1")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "role header mismatch")

    def test_bootstrap_mode_allows_admin_header_when_no_users_exist(self):
        store = _Store({})
        tokens = {"t1": time.time() + 60}

        user_id, role = require_admin_access(store, tokens, None, "admin", "Bearer t1", allow_bootstrap=True)
        self.assertEqual(user_id, "bootstrap")
        self.assertEqual(role, "admin")

    def test_bootstrap_mode_requires_opt_in(self):
        store = _Store({})
        tokens = {"t1": time.time() + 60}

        with self.assertRaises(HTTPException) as ctx:
            require_admin_access(store, tokens, None, "admin", "Bearer t1")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "admin user required")

    def test_bootstrap_mode_rejects_non_admin_header(self):
        store = _Store({})
        tokens = {"t1": time.time() + 60}

        with self.assertRaises(HTTPException) as ctx:
            require_admin_access(store, tokens, None, "standard_user", "Bearer t1", allow_bootstrap=True)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "admin user required")


if __name__ == "__main__":
    unittest.main()
