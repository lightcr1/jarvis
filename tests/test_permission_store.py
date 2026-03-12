import os
import tempfile
import unittest

from jarvis.permission_store import PermissionStore


class PermissionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(self.tmpdir.name, "permissions.json")
        self.store = PermissionStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_PERMISSION_STORE_PATH", None)

    def test_set_and_list_group_permissions(self):
        perms = self.store.set_group_permissions("grp-1", ["voice.use", "voice.use", "actions.write.execute"])
        self.assertEqual(perms, ["voice.use", "actions.write.execute"])
        listed = self.store.list_group_permissions()
        self.assertEqual(listed["grp-1"], ["voice.use", "actions.write.execute"])

    def test_set_and_list_user_permissions(self):
        perms = self.store.set_user_permissions("usr-1", ["audit.read"])
        self.assertEqual(perms, ["audit.read"])
        listed = self.store.list_user_permissions()
        self.assertEqual(listed["usr-1"], ["audit.read"])

    def test_clear_permissions(self):
        self.store.set_group_permissions("grp-1", ["voice.use"])
        self.store.set_user_permissions("usr-1", ["audit.read"])
        self.assertTrue(self.store.clear_group_permissions("grp-1"))
        self.assertTrue(self.store.clear_user_permissions("usr-1"))
        self.assertEqual(self.store.list_group_permissions(), {})
        self.assertEqual(self.store.list_user_permissions(), {})


    def test_invalid_permissions_detection(self):
        invalid = self.store.invalid_permissions(["voice.use", "unknown.permission", ""])
        self.assertEqual(invalid, ["unknown.permission"])

    def test_set_group_permissions_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            self.store.set_group_permissions("grp-1", ["voice.use", "unknown.permission"])
        self.assertEqual(self.store.list_group_permissions(), {})

    def test_set_user_permissions_rejects_invalid_values(self):
        with self.assertRaises(ValueError):
            self.store.set_user_permissions("usr-1", ["audit.read", "bad.permission"])
        self.assertEqual(self.store.list_user_permissions(), {})


if __name__ == "__main__":
    unittest.main()
