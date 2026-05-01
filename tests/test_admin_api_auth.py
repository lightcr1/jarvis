import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4


class AdminApiAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name

        os.environ["JARVIS_PASSPHRASE"] = "test-pass"
        os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")

        jarvisappv4.audit_log = jarvisappv4.AuditLogStore()
        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4._tokens.clear()
        jarvisappv4._identity_tokens.clear()

        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _unlock(self) -> str:
        res = self.client.post("/unlock", json={"passphrase": "test-pass"})
        self.assertEqual(res.status_code, 200)
        return res.json()["token"]

    def test_admin_login_seeds_default_admin_and_returns_identity(self):
        res = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["username"], "admin")
        self.assertEqual(body["role"], "admin")
        self.assertTrue(body["user_id"].startswith("usr-"))
        self.assertTrue(body["token"])

        listing = self.client.get(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {body['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": body["user_id"],
            },
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()["users"][0]["username"], "admin")

    def test_user_login_and_preferences_round_trip(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()

        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "alice", "role": "standard_user", "enabled": True, "password": "alice-pass"},
        )
        self.assertEqual(created.status_code, 200)

        login = self.client.post("/auth/login", json={"username": "alice", "password": "alice-pass"})
        self.assertEqual(login.status_code, 200)
        session_token = login.json()["session_token"]

        update = self.client.put(
            "/auth/me/preferences",
            headers={"X-Jarvis-Session": session_token},
            json={
                "display_name": "Alice",
                "auto_play_voice": False,
                "compact_mode": True,
                "orb_detail": "medium",
                "theme": "light",
                "location": "Munich",
                "notes": ["buy milk", "call doctor"],
            },
        )
        self.assertEqual(update.status_code, 200)
        prefs = update.json()["preferences"]
        self.assertEqual(prefs["display_name"], "Alice")
        self.assertEqual(prefs["theme"], "light")
        self.assertEqual(prefs["location"], "Munich")
        self.assertEqual(prefs["notes"], ["buy milk", "call doctor"])

        me = self.client.get("/auth/me", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["username"], "alice")
        self.assertEqual(me.json()["preferences"]["theme"], "light")
        self.assertEqual(me.json()["preferences"]["location"], "Munich")
        self.assertEqual(me.json()["preferences"]["notes"], ["buy milk", "call doctor"])

    def test_preferences_location_strips_whitespace(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()

        self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]},
            json={"username": "bob", "role": "standard_user", "enabled": True, "password": "bob-pass"},
        )

        session_token = self.client.post("/auth/login", json={"username": "bob", "password": "bob-pass"}).json()["session_token"]

        update = self.client.put(
            "/auth/me/preferences",
            headers={"X-Jarvis-Session": session_token},
            json={"location": "  Berlin  "},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["preferences"]["location"], "Berlin")

    def test_preferences_notes_persist_as_list(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()

        self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]},
            json={"username": "carol", "role": "standard_user", "enabled": True, "password": "carol-pass"},
        )

        session_token = self.client.post("/auth/login", json={"username": "carol", "password": "carol-pass"}).json()["session_token"]

        update = self.client.put(
            "/auth/me/preferences",
            headers={"X-Jarvis-Session": session_token},
            json={"notes": ["item one", "item two", "item three"]},
        )
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.json()["preferences"]["notes"], ["item one", "item two", "item three"])

        # Overwrite with fewer notes
        update2 = self.client.put(
            "/auth/me/preferences",
            headers={"X-Jarvis-Session": session_token},
            json={"notes": ["only one"]},
        )
        self.assertEqual(update2.status_code, 200)
        self.assertEqual(update2.json()["preferences"]["notes"], ["only one"])

    def test_preferences_defaults_include_location_and_notes(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()

        self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]},
            json={"username": "dave", "role": "standard_user", "enabled": True, "password": "dave-pass"},
        )

        session_token = self.client.post("/auth/login", json={"username": "dave", "password": "dave-pass"}).json()["session_token"]

        me = self.client.get("/auth/me", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(me.status_code, 200)
        prefs = me.json()["preferences"]
        self.assertIn("location", prefs)
        self.assertIn("notes", prefs)
        self.assertEqual(prefs["location"], "")
        self.assertEqual(prefs["notes"], [])




    def test_unlock_and_revoke_emit_audit_events(self):
        token = self._unlock()

        issued_events = jarvisappv4.audit_log.read_events(event="unlock_issued", limit=5)
        self.assertGreaterEqual(len(issued_events), 1)
        self.assertIn("expires_in_sec", issued_events[0])
        self.assertIn("token_fingerprint", issued_events[0])

        revoke = self.client.post(
            "/unlock/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(revoke.status_code, 200)

        revoked_events = jarvisappv4.audit_log.read_events(event="unlock_revoked", limit=5)
        self.assertGreaterEqual(len(revoked_events), 1)
        self.assertIn("active_token_count", revoked_events[0])
        self.assertIn("token_fingerprint", revoked_events[0])

    def test_unlock_failure_and_revoke_denied_emit_audit_events(self):
        wrong = self.client.post("/unlock", json={"passphrase": "wrong"})
        self.assertEqual(wrong.status_code, 401)

        denied = self.client.post("/unlock/revoke")
        self.assertEqual(denied.status_code, 401)

        unlock_failed = jarvisappv4.audit_log.read_events(event="unlock_failed", limit=5)
        self.assertGreaterEqual(len(unlock_failed), 1)
        self.assertEqual(unlock_failed[0].get("reason"), "wrong_passphrase")

        revoke_denied = jarvisappv4.audit_log.read_events(event="unlock_revoke_denied", limit=5)
        self.assertGreaterEqual(len(revoke_denied), 1)
        self.assertEqual(revoke_denied[0].get("reason"), "missing_token")

    def test_unlock_uses_safe_defaults_for_invalid_token_env_values(self):
        with patch.dict(
            os.environ,
            {"JARVIS_TOKEN_TTL_MIN": "not-an-int", "JARVIS_MAX_ACTIVE_TOKENS": "invalid"},
            clear=False,
        ):
            token = self._unlock()

        create = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(create.status_code, 200)

    def test_unlock_clamps_low_token_env_values_to_minimum(self):
        with patch.dict(
            os.environ,
            {"JARVIS_TOKEN_TTL_MIN": "0", "JARVIS_MAX_ACTIVE_TOKENS": "0"},
            clear=False,
        ):
            first = self._unlock()
            second = self._unlock()

        blocked = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {first}", "X-Jarvis-Role": "admin"},
        )
        self.assertEqual(blocked.status_code, 401)

        allowed = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {second}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_unlock_honors_max_active_token_capacity(self):
        with patch.dict(os.environ, {"JARVIS_MAX_ACTIVE_TOKENS": "1"}, clear=False):
            first = self._unlock()
            second = self._unlock()

        # First token should be evicted once the second token is issued.
        blocked = self.client.get(
            "/admin/users",
            headers={"Authorization": f"Bearer {first}", "X-Jarvis-Role": "admin"},
        )
        self.assertEqual(blocked.status_code, 401)
        self.assertIn("admin token required", blocked.text)

        allowed = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {second}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(allowed.status_code, 200)

    def test_admin_endpoint_requires_active_token(self):
        res = self.client.get(
            "/admin/users",
            headers={"X-Jarvis-Role": "admin", "X-Jarvis-User-Id": "usr-any"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("admin token required", res.text)

    def test_bootstrap_can_create_first_admin_without_user_id(self):
        token = self._unlock()

        create = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(create.status_code, 200)
        self.assertEqual(create.json()["role"], "admin")

    def test_bootstrap_not_allowed_for_list_users_endpoint(self):
        token = self._unlock()

        listing = self.client.get(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
        )
        self.assertEqual(listing.status_code, 401)
        self.assertIn("admin user required", listing.text)

    def test_bootstrap_cannot_create_non_admin_user(self):
        token = self._unlock()

        create = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "first-user", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(create.status_code, 400)
        self.assertIn("bootstrap can only create admin user", create.text)

    def test_bootstrap_cannot_create_disabled_admin_user(self):
        token = self._unlock()

        create = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": False},
        )
        self.assertEqual(create.status_code, 400)
        self.assertIn("bootstrap admin must be enabled", create.text)

    def test_after_first_user_bootstrap_without_user_id_is_blocked(self):
        token = self._unlock()

        create = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(create.status_code, 200)

        blocked = self.client.get(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
        )
        self.assertEqual(blocked.status_code, 401)
        self.assertIn("admin user required", blocked.text)

    def test_admin_access_succeeds_with_valid_admin_identity(self):
        token = self._unlock()

        create = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(create.status_code, 200)
        user_id = create.json()["id"]

        listing = self.client.get(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": user_id,
            },
        )
        self.assertEqual(listing.status_code, 200)
        self.assertGreaterEqual(len(listing.json().get("users", [])), 1)

    def test_revoked_token_is_rejected_by_admin_endpoints(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        admin_id = first.json()["id"]

        revoke = self.client.post(
            "/unlock/revoke",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(revoke.status_code, 200)
        self.assertTrue(revoke.json().get("ok"))

        listing = self.client.get(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(listing.status_code, 401)
        self.assertIn("admin token required", listing.text)


    def test_unlock_revoke_rejects_falsy_epoch_token_entry(self):
        jarvisappv4._tokens["epoch-zero"] = 0.0

        res = self.client.post(
            "/unlock/revoke",
            headers={"Authorization": "Bearer epoch-zero"},
        )
        self.assertEqual(res.status_code, 401)
        self.assertIn("Token expired or invalid", res.text)
        self.assertNotIn("epoch-zero", jarvisappv4._tokens)

    def test_unlock_revoke_requires_valid_token(self):
        missing = self.client.post("/unlock/revoke")
        self.assertEqual(missing.status_code, 401)
        self.assertIn("Missing token", missing.text)

        invalid = self.client.post(
            "/unlock/revoke",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        self.assertEqual(invalid.status_code, 401)
        self.assertIn("Token expired or invalid", invalid.text)


    def test_inactive_revoke_audit_event_contains_token_fingerprint(self):
        jarvisappv4._tokens["expired-token"] = 1.0

        self.client.post(
            "/unlock/revoke",
            headers={"Authorization": "Bearer expired-token"},
        )

        denied = jarvisappv4.audit_log.read_events(event="unlock_revoke_denied", limit=5)
        inactive = next((e for e in denied if e.get("reason") == "inactive_token"), None)
        self.assertIsNotNone(inactive)
        self.assertIn("token_fingerprint", inactive)

    def test_unlock_revoke_rejects_expired_token_and_prunes_it(self):
        jarvisappv4._tokens["expired-token"] = 1.0

        expired = self.client.post(
            "/unlock/revoke",
            headers={"Authorization": "Bearer expired-token"},
        )
        self.assertEqual(expired.status_code, 401)
        self.assertIn("Token expired or invalid", expired.text)
        self.assertNotIn("expired-token", jarvisappv4._tokens)





    def test_admin_audit_filters_are_case_normalized(self):
        token = self._unlock()

        bootstrap = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(bootstrap.status_code, 200)
        admin_id = bootstrap.json()["id"]

        self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "member", "role": "standard_user", "enabled": True},
        )

        issued = jarvisappv4.audit_log.read_events(event="unlock_issued", limit=1)
        self.assertEqual(len(issued), 1)
        fp_upper = str(issued[0].get("token_fingerprint", "")).upper()

        events = self.client.get(
            f"/admin/audit/events?event=ADMIN_USER_CREATED&role=ADMIN&token_fingerprint={fp_upper}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 200)
        filters = events.json().get("filters", {})
        self.assertEqual(filters.get("event"), "admin_user_created")
        self.assertEqual(filters.get("role"), "admin")
        self.assertEqual(filters.get("token_fingerprint"), fp_upper.lower())

    def test_admin_audit_endpoints_support_token_fingerprint_filter(self):
        token = self._unlock()

        issued_events = jarvisappv4.audit_log.read_events(event="unlock_issued", limit=1)
        self.assertEqual(len(issued_events), 1)
        fingerprint = issued_events[0].get("token_fingerprint")
        self.assertTrue(fingerprint)

        bootstrap = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(bootstrap.status_code, 200)
        admin_id = bootstrap.json()["id"]

        events = self.client.get(
            f"/admin/audit/events?event=unlock_issued&token_fingerprint={fingerprint}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 200)
        body = events.json()
        self.assertGreaterEqual(body.get("count", 0), 1)
        self.assertEqual(body.get("filters", {}).get("token_fingerprint"), fingerprint)

        counts = self.client.get(
            f"/admin/audit/counts?token_fingerprint={fingerprint}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 200)
        self.assertEqual(counts.json().get("filters", {}).get("token_fingerprint"), fingerprint)

    def test_admin_audit_endpoints_support_actor_user_filter(self):
        token = self._unlock()

        bootstrap = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(bootstrap.status_code, 200)
        admin_id = bootstrap.json()["id"]

        self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "member", "role": "standard_user", "enabled": True},
        )

        events = self.client.get(
            f"/admin/audit/events?event=admin_user_created&actor_user_id={admin_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 200)
        body = events.json()
        self.assertGreaterEqual(body.get("count", 0), 1)
        self.assertEqual(body.get("filters", {}).get("actor_user_id"), admin_id)

        counts = self.client.get(
            f"/admin/audit/counts?actor_user_id={admin_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 200)
        self.assertEqual(counts.json().get("filters", {}).get("actor_user_id"), admin_id)

    def test_admin_audit_event_includes_actor_user_id(self):
        token = self._unlock()

        bootstrap = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(bootstrap.status_code, 200)
        admin_id = bootstrap.json()["id"]

        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "member", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(created.status_code, 200)

        events = jarvisappv4.audit_log.read_events(event="admin_user_created", limit=5)
        self.assertGreaterEqual(len(events), 2)
        non_bootstrap = next((e for e in events if e.get("username") == "member"), None)
        self.assertIsNotNone(non_bootstrap)
        self.assertEqual(non_bootstrap.get("actor_user_id"), admin_id)

    def test_admin_create_user_rejects_duplicate_username(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        admin_id = first.json()["id"]

        dup = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "OWNER", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(dup.status_code, 409)
        self.assertIn("username already exists", dup.text)

    def test_admin_create_user_rejects_invalid_role(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        admin_id = first.json()["id"]

        create = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "owner-2", "role": "not_a_role", "enabled": True},
        )
        self.assertEqual(create.status_code, 400)
        self.assertIn("invalid role", create.text)

    def test_admin_update_user_rejects_invalid_role(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        admin_id = first.json()["id"]

        managed_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "member", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(managed_user.status_code, 200)
        member_id = managed_user.json()["id"]

        update = self.client.patch(
            f"/admin/users/{member_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"role": "definitely_invalid"},
        )
        self.assertEqual(update.status_code, 400)
        self.assertIn("invalid role", update.text)

    def test_admin_create_group_rejects_duplicate_name(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        first_group = self.client.post(
            "/admin/groups",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"name": "Admins", "description": "core"},
        )
        self.assertEqual(first_group.status_code, 200)

        dup_group = self.client.post(
            "/admin/groups",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"name": "admins", "description": "duplicate"},
        )
        self.assertEqual(dup_group.status_code, 409)
        self.assertIn("group name already exists", dup_group.text)

    def test_admin_add_assignment_rejects_duplicate_membership(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        managed_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "member", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(managed_user.status_code, 200)
        member_id = managed_user.json()["id"]

        group = self.client.post(
            "/admin/groups",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"name": "Ops", "description": "ops"},
        )
        self.assertEqual(group.status_code, 200)
        group_id = group.json()["id"]

        first_assignment = self.client.post(
            "/admin/assignments",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"user_id": member_id, "group_id": group_id},
        )
        self.assertEqual(first_assignment.status_code, 200)

        dup_assignment = self.client.post(
            "/admin/assignments",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"user_id": member_id, "group_id": group_id},
        )
        self.assertEqual(dup_assignment.status_code, 409)
        self.assertIn("membership already exists", dup_assignment.text)

    def test_admin_set_user_permissions_rejects_invalid_permission(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        managed_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"username": "member", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(managed_user.status_code, 200)
        member_id = managed_user.json()["id"]

        set_perm = self.client.put(
            f"/admin/permissions/users/{member_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
            json={"permissions": ["assistant.chat", "unknown.permission"]},
        )
        self.assertEqual(set_perm.status_code, 400)
        self.assertIn("invalid permissions", set_perm.text)

    def test_admin_audit_events_rejects_invalid_limit(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        res = self.client.get(
            "/admin/audit/events?limit=0",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("limit must be between 1 and 500", res.text)





    def test_admin_audit_events_reject_invalid_event_filter(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        events = self.client.get(
            "/admin/audit/events?event=Bad-Event!",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 400)
        self.assertIn("event must match [a-z0-9_]{1,64}", events.text)

        counts = self.client.get(
            "/admin/audit/counts?event=Bad-Event!",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 400)
        self.assertIn("event must match [a-z0-9_]{1,64}", counts.text)

    def test_admin_audit_endpoints_reject_invalid_role_filter(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        events = self.client.get(
            "/admin/audit/events?role=totally_invalid",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 400)
        self.assertIn("role must be one of", events.text)

        counts = self.client.get(
            "/admin/audit/counts?role=not_a_role",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 400)
        self.assertIn("role must be one of", counts.text)

    def test_admin_audit_endpoints_reject_invalid_actor_user_filter(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        events = self.client.get(
            "/admin/audit/events?actor_user_id=not-a-user-id",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 400)
        self.assertIn("actor_user_id must be 'bootstrap' or match usr-[0-9a-f]{12}", events.text)

        counts = self.client.get(
            "/admin/audit/counts?actor_user_id=bad",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 400)
        self.assertIn("actor_user_id must be 'bootstrap' or match usr-[0-9a-f]{12}", counts.text)

    def test_admin_audit_endpoints_reject_invalid_token_fingerprint_filter(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        events = self.client.get(
            "/admin/audit/events?token_fingerprint=INVALID",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 400)
        self.assertIn("token_fingerprint must be 16 lowercase hex characters", events.text)

        counts = self.client.get(
            "/admin/audit/counts?token_fingerprint=short",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 400)
        self.assertIn("token_fingerprint must be 16 lowercase hex characters", counts.text)




    def test_admin_audit_count_normalizes_blank_filters(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        res = self.client.get(
            "/admin/audit/count?event=%20%20&role=%20%20&actor_user_id=%20%20&token_fingerprint=%20%20",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(res.status_code, 200)
        filters = res.json().get("filters", {})
        self.assertIsNone(filters.get("event"))
        self.assertIsNone(filters.get("role"))
        self.assertIsNone(filters.get("actor_user_id"))
        self.assertIsNone(filters.get("token_fingerprint"))


    def test_admin_audit_count_accepts_uppercase_token_fingerprint(self):
        token = self._unlock()

        bootstrap = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(bootstrap.status_code, 200)
        admin_id = bootstrap.json()["id"]

        issued = jarvisappv4.audit_log.read_events(event="unlock_issued", limit=1)
        self.assertEqual(len(issued), 1)
        fp_upper = str(issued[0].get("token_fingerprint", "")).upper()

        count = self.client.get(
            f"/admin/audit/count?event=UNLOCK_ISSUED&token_fingerprint={fp_upper}",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(count.status_code, 200)
        body = count.json()
        self.assertGreaterEqual(body.get("count", 0), 1)
        self.assertEqual(body.get("filters", {}).get("event"), "unlock_issued")
        self.assertEqual(body.get("filters", {}).get("token_fingerprint"), fp_upper.lower())

    def test_admin_audit_count_endpoint_supports_filters(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        count_res = self.client.get(
            "/admin/audit/count?event=admin_user_created",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(count_res.status_code, 200)
        body = count_res.json()
        self.assertGreaterEqual(body.get("count", 0), 1)
        self.assertEqual(body.get("filters", {}).get("event"), "admin_user_created")

    def test_admin_audit_count_rejects_invalid_token_fingerprint_filter(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        bad = self.client.get(
            "/admin/audit/count?token_fingerprint=INVALID",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(bad.status_code, 400)
        self.assertIn("token_fingerprint must be 16 lowercase hex characters", bad.text)

    def test_admin_audit_counts_supports_event_filter(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        counts = self.client.get(
            "/admin/audit/counts?event=admin_user_created",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 200)
        body = counts.json()
        self.assertEqual(body.get("filters", {}).get("event"), "admin_user_created")
        self.assertEqual(set(body.get("counts", {}).keys()), {"admin_user_created"})


    def test_admin_audit_endpoints_reject_negative_timestamps(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        events_since = self.client.get(
            "/admin/audit/events?since_ts=-1",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events_since.status_code, 400)
        self.assertIn("since_ts must be >= 0", events_since.text)

        events_until = self.client.get(
            "/admin/audit/events?until_ts=-1",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events_until.status_code, 400)
        self.assertIn("until_ts must be >= 0", events_until.text)

        count_single = self.client.get(
            "/admin/audit/count?since_ts=-5",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(count_single.status_code, 400)
        self.assertIn("since_ts must be >= 0", count_single.text)

        counts = self.client.get(
            "/admin/audit/counts?until_ts=-5",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 400)
        self.assertIn("until_ts must be >= 0", counts.text)

    def test_admin_audit_endpoints_reject_invalid_time_range(self):
        token = self._unlock()

        first_user = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
            },
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(first_user.status_code, 200)
        admin_id = first_user.json()["id"]

        events = self.client.get(
            "/admin/audit/events?since_ts=20&until_ts=10",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(events.status_code, 400)
        self.assertIn("since_ts must be <= until_ts", events.text)

        counts = self.client.get(
            "/admin/audit/counts?since_ts=20&until_ts=10",
            headers={
                "Authorization": f"Bearer {token}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin_id,
            },
        )
        self.assertEqual(counts.status_code, 400)
        self.assertIn("since_ts must be <= until_ts", counts.text)

    def test_delete_user_cleans_memberships_and_user_permissions(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        user = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"username": "member", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(user.status_code, 200)
        user_id = user.json()["id"]

        group = self.client.post(
            "/admin/groups",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"name": "Ops", "description": "ops"},
        )
        self.assertEqual(group.status_code, 200)
        group_id = group.json()["id"]

        self.client.post(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"user_id": user_id, "group_id": group_id},
        )
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"permissions": ["assistant.chat"]},
        )

        deleted = self.client.delete(
            f"/admin/users/{user_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(deleted.status_code, 200)

        assignments = self.client.get(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(assignments.status_code, 200)
        self.assertEqual(assignments.json().get("memberships"), [])

        perms = self.client.get(
            "/admin/permissions",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(perms.status_code, 200)
        self.assertNotIn(user_id, perms.json().get("user_permissions", {}))

    def test_delete_group_cleans_memberships_and_group_permissions(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        user = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"username": "member", "role": "standard_user", "enabled": True},
        )
        self.assertEqual(user.status_code, 200)
        user_id = user.json()["id"]

        group = self.client.post(
            "/admin/groups",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"name": "Ops", "description": "ops"},
        )
        self.assertEqual(group.status_code, 200)
        group_id = group.json()["id"]

        self.client.post(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"user_id": user_id, "group_id": group_id},
        )
        self.client.put(
            f"/admin/permissions/groups/{group_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"permissions": ["assistant.chat"]},
        )

        deleted = self.client.delete(
            f"/admin/groups/{group_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(deleted.status_code, 200)

        assignments = self.client.get(
            "/admin/assignments",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(assignments.status_code, 200)
        self.assertEqual(assignments.json().get("memberships"), [])

        perms = self.client.get(
            "/admin/permissions",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(perms.status_code, 200)
        self.assertNotIn(group_id, perms.json().get("group_permissions", {}))

    def test_cannot_delete_last_enabled_admin(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        deleted = self.client.delete(
            f"/admin/users/{admin_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(deleted.status_code, 400)
        self.assertIn("cannot delete last enabled admin", deleted.text)

    def test_deleting_admin_allowed_if_another_enabled_admin_exists(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner1", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        second = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
            json={"username": "owner2", "role": "admin", "enabled": True},
        )
        self.assertEqual(second.status_code, 200)

        deleted = self.client.delete(
            f"/admin/users/{first_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": second.json()["id"]},
        )
        self.assertEqual(deleted.status_code, 200)

    def test_cannot_disable_last_enabled_admin(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        updated = self.client.patch(
            f"/admin/users/{admin_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"enabled": False},
        )
        self.assertEqual(updated.status_code, 400)
        self.assertIn("cannot disable last enabled admin", updated.text)

    def test_disabling_admin_allowed_if_another_enabled_admin_exists(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner1", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        second = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
            json={"username": "owner2", "role": "admin", "enabled": True},
        )
        self.assertEqual(second.status_code, 200)
        second_id = second.json()["id"]

        updated = self.client.patch(
            f"/admin/users/{first_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": second_id},
            json={"enabled": False},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["enabled"])

    def test_cannot_demote_last_enabled_admin(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        updated = self.client.patch(
            f"/admin/users/{admin_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"role": "standard_user"},
        )
        self.assertEqual(updated.status_code, 400)
        self.assertIn("cannot demote last enabled admin", updated.text)

    def test_demoting_admin_allowed_if_another_enabled_admin_exists(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner1", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        second = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
            json={"username": "owner2", "role": "admin", "enabled": True},
        )
        self.assertEqual(second.status_code, 200)
        second_id = second.json()["id"]

        updated = self.client.patch(
            f"/admin/users/{first_id}",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": second_id},
            json={"role": "standard_user"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["role"], "standard_user")

    def test_admin_status_summary_reports_no_orphans_in_clean_state(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        summary = self.client.get(
            "/admin/status/summary",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(summary.status_code, 200)
        body = summary.json()
        self.assertEqual(body["counts"]["enabled_admins"], 1)
        self.assertEqual(body["counts"]["disabled_admins"], 0)
        self.assertTrue(body["counts"]["admin_lockout_risk"])
        self.assertEqual(body["counts"]["admin_lockout_state"], "at_risk")
        self.assertEqual(body["counts"]["orphan_memberships"], 0)
        self.assertEqual(body["counts"]["orphan_group_permission_sets"], 0)
        self.assertEqual(body["counts"]["orphan_user_permission_sets"], 0)

    def test_admin_status_summary_clears_lockout_risk_with_two_enabled_admins(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner1", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        second = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
            json={"username": "owner2", "role": "admin", "enabled": True},
        )
        self.assertEqual(second.status_code, 200)

        summary = self.client.get(
            "/admin/status/summary",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
        )
        self.assertEqual(summary.status_code, 200)
        body = summary.json()
        self.assertEqual(body["counts"]["enabled_admins"], 2)
        self.assertEqual(body["counts"]["disabled_admins"], 0)
        self.assertFalse(body["counts"]["admin_lockout_risk"])
        self.assertEqual(body["counts"]["admin_lockout_state"], "ok")

    def test_admin_status_summary_counts_disabled_admins(self):
        token = self._unlock()

        first = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner1", "role": "admin", "enabled": True},
        )
        self.assertEqual(first.status_code, 200)
        first_id = first.json()["id"]

        second = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
            json={"username": "owner2", "role": "admin", "enabled": False},
        )
        self.assertEqual(second.status_code, 200)

        summary = self.client.get(
            "/admin/status/summary",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": first_id},
        )
        self.assertEqual(summary.status_code, 200)
        body = summary.json()
        self.assertEqual(body["counts"]["enabled_admins"], 1)
        self.assertEqual(body["counts"]["disabled_admins"], 1)
        self.assertTrue(body["counts"]["admin_lockout_risk"])
        self.assertEqual(body["counts"]["admin_lockout_state"], "at_risk")

    def test_admin_status_summary_reports_orphans(self):
        token = self._unlock()

        admin = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(admin.status_code, 200)
        admin_id = admin.json()["id"]

        # Seed orphaned records directly to simulate integrity drift from legacy/manual edits.
        jarvisappv4.membership_store.add_membership("usr-missing", "grp-missing")
        jarvisappv4.permission_store.set_user_permissions("usr-missing", ["assistant.chat"])
        jarvisappv4.permission_store.set_group_permissions("grp-missing", ["assistant.chat"])

        summary = self.client.get(
            "/admin/status/summary",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
        )
        self.assertEqual(summary.status_code, 200)
        body = summary.json()
        self.assertEqual(body["counts"]["enabled_admins"], 1)
        self.assertEqual(body["counts"]["disabled_admins"], 0)
        self.assertTrue(body["counts"]["admin_lockout_risk"])
        self.assertEqual(body["counts"]["admin_lockout_state"], "at_risk")
        self.assertEqual(body["counts"]["orphan_memberships"], 1)
        self.assertEqual(body["counts"]["orphan_group_permission_sets"], 1)
        self.assertEqual(body["counts"]["orphan_user_permission_sets"], 1)
        self.assertEqual(len(body["orphans"]["memberships"]), 1)
        self.assertEqual(body["orphans"]["group_permission_sets"], ["grp-missing"])
        self.assertEqual(body["orphans"]["user_permission_sets"], ["usr-missing"])


if __name__ == "__main__":
    unittest.main()
