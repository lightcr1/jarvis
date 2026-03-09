import os
import tempfile
import unittest

from authz import build_permission_context, permission_decision, resolve_effective_permissions
from group_store import GroupStore
from membership_store import MembershipStore
from permission_store import PermissionStore
from user_store import UserStore


class AuthzResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(self.tmpdir.name, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(self.tmpdir.name, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(self.tmpdir.name, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(self.tmpdir.name, "permissions.json")

        self.users = UserStore()
        self.groups = GroupStore()
        self.memberships = MembershipStore()
        self.permissions = PermissionStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        for k in [
            "JARVIS_USER_STORE_PATH",
            "JARVIS_GROUP_STORE_PATH",
            "JARVIS_MEMBERSHIP_STORE_PATH",
            "JARVIS_PERMISSION_STORE_PATH",
        ]:
            os.environ.pop(k, None)

    def test_role_permissions_are_included(self):
        perms = resolve_effective_permissions("admin", None, self.memberships, self.permissions)
        self.assertIn("actions.write.execute", perms)
        self.assertIn("actions.dangerous.execute", perms)

    def test_user_and_group_permissions_are_combined(self):
        u = self.users.create_user("alice", role="standard_user")
        g = self.groups.create_group("ops")
        self.memberships.add_membership(u["id"], g["id"])
        self.permissions.set_user_permissions(u["id"], ["audit.read"])
        self.permissions.set_group_permissions(g["id"], ["actions.write.execute"])

        perms = resolve_effective_permissions("standard_user", u["id"], self.memberships, self.permissions)
        self.assertIn("voice.use", perms)
        self.assertIn("audit.read", perms)
        self.assertIn("actions.write.execute", perms)


    def test_build_permission_context_contains_breakdown(self):
        u = self.users.create_user("bob", role="standard_user")
        g = self.groups.create_group("ops")
        self.memberships.add_membership(u["id"], g["id"])
        self.permissions.set_user_permissions(u["id"], ["audit.read"])
        self.permissions.set_group_permissions(g["id"], ["actions.write.execute"])

        ctx = build_permission_context("standard_user", u["id"], self.memberships, self.permissions)
        self.assertEqual(ctx["role"], "standard_user")
        self.assertIn("voice.use", ctx["role_permissions"])
        self.assertIn("audit.read", ctx["user_permissions"])
        self.assertIn(g["id"], ctx["group_ids"])
        self.assertIn("actions.write.execute", ctx["group_permissions"][g["id"]])
        self.assertIn("actions.write.execute", ctx["effective_permissions"])


    def test_permission_decision_identifies_source(self):
        u = self.users.create_user("charlie", role="standard_user")
        g = self.groups.create_group("ops")
        self.memberships.add_membership(u["id"], g["id"])
        self.permissions.set_group_permissions(g["id"], ["actions.write.execute"])

        decision = permission_decision("standard_user", u["id"], "actions.write.execute", self.memberships, self.permissions)
        self.assertTrue(decision["allowed"])
        self.assertTrue((decision["source"] or "").startswith("group:"))

        denied = permission_decision("standard_user", u["id"], "actions.dangerous.execute", self.memberships, self.permissions)
        self.assertFalse(denied["allowed"])
        self.assertIsNone(denied["source"])


if __name__ == "__main__":
    unittest.main()
