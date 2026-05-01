import os
import tempfile
import unittest

from jarvis.user_preferences_store import UserPreferencesStore, DEFAULT_PREFERENCES


class UserPreferencesStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(self.tmpdir.name, "prefs.json")
        self.store = UserPreferencesStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_USER_PREFERENCES_PATH", None)

    def test_get_returns_defaults_for_new_user(self):
        prefs = self.store.get("usr-new")
        self.assertEqual("dark", prefs["theme"])
        self.assertFalse(prefs["compact_mode"])
        self.assertEqual("", prefs["display_name"])
        self.assertEqual([], prefs["notes"])
        self.assertEqual("", prefs["location"])

    def test_update_persists_display_name(self):
        self.store.update("usr-1", {"display_name": "  Alice  "})
        prefs = self.store.get("usr-1")
        self.assertEqual("Alice", prefs["display_name"])

    def test_update_persists_location(self):
        self.store.update("usr-1", {"location": "Munich"})
        prefs = self.store.get("usr-1")
        self.assertEqual("Munich", prefs["location"])

    def test_update_persists_notes(self):
        self.store.update("usr-1", {"notes": ["buy milk", "call doctor"]})
        prefs = self.store.get("usr-1")
        self.assertEqual(["buy milk", "call doctor"], prefs["notes"])

    def test_update_overwrites_notes(self):
        self.store.update("usr-1", {"notes": ["first"]})
        self.store.update("usr-1", {"notes": ["second"]})
        prefs = self.store.get("usr-1")
        self.assertEqual(["second"], prefs["notes"])

    def test_update_theme_only_allows_light_or_dark(self):
        self.store.update("usr-1", {"theme": "light"})
        self.assertEqual("light", self.store.get("usr-1")["theme"])

        self.store.update("usr-1", {"theme": "invalid"})
        self.assertEqual("dark", self.store.get("usr-1")["theme"])

    def test_update_compact_mode(self):
        self.store.update("usr-1", {"compact_mode": True})
        self.assertTrue(self.store.get("usr-1")["compact_mode"])

    def test_update_accent_color(self):
        self.store.update("usr-1", {"accent_color": "#ff8800"})
        self.assertEqual("#ff8800", self.store.get("usr-1")["accent_color"])

    def test_update_accent_color_empty_keeps_current(self):
        self.store.update("usr-1", {"accent_color": "cyan"})
        self.store.update("usr-1", {"accent_color": ""})
        self.assertEqual("cyan", self.store.get("usr-1")["accent_color"])

    def test_update_sets_updated_at_timestamp(self):
        import time
        before = int(time.time())
        prefs = self.store.update("usr-1", {"display_name": "Bob"})
        after = int(time.time())
        self.assertGreaterEqual(prefs["updated_at"], before)
        self.assertLessEqual(prefs["updated_at"], after)

    def test_update_orb_detail(self):
        self.store.update("usr-1", {"orb_detail": "low"})
        self.assertEqual("low", self.store.get("usr-1")["orb_detail"])

    def test_delete_existing_user(self):
        self.store.update("usr-1", {"display_name": "Alice"})
        result = self.store.delete("usr-1")
        self.assertTrue(result)
        prefs = self.store.get("usr-1")
        self.assertEqual("", prefs["display_name"])

    def test_delete_nonexistent_user_returns_false(self):
        result = self.store.delete("usr-ghost")
        self.assertFalse(result)

    def test_get_isolated_per_user(self):
        self.store.update("usr-a", {"display_name": "Alice"})
        self.store.update("usr-b", {"display_name": "Bob"})
        self.assertEqual("Alice", self.store.get("usr-a")["display_name"])
        self.assertEqual("Bob", self.store.get("usr-b")["display_name"])

    def test_persists_across_reload(self):
        self.store.update("usr-1", {"display_name": "Persisted"})
        store2 = UserPreferencesStore()
        self.assertEqual("Persisted", store2.get("usr-1")["display_name"])

    def test_default_preferences_has_all_keys(self):
        for key in ["display_name", "accent_color", "auto_play_voice", "compact_mode",
                    "orb_detail", "theme", "location", "notes"]:
            self.assertIn(key, DEFAULT_PREFERENCES)


class PermissionStoreEdgeCaseTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(self.tmpdir.name, "permissions.json")
        from jarvis.permission_store import PermissionStore
        self.store = PermissionStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_PERMISSION_STORE_PATH", None)

    def test_clear_nonexistent_group_returns_false(self):
        result = self.store.clear_group_permissions("grp-ghost")
        self.assertFalse(result)

    def test_clear_nonexistent_user_returns_false(self):
        result = self.store.clear_user_permissions("usr-ghost")
        self.assertFalse(result)

    def test_empty_permissions_list_allowed(self):
        perms = self.store.set_group_permissions("grp-1", [])
        self.assertEqual([], perms)

    def test_normalize_deduplicates(self):
        perms = self.store.set_group_permissions("grp-1", ["voice.use", "voice.use", "audit.read"])
        self.assertEqual(["voice.use", "audit.read"], perms)

    def test_normalize_strips_empty_strings(self):
        perms = self.store.set_user_permissions("usr-1", ["audit.read"])
        self.assertEqual(["audit.read"], perms)

    def test_invalid_permissions_empty_entry_ignored(self):
        invalid = self.store.invalid_permissions(["voice.use", "", "  "])
        self.assertEqual([], invalid)

    def test_list_group_permissions_returns_copy(self):
        self.store.set_group_permissions("grp-1", ["voice.use"])
        listed = self.store.list_group_permissions()
        listed["grp-1"] = []
        self.assertEqual(["voice.use"], self.store.list_group_permissions()["grp-1"])

    def test_ha_permissions_known(self):
        from jarvis.permission_store import KNOWN_PERMISSIONS
        self.assertIn("home_assistant.access", KNOWN_PERMISSIONS)
        self.assertIn("home_assistant.device_control", KNOWN_PERMISSIONS)


if __name__ == "__main__":
    unittest.main()
