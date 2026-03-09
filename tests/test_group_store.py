import os
import tempfile
import unittest

from group_store import GroupStore


class GroupStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(self.tmpdir.name, "groups.json")
        self.store = GroupStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_GROUP_STORE_PATH", None)

    def test_create_list_get_group(self):
        created = self.store.create_group("admins", description="admin group")
        self.assertTrue(created["id"].startswith("grp-"))

        listed = self.store.list_groups()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["name"], "admins")

        fetched = self.store.get_group(created["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["description"], "admin group")

    def test_update_group(self):
        created = self.store.create_group("ops")
        updated = self.store.update_group(created["id"], name="ops-team", description="ops team")
        self.assertIsNotNone(updated)
        self.assertEqual(updated["name"], "ops-team")
        self.assertEqual(updated["description"], "ops team")

    def test_delete_group(self):
        created = self.store.create_group("guests")
        deleted = self.store.delete_group(created["id"])
        self.assertTrue(deleted)
        self.assertEqual(self.store.list_groups(), [])

    def test_create_group_rejects_duplicate_name_case_insensitive(self):
        self.store.create_group("Admins")
        with self.assertRaises(ValueError):
            self.store.create_group("admins")

    def test_update_group_rejects_duplicate_name_case_insensitive(self):
        one = self.store.create_group("Ops")
        self.store.create_group("Guests")
        with self.assertRaises(ValueError):
            self.store.update_group(one["id"], name="guests")


if __name__ == "__main__":
    unittest.main()
