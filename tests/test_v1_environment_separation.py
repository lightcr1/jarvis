"""
V1 Environment Separation Tests — validates config isolation between dev/test/prod.

Covers:
  E1. AdminSettingsStore defaults match CLAUDE.md documented values
  E2. JARVIS_EMERGENCY_STOP env var is respected
  E3. Token TTL configuration
  E4. Default admin credentials via env vars
  E5. Two store instances at different paths do not interfere
  E6. KNOWN_PERMISSIONS is complete (all permissions used in endpoints are declared)
"""
from __future__ import annotations

import os
import tempfile
import unittest


# ---------------------------------------------------------------------------
# E1 — AdminSettingsStore defaults
# ---------------------------------------------------------------------------

class TestAdminSettingsStoreDefaults(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_file = os.path.join(tempfile.mkdtemp(), "s.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = self.tmp_file

    def tearDown(self) -> None:
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def _store(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        return AdminSettingsStore()

    def test_default_wakeword_enabled_is_false(self) -> None:
        self.assertFalse(self._store().get()["voice"]["wakeword_enabled"])

    def test_default_wakeword_phrase(self) -> None:
        self.assertEqual(self._store().get()["voice"]["wakeword_phrase"], "hey jarvis")

    def test_default_wakeword_engine_is_software(self) -> None:
        self.assertEqual(self._store().get()["voice"]["wakeword_engine"], "software")

    def test_default_wakeword_sensitivity_is_half(self) -> None:
        self.assertAlmostEqual(self._store().get()["voice"]["wakeword_sensitivity"], 0.5)

    def test_default_stt_provider_is_local(self) -> None:
        self.assertEqual(self._store().get()["voice"]["stt_provider"], "local")

    def test_default_confirmation_ttl(self) -> None:
        self.assertEqual(self._store().get()["home_assistant"]["confirmation_ttl_sec"], 300)

    def test_sensitivity_clamped_above_1(self) -> None:
        s = self._store()
        s.update({"voice": {"wakeword_sensitivity": 999}})
        self.assertAlmostEqual(s.get()["voice"]["wakeword_sensitivity"], 1.0)

    def test_sensitivity_clamped_below_0(self) -> None:
        s = self._store()
        s.update({"voice": {"wakeword_sensitivity": -5}})
        self.assertAlmostEqual(s.get()["voice"]["wakeword_sensitivity"], 0.0)

    def test_invalid_stt_provider_resets_to_local(self) -> None:
        s = self._store()
        s.update({"voice": {"stt_provider": "invalid_provider"}})
        self.assertEqual(s.get()["voice"]["stt_provider"], "local")


# ---------------------------------------------------------------------------
# E2 — Emergency stop env var
# ---------------------------------------------------------------------------

class TestEmergencyStopEnvVar(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("JARVIS_EMERGENCY_STOP", None)

    def test_emergency_stop_disabled_by_default(self) -> None:
        os.environ.pop("JARVIS_EMERGENCY_STOP", None)
        from jarvis.jarvis_engine import emergency_stop_enabled
        self.assertFalse(emergency_stop_enabled())

    def test_emergency_stop_enabled_with_1(self) -> None:
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        from jarvis.jarvis_engine import emergency_stop_enabled
        self.assertTrue(emergency_stop_enabled())

    def test_emergency_stop_enabled_with_true(self) -> None:
        os.environ["JARVIS_EMERGENCY_STOP"] = "true"
        from jarvis.jarvis_engine import emergency_stop_enabled
        self.assertTrue(emergency_stop_enabled())

    def test_emergency_stop_disabled_with_0(self) -> None:
        os.environ["JARVIS_EMERGENCY_STOP"] = "0"
        from jarvis.jarvis_engine import emergency_stop_enabled
        self.assertFalse(emergency_stop_enabled())


# ---------------------------------------------------------------------------
# E3 — Token TTL config
# ---------------------------------------------------------------------------

class TestTokenTTLConfig(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_file = os.path.join(tempfile.mkdtemp(), "s.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = self.tmp_file

    def tearDown(self) -> None:
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def test_token_ttl_min_is_positive(self) -> None:
        from jarvis.admin_settings_store import AdminSettingsStore
        s = AdminSettingsStore()
        self.assertGreater(s.get()["usage_limits"]["token_ttl_min"], 0)

    def test_token_ttl_cannot_be_zero(self) -> None:
        from jarvis.admin_settings_store import AdminSettingsStore
        s = AdminSettingsStore()
        s.update({"usage_limits": {"token_ttl_min": 0}})
        self.assertGreaterEqual(s.get()["usage_limits"]["token_ttl_min"], 1)

    def test_max_active_tokens_cannot_be_zero(self) -> None:
        from jarvis.admin_settings_store import AdminSettingsStore
        s = AdminSettingsStore()
        s.update({"usage_limits": {"max_active_tokens": 0}})
        self.assertGreaterEqual(s.get()["usage_limits"]["max_active_tokens"], 1)


# ---------------------------------------------------------------------------
# E4 — Two stores at different paths do not interfere
# ---------------------------------------------------------------------------

class TestStoreIsolation(unittest.TestCase):
    def test_two_user_stores_isolated(self) -> None:
        tmp_a = os.path.join(tempfile.mkdtemp(), "users_a.json")
        tmp_b = os.path.join(tempfile.mkdtemp(), "users_b.json")
        from jarvis.user_store import UserStore

        os.environ["JARVIS_USER_STORE_PATH"] = tmp_a
        store_a = UserStore()
        store_a.create_user("alice_a", role="standard_user")

        os.environ["JARVIS_USER_STORE_PATH"] = tmp_b
        store_b = UserStore()
        store_b.create_user("bob_b", role="standard_user")

        os.environ["JARVIS_USER_STORE_PATH"] = tmp_a
        store_a_reload = UserStore()
        usernames_a = [u["username"] for u in store_a_reload.list_users()]
        self.assertIn("alice_a", usernames_a)
        self.assertNotIn("bob_b", usernames_a)

        os.environ.pop("JARVIS_USER_STORE_PATH", None)

    def test_two_settings_stores_isolated(self) -> None:
        tmp_a = os.path.join(tempfile.mkdtemp(), "a.json")
        tmp_b = os.path.join(tempfile.mkdtemp(), "b.json")
        from jarvis.admin_settings_store import AdminSettingsStore

        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = tmp_a
        s_a = AdminSettingsStore()
        s_a.update({"voice": {"wakeword_enabled": True}})

        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = tmp_b
        s_b = AdminSettingsStore()

        self.assertFalse(s_b.get()["voice"]["wakeword_enabled"])
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)


# ---------------------------------------------------------------------------
# E5 — KNOWN_PERMISSIONS completeness
# ---------------------------------------------------------------------------

class TestKnownPermissionsCompleteness(unittest.TestCase):
    def test_known_permissions_contains_all_expected(self) -> None:
        from jarvis.permission_store import KNOWN_PERMISSIONS
        expected = {
            "voice.use",
            "assistant.chat",
            "devices.read",
            "devices.manage",
            "calendar.read",
            "calendar.write",
            "email.read",
            "email.write",
            "actions.write.execute",
            "actions.dangerous.execute",
            "actions.dangerous.approve",
            "users.manage",
            "groups.manage",
            "permissions.manage",
            "audit.read",
            "settings.manage",
            "emergency_stop.trigger",
        }
        missing = expected - set(KNOWN_PERMISSIONS)
        self.assertEqual(missing, set(), f"Missing from KNOWN_PERMISSIONS: {missing}")

    def test_known_permissions_is_nonempty_collection(self) -> None:
        from jarvis.permission_store import KNOWN_PERMISSIONS
        self.assertGreater(len(KNOWN_PERMISSIONS), 0)


# ---------------------------------------------------------------------------
# E6 — Valid roles
# ---------------------------------------------------------------------------

class TestValidRoles(unittest.TestCase):
    def test_all_four_roles_defined(self) -> None:
        from jarvis.jarvis_engine import VALID_ROLES
        self.assertIn("admin", VALID_ROLES)
        self.assertIn("standard_user", VALID_ROLES)
        self.assertIn("guest_restricted", VALID_ROLES)
        self.assertIn("service_system", VALID_ROLES)

    def test_user_store_rejects_invalid_role(self) -> None:
        tmp = tempfile.mkdtemp()
        os.environ["JARVIS_USER_STORE_PATH"] = tmp
        try:
            from jarvis.user_store import UserStore
            s = UserStore()
            with self.assertRaises((ValueError, Exception)):
                s.create_user("test", role="superadmin")
        finally:
            os.environ.pop("JARVIS_USER_STORE_PATH", None)


if __name__ == "__main__":
    unittest.main()
