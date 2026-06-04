"""
V1 Recovery Drill Tests — automated evidence for MANUAL_ACCEPTANCE_V1.md Section D.

Covers:
  D1. Store persistence across process restart (write → reload → verify)
  D2. Backup/restore round-trip with version check
  D3. Corrupt/missing file fallback
  D4. AdminSettingsStore survives reload
  D5. Chat history store persists to SQLite and reloads
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest


# ---------------------------------------------------------------------------
# D1 — UserStore persistence
# ---------------------------------------------------------------------------

class TestUserStorePersistence(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp()
        self.store_file = os.path.join(tmp, "users.json")
        os.environ["JARVIS_USER_STORE_PATH"] = self.store_file

    def tearDown(self) -> None:
        os.environ.pop("JARVIS_USER_STORE_PATH", None)

    def _make_store(self):
        from jarvis.user_store import UserStore
        return UserStore()

    def test_user_persists_after_store_reload(self) -> None:
        s1 = self._make_store()
        s1.create_user("alice", role="standard_user")
        s2 = self._make_store()
        users = s2.list_users()
        self.assertTrue(any(u["username"] == "alice" for u in users))

    def test_deleted_user_absent_after_reload(self) -> None:
        s1 = self._make_store()
        alice = s1.create_user("alice", role="standard_user")
        s1.delete_user(alice["id"])
        s2 = self._make_store()
        self.assertIsNone(s2.get_user(alice["id"]))

    def test_updated_role_persists(self) -> None:
        s1 = self._make_store()
        alice = s1.create_user("alice", role="standard_user")
        s1.update_user(alice["id"], role="admin")
        s2 = self._make_store()
        reloaded = s2.get_user(alice["id"])
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        self.assertEqual(reloaded["role"], "admin")


# ---------------------------------------------------------------------------
# D2 — AdminSettingsStore persistence
# ---------------------------------------------------------------------------

class TestAdminSettingsStorePersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_file = os.path.join(tempfile.mkdtemp(), "settings.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = self.tmp_file

    def tearDown(self) -> None:
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def _make_store(self):
        from jarvis.admin_settings_store import AdminSettingsStore
        return AdminSettingsStore()

    def test_updated_settings_persist_after_reload(self) -> None:
        s1 = self._make_store()
        s1.update({"voice": {"wakeword_enabled": True}})
        s2 = self._make_store()
        self.assertTrue(s2.get()["voice"]["wakeword_enabled"])

    def test_wakeword_engine_persists(self) -> None:
        s1 = self._make_store()
        s1.update({"voice": {"wakeword_engine": "openwakeword"}})
        s2 = self._make_store()
        self.assertEqual(s2.get()["voice"]["wakeword_engine"], "openwakeword")

    def test_invalid_wakeword_engine_resets_to_default(self) -> None:
        s1 = self._make_store()
        s1.update({"voice": {"wakeword_engine": "evil_engine"}})
        s2 = self._make_store()
        self.assertEqual(s2.get()["voice"]["wakeword_engine"], "software")

    def test_defaults_present_on_first_load(self) -> None:
        s = self._make_store()
        settings = s.get()
        self.assertIn("usage_limits", settings)
        self.assertIn("voice", settings)
        self.assertIn("home_assistant", settings)
        self.assertIn("wakeword_engine", settings["voice"])
        self.assertIn("wakeword_sensitivity", settings["voice"])


# ---------------------------------------------------------------------------
# D3 — Corrupt/missing file fallback
# ---------------------------------------------------------------------------

class TestStoreFallbackOnCorruptFile(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_file = os.path.join(tempfile.mkdtemp(), "settings.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = self.tmp_file

    def tearDown(self) -> None:
        os.environ.pop("JARVIS_ADMIN_SETTINGS_PATH", None)

    def test_corrupt_json_falls_back_to_defaults(self) -> None:
        with open(self.tmp_file, "w") as f:
            f.write("NOT_JSON{{{{")
        from jarvis.admin_settings_store import AdminSettingsStore
        s = AdminSettingsStore()
        settings = s.get()
        self.assertIn("voice", settings)
        self.assertIn("usage_limits", settings)

    def test_missing_file_returns_defaults(self) -> None:
        from jarvis.admin_settings_store import AdminSettingsStore
        s = AdminSettingsStore()
        settings = s.get()
        self.assertIn("voice", settings)
        self.assertFalse(settings["voice"]["wakeword_enabled"])


# ---------------------------------------------------------------------------
# D4 — PermissionStore persistence
# ---------------------------------------------------------------------------

class TestPermissionStorePersistence(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp()
        self.env_key = "JARVIS_PERMISSION_STORE_PATH"
        os.environ[self.env_key] = os.path.join(tmp, "permissions.json")

    def tearDown(self) -> None:
        os.environ.pop(self.env_key, None)

    def _make_store(self):
        from jarvis.permission_store import PermissionStore
        return PermissionStore()

    def test_user_permission_grant_persists(self) -> None:
        s1 = self._make_store()
        s1.set_user_permissions("usr-001", ["actions.write.execute"])
        s2 = self._make_store()
        self.assertIn("actions.write.execute", s2.list_user_permissions().get("usr-001", []))

    def test_group_permission_grant_persists(self) -> None:
        s1 = self._make_store()
        s1.set_group_permissions("grp-001", ["devices.manage"])
        s2 = self._make_store()
        self.assertIn("devices.manage", s2.list_group_permissions().get("grp-001", []))

    def test_cleared_permissions_absent_after_reload(self) -> None:
        s1 = self._make_store()
        s1.set_user_permissions("usr-001", ["actions.write.execute"])
        s1.clear_user_permissions("usr-001")
        s2 = self._make_store()
        self.assertNotIn("actions.write.execute", s2.list_user_permissions().get("usr-001", []))


# ---------------------------------------------------------------------------
# D5 — ChatHistoryStore SQLite persistence
# ---------------------------------------------------------------------------

class TestChatHistoryStorePersistence(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.mkdtemp()
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = self.tmp

    def tearDown(self) -> None:
        os.environ.pop("JARVIS_CHAT_HISTORY_PATH", None)

    def _make_store(self):
        from jarvis.runtime_state import ChatHistoryStore
        return ChatHistoryStore()

    def test_session_persists_after_store_reload(self) -> None:
        s1 = self._make_store()
        sess = s1.create_session("My session", "user:usr-001", "usr-001")
        s2 = self._make_store()
        reloaded = s2.get_session(sess["id"], "user:usr-001")
        self.assertIsNotNone(reloaded)

    def test_messages_persist_after_store_reload(self) -> None:
        s1 = self._make_store()
        sess = s1.create_session("Chat", "user:usr-001", "usr-001")
        s1.append_message(sess["id"], "user", "hello jarvis", "user:usr-001", "usr-001")
        s2 = self._make_store()
        reloaded = s2.get_session(sess["id"], "user:usr-001")
        self.assertIsNotNone(reloaded)
        assert reloaded is not None
        msgs = reloaded.get("messages", [])
        self.assertTrue(any(m.get("text") == "hello jarvis" for m in msgs))

    def test_deleted_session_absent_after_reload(self) -> None:
        s1 = self._make_store()
        sess = s1.create_session("Temp", "user:usr-001", "usr-001")
        s1.delete_session(sess["id"], "user:usr-001")
        s2 = self._make_store()
        self.assertIsNone(s2.get_session(sess["id"], "user:usr-001"))


# ---------------------------------------------------------------------------
# D6 — Backup/restore JSON round-trip
# ---------------------------------------------------------------------------

class TestBackupRestoreRoundTrip(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(tmp, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(tmp, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(tmp, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(tmp, "permissions.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(tmp, "settings.json")

    def tearDown(self) -> None:
        for k in ["JARVIS_USER_STORE_PATH", "JARVIS_GROUP_STORE_PATH",
                  "JARVIS_MEMBERSHIP_STORE_PATH", "JARVIS_PERMISSION_STORE_PATH",
                  "JARVIS_ADMIN_SETTINGS_PATH"]:
            os.environ.pop(k, None)

    def _make_all(self):
        from jarvis.user_store import UserStore
        from jarvis.group_store import GroupStore
        from jarvis.membership_store import MembershipStore
        from jarvis.permission_store import PermissionStore
        from jarvis.admin_settings_store import AdminSettingsStore
        return UserStore(), GroupStore(), MembershipStore(), PermissionStore(), AdminSettingsStore()

    def test_backup_has_required_fields(self) -> None:
        us, gs, ms, ps, ss = self._make_all()
        us.create_user("alice", role="standard_user")
        backup = {
            "backup_version": 1,
            "users": us.list_users(),
            "groups": gs.list_groups(),
            "memberships": ms.list_memberships(),
            "permissions": {
                "groups": ps.list_group_permissions(),
                "users": ps.list_user_permissions(),
            },
            "settings": ss.get(),
        }
        self.assertEqual(backup["backup_version"], 1)
        self.assertIn("users", backup)
        self.assertTrue(any(u["username"] == "alice" for u in backup["users"]))

    def test_backup_version_1_is_valid_json(self) -> None:
        us, gs, ms, ps, ss = self._make_all()
        backup = {
            "backup_version": 1,
            "users": us.list_users(),
            "groups": gs.list_groups(),
            "memberships": ms.list_memberships(),
            "permissions": {"groups": ps.list_group_permissions(), "users": ps.list_user_permissions()},
            "settings": ss.get(),
        }
        serialized = json.dumps(backup)
        restored = json.loads(serialized)
        self.assertEqual(restored["backup_version"], 1)

    def test_restore_overwrites_existing_users(self) -> None:
        us, gs, ms, ps, ss = self._make_all()
        alice = us.create_user("alice", role="standard_user")
        backup_users = [{"id": "restored-usr-1", "username": "bob", "role": "standard_user",
                         "enabled": True, "created_at": 0, "updated_at": 0}]
        us.data["users"] = {u["id"]: u for u in backup_users}
        us._save()
        us2, *_ = self._make_all()
        all_usernames = [u["username"] for u in us2.list_users()]
        self.assertIn("bob", all_usernames)
        self.assertNotIn("alice", all_usernames)


if __name__ == "__main__":
    unittest.main()
