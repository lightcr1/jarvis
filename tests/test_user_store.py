import os
import tempfile
import unittest

from user_store import UserStore


class UserStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(self.tmpdir.name, "users.json")
        self.store = UserStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_USER_STORE_PATH", None)

    def test_create_list_get_user(self):
        created = self.store.create_user("alice", role="standard_user")
        self.assertTrue(created["id"].startswith("usr-"))

        listed = self.store.list_users()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["username"], "alice")

        fetched = self.store.get_user(created["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["role"], "standard_user")

    def test_update_user(self):
        created = self.store.create_user("bob", role="guest_restricted")
        updated = self.store.update_user(created["id"], role="admin", enabled=False)
        self.assertIsNotNone(updated)
        self.assertEqual(updated["role"], "admin")
        self.assertFalse(updated["enabled"])

    def test_delete_user(self):
        created = self.store.create_user("carol")
        deleted = self.store.delete_user(created["id"])
        self.assertTrue(deleted)
        self.assertEqual(self.store.list_users(), [])

    def test_create_user_rejects_duplicate_username_case_insensitive(self):
        self.store.create_user("Alice")
        with self.assertRaises(ValueError):
            self.store.create_user("alice")

    def test_create_user_rejects_invalid_role(self):
        with self.assertRaises(ValueError):
            self.store.create_user("dave", role="superadmin")

    def test_update_user_rejects_invalid_role(self):
        created = self.store.create_user("erin", role="standard_user")
        with self.assertRaises(ValueError):
            self.store.update_user(created["id"], role="root")

    def test_enabled_admin_count(self):
        self.store.create_user("a1", role="admin", enabled=True)
        self.store.create_user("a2", role="admin", enabled=False)
        self.store.create_user("u1", role="standard_user", enabled=True)
        self.assertEqual(self.store.enabled_admin_count(), 1)


if __name__ == "__main__":
    unittest.main()
