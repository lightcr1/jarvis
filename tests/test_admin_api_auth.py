import os
import tempfile
import unittest

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

        jarvisappv4.audit_log = jarvisappv4.AuditLogStore()
        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4._tokens.clear()

        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _unlock(self) -> str:
        res = self.client.post("/unlock", json={"passphrase": "test-pass"})
        self.assertEqual(res.status_code, 200)
        return res.json()["token"]

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
