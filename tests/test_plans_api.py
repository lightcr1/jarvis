import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4


class PlansApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_PLAN_STORE_PATH"] = os.path.join(base, "plans.json")
        os.environ["JARVIS_CREDIT_STORE_PATH"] = os.path.join(base, "credits.json")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")
        os.environ["JARVIS_USAGE_LOG_PATH"] = os.path.join(base, "usage.jsonl")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.plan_store = jarvisappv4.PlanStore()
        jarvisappv4.credit_store = jarvisappv4.CreditStore()
        jarvisappv4.user_limits_store = jarvisappv4.UserLimitsStore()
        jarvisappv4.admin_settings_store = jarvisappv4.AdminSettingsStore()
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _admin_headers(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        return {
            "Authorization": f"Bearer {admin['token']}",
            "X-Jarvis-Role": "admin",
            "X-Jarvis-User-Id": admin["user_id"],
        }

    def _create_standard_user(self, headers, username):
        created = self.client.post(
            "/admin/users",
            headers=headers,
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        self.assertEqual(200, created.status_code)
        user_id = created.json()["id"]
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        self.assertEqual(200, login.status_code)
        return user_id, login.json()["session_token"]

    def test_list_plans_requires_admin(self):
        resp = self.client.get("/admin/plans")
        self.assertEqual(401, resp.status_code)

    def test_list_plans_includes_seeded_defaults(self):
        headers = self._admin_headers()
        resp = self.client.get("/admin/plans", headers=headers)
        self.assertEqual(200, resp.status_code)
        names = [p["name"] for p in resp.json()["plans"]]
        self.assertIn("Free", names)
        self.assertIn("Standard", names)
        self.assertIn("Pro", names)

    def test_create_update_delete_plan(self):
        headers = self._admin_headers()
        created = self.client.post(
            "/admin/plans",
            headers=headers,
            json={"name": "Team", "price_chf_per_month": 50, "ai_credit_chf_monthly": 60, "storage_gb_included": 500, "sort_order": 3},
        )
        self.assertEqual(201, created.status_code)
        plan_id = created.json()["plan"]["id"]

        updated = self.client.patch(f"/admin/plans/{plan_id}", headers=headers, json={"price_chf_per_month": 45})
        self.assertEqual(200, updated.status_code)
        self.assertEqual(45.0, updated.json()["plan"]["price_chf_per_month"])

        deleted = self.client.delete(f"/admin/plans/{plan_id}", headers=headers)
        self.assertEqual(200, deleted.status_code)

        missing_update = self.client.patch(f"/admin/plans/{plan_id}", headers=headers, json={"price_chf_per_month": 1})
        self.assertEqual(404, missing_update.status_code)

    def test_assign_plan_to_user_grants_credit_and_billing_reflects_it(self):
        headers = self._admin_headers()
        user_id, session_token = self._create_standard_user(headers, "alice")

        assigned = self.client.put(f"/admin/users/{user_id}/plan", headers=headers, json={"plan_id": "plan-standard"})
        self.assertEqual(200, assigned.status_code)
        self.assertEqual("plan-standard", assigned.json()["plan_id"])

        billing = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, billing.status_code)
        data = billing.json()
        self.assertEqual(10.0, data["balance_chf"])
        self.assertEqual("Standard", data["plan"]["name"])
        self.assertGreaterEqual(len(data["plans"]), 3)
        self.assertIn("storage", data)
        self.assertIn("estimated_overage_chf", data["storage"])

    def test_assign_unknown_plan_returns_404(self):
        headers = self._admin_headers()
        user_id, _ = self._create_standard_user(headers, "bob")
        resp = self.client.put(f"/admin/users/{user_id}/plan", headers=headers, json={"plan_id": "plan-nope"})
        self.assertEqual(404, resp.status_code)

    def test_billing_without_plan_has_no_plan_but_lists_options(self):
        headers = self._admin_headers()
        _, session_token = self._create_standard_user(headers, "carol")
        billing = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, billing.status_code)
        data = billing.json()
        self.assertIsNone(data["plan"])
        self.assertGreaterEqual(len(data["plans"]), 3)


if __name__ == "__main__":
    unittest.main()
