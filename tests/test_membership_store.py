import os
import tempfile
import unittest

from membership_store import MembershipStore


class MembershipStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(self.tmpdir.name, "memberships.json")
        self.store = MembershipStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_MEMBERSHIP_STORE_PATH", None)

    def test_add_and_list_memberships(self):
        self.store.add_membership("usr-1", "grp-1")
        all_items = self.store.list_memberships()
        self.assertEqual(len(all_items), 1)
        self.assertEqual(all_items[0]["user_id"], "usr-1")

    def test_add_membership_rejects_duplicates(self):
        self.store.add_membership("usr-1", "grp-1")
        with self.assertRaises(ValueError):
            self.store.add_membership("usr-1", "grp-1")

    def test_list_user_groups(self):
        self.store.add_membership("usr-1", "grp-1")
        self.store.add_membership("usr-1", "grp-2")
        self.store.add_membership("usr-2", "grp-3")
        groups = self.store.list_user_groups("usr-1")
        self.assertEqual(set(groups), {"grp-1", "grp-2"})

    def test_remove_membership(self):
        self.store.add_membership("usr-1", "grp-1")
        removed = self.store.remove_membership("usr-1", "grp-1")
        self.assertTrue(removed)
        self.assertEqual(self.store.list_memberships(), [])

    def test_remove_user_memberships(self):
        self.store.add_membership("usr-1", "grp-1")
        self.store.add_membership("usr-1", "grp-2")
        self.store.add_membership("usr-2", "grp-2")
        removed = self.store.remove_user_memberships("usr-1")
        self.assertEqual(removed, 2)
        items = self.store.list_memberships()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["user_id"], "usr-2")
        self.assertEqual(items[0]["group_id"], "grp-2")

    def test_remove_group_memberships(self):
        self.store.add_membership("usr-1", "grp-1")
        self.store.add_membership("usr-2", "grp-1")
        self.store.add_membership("usr-2", "grp-2")
        removed = self.store.remove_group_memberships("grp-1")
        self.assertEqual(removed, 2)
        items = self.store.list_memberships()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["group_id"], "grp-2")


if __name__ == "__main__":
    unittest.main()
