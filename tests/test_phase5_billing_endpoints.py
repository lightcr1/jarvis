"""Phase 5 — billing endpoints integration tests.

Tests:
- POST /admin/credits/topup changes balance
- GET /admin/credits/{user_id} returns balance + ledger
- PUT /admin/users/{id}/limits persists limits
- GET /admin/usage returns aggregate + buckets
- GET /auth/me/billing returns balance + limits + recent_usage
"""

import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4


def _setup_env(base: str) -> None:
    os.environ["JARVIS_PASSPHRASE"] = "test-pass"
    os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
    os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
    os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
    os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
    os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
    os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")
    os.environ["JARVIS_CREDIT_STORE_PATH"] = os.path.join(base, "credits.json")
    os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
    os.environ["JARVIS_USAGE_LOG_PATH"] = os.path.join(base, "usage.log")
    os.environ["JARVIS_BYOK_STORE_PATH"] = os.path.join(base, "byok.json")
    os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(base, "chat_history.db")


_ENV_KEYS = [
    "JARVIS_PASSPHRASE",
    "JARVIS_AUDIT_LOG_PATH",
    "JARVIS_USER_STORE_PATH",
    "JARVIS_GROUP_STORE_PATH",
    "JARVIS_MEMBERSHIP_STORE_PATH",
    "JARVIS_PERMISSION_STORE_PATH",
    "JARVIS_ADMIN_SETTINGS_PATH",
    "JARVIS_CREDIT_STORE_PATH",
    "JARVIS_USER_LIMITS_STORE_PATH",
    "JARVIS_USAGE_LOG_PATH",
    "JARVIS_BYOK_STORE_PATH",
    "JARVIS_CHAT_HISTORY_PATH",
]


class Phase5BillingEndpointsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        _setup_env(base)

        jarvisappv4.audit_log = jarvisappv4.AuditLogStore()
        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_settings_store = jarvisappv4.AdminSettingsStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.credit_store = jarvisappv4.CreditStore()
        jarvisappv4.user_limits_store = jarvisappv4.UserLimitsStore()
        jarvisappv4.usage_log_store = jarvisappv4.UsageLogStore()
        jarvisappv4.byok_store = jarvisappv4.ByokKeyStore()
        jarvisappv4._tokens.clear()

        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in _ENV_KEYS:
            os.environ.pop(key, None)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _unlock(self) -> str:
        res = self.client.post("/unlock", json={"passphrase": "test-pass"})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["token"]

    def _admin_headers(self, token: str, user_id: str = "") -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "X-Jarvis-Role": "admin",
            "X-Jarvis-User-Id": user_id,
        }

    def _bootstrap_admin(self) -> tuple[str, str]:
        token = self._unlock()
        res = self.client.post(
            "/admin/users",
            headers=self._admin_headers(token),
            json={"username": "owner", "role": "admin", "enabled": True},
        )
        self.assertEqual(res.status_code, 200, res.text)
        admin_id = res.json()["id"]
        return token, admin_id

    def _create_user_and_session(self, token: str, admin_id: str, username: str = "alice") -> tuple[str, str]:
        res = self.client.post(
            "/admin/users",
            headers=self._admin_headers(token, admin_id),
            json={"username": username, "role": "standard_user", "enabled": True, "password": "pw123456"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        user_id = res.json()["id"]

        login_res = self.client.post("/auth/login", json={"username": username, "password": "pw123456"})
        self.assertEqual(login_res.status_code, 200, login_res.text)
        session_token = login_res.json()["session_token"]
        return user_id, session_token

    # ── POST /admin/credits/topup ─────────────────────────────────────────

    def test_topup_changes_balance(self):
        token, admin_id = self._bootstrap_admin()
        target_id, _ = self._create_user_and_session(token, admin_id)

        res = self.client.post(
            "/admin/credits/topup",
            headers=self._admin_headers(token, admin_id),
            json={"user_id": target_id, "amount_chf": 5.0, "note": "initial grant"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertIn("entry", body)
        entry = body["entry"]
        self.assertEqual(entry["type"], "topup")
        self.assertAlmostEqual(entry["amount_chf"], 5.0)
        self.assertAlmostEqual(entry["balance_after"], 5.0)
        self.assertEqual(entry["note"], "initial grant")

    def test_topup_accumulates_balance(self):
        token, admin_id = self._bootstrap_admin()
        target_id, _ = self._create_user_and_session(token, admin_id)
        hdrs = self._admin_headers(token, admin_id)

        self.client.post("/admin/credits/topup", headers=hdrs, json={"user_id": target_id, "amount_chf": 3.0})
        self.client.post("/admin/credits/topup", headers=hdrs, json={"user_id": target_id, "amount_chf": 2.0})

        res = self.client.get(f"/admin/credits/{target_id}", headers=hdrs)
        self.assertEqual(res.status_code, 200, res.text)
        self.assertAlmostEqual(res.json()["balance_chf"], 5.0)

    def test_topup_requires_admin(self):
        token = self._unlock()
        res = self.client.post(
            "/admin/credits/topup",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "standard_user"},
            json={"user_id": "usr-x", "amount_chf": 1.0},
        )
        self.assertIn(res.status_code, [401, 403])

    def test_topup_rejects_zero_amount(self):
        token, admin_id = self._bootstrap_admin()
        res = self.client.post(
            "/admin/credits/topup",
            headers=self._admin_headers(token, admin_id),
            json={"user_id": "usr-x", "amount_chf": 0.0},
        )
        self.assertEqual(res.status_code, 422)

    # ── GET /admin/credits/{user_id} ──────────────────────────────────────

    def test_get_credits_returns_zero_balance_for_new_user(self):
        token, admin_id = self._bootstrap_admin()
        res = self.client.get(
            "/admin/credits/nonexistent-user",
            headers=self._admin_headers(token, admin_id),
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["user_id"], "nonexistent-user")
        self.assertAlmostEqual(body["balance_chf"], 0.0)
        self.assertIsInstance(body["ledger"], list)
        self.assertEqual(len(body["ledger"]), 0)

    def test_get_credits_returns_ledger_entries(self):
        token, admin_id = self._bootstrap_admin()
        target_id, _ = self._create_user_and_session(token, admin_id)
        hdrs = self._admin_headers(token, admin_id)

        self.client.post("/admin/credits/topup", headers=hdrs, json={"user_id": target_id, "amount_chf": 10.0, "note": "test"})
        self.client.post("/admin/credits/topup", headers=hdrs, json={"user_id": target_id, "amount_chf": 5.0, "note": "extra"})

        res = self.client.get(f"/admin/credits/{target_id}", headers=hdrs)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertAlmostEqual(body["balance_chf"], 15.0)
        self.assertEqual(len(body["ledger"]), 2)

    def test_get_credits_ledger_max_20(self):
        token, admin_id = self._bootstrap_admin()
        hdrs = self._admin_headers(token, admin_id)
        for i in range(25):
            self.client.post("/admin/credits/topup", headers=hdrs, json={"user_id": "bulk-user", "amount_chf": 1.0})

        res = self.client.get("/admin/credits/bulk-user", headers=hdrs)
        self.assertEqual(res.status_code, 200)
        self.assertLessEqual(len(res.json()["ledger"]), 20)

    def test_get_credits_requires_admin(self):
        token = self._unlock()
        res = self.client.get(
            "/admin/credits/usr-x",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "standard_user"},
        )
        self.assertIn(res.status_code, [401, 403])

    # ── PUT /admin/users/{id}/limits ──────────────────────────────────────

    def test_update_limits_persists_values(self):
        token, admin_id = self._bootstrap_admin()
        target_id, _ = self._create_user_and_session(token, admin_id)
        hdrs = self._admin_headers(token, admin_id)

        res = self.client.put(
            f"/admin/users/{target_id}/limits",
            headers=hdrs,
            json={"chf_per_day": 2.5, "chf_per_month": 50.0, "requests_per_min": 10},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertAlmostEqual(body["chf_per_day"], 2.5)
        self.assertAlmostEqual(body["chf_per_month"], 50.0)
        self.assertEqual(body["requests_per_min"], 10)

    def test_update_limits_partial_update(self):
        token, admin_id = self._bootstrap_admin()
        target_id, _ = self._create_user_and_session(token, admin_id)
        hdrs = self._admin_headers(token, admin_id)

        self.client.put(f"/admin/users/{target_id}/limits", headers=hdrs, json={"chf_per_day": 5.0})
        res = self.client.put(f"/admin/users/{target_id}/limits", headers=hdrs, json={"chf_per_month": 100.0})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertAlmostEqual(body["chf_per_day"], 5.0)
        self.assertAlmostEqual(body["chf_per_month"], 100.0)

    def test_update_limits_requires_admin(self):
        token = self._unlock()
        res = self.client.put(
            "/admin/users/usr-x/limits",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "standard_user"},
            json={"chf_per_day": 1.0},
        )
        self.assertIn(res.status_code, [401, 403])

    def test_update_limits_invalid_requests_per_min(self):
        token, admin_id = self._bootstrap_admin()
        res = self.client.put(
            "/admin/users/usr-x/limits",
            headers=self._admin_headers(token, admin_id),
            json={"requests_per_min": 0},
        )
        self.assertEqual(res.status_code, 422)

    # ── GET /admin/usage ──────────────────────────────────────────────────

    def test_usage_returns_aggregate_and_buckets(self):
        token, admin_id = self._bootstrap_admin()
        hdrs = self._admin_headers(token, admin_id)

        res = self.client.get("/admin/usage", headers=hdrs)
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertIn("aggregate", body)
        self.assertIn("daily_buckets", body)
        self.assertIn("recent", body)
        agg = body["aggregate"]
        self.assertIn("request_count", agg)
        self.assertIn("total_cost_chf", agg)

    def test_usage_empty_store(self):
        token, admin_id = self._bootstrap_admin()
        hdrs = self._admin_headers(token, admin_id)

        res = self.client.get("/admin/usage", headers=hdrs)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["aggregate"]["request_count"], 0)
        self.assertEqual(body["recent"], [])
        self.assertIsInstance(body["daily_buckets"], list)

    def test_usage_with_data(self):
        token, admin_id = self._bootstrap_admin()
        hdrs = self._admin_headers(token, admin_id)

        jarvisappv4.usage_log_store.log({
            "user_id": "u1",
            "provider": "openrouter",
            "model": "claude-haiku",
            "billing_mode": "system",
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "estimated_cost_usd": 0.001,
            "estimated_cost_chf": 0.0009,
            "request_status": "ok",
        })

        res = self.client.get("/admin/usage", headers=hdrs)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["aggregate"]["request_count"], 1)
        self.assertEqual(len(body["recent"]), 1)

    def test_usage_filter_by_user_id(self):
        token, admin_id = self._bootstrap_admin()
        hdrs = self._admin_headers(token, admin_id)

        jarvisappv4.usage_log_store.log({"user_id": "u1", "provider": "openrouter", "model": "m1",
                                         "input_tokens": 10, "output_tokens": 5, "total_tokens": 15,
                                         "estimated_cost_usd": 0.0, "estimated_cost_chf": 0.0, "request_status": "ok"})
        jarvisappv4.usage_log_store.log({"user_id": "u2", "provider": "openrouter", "model": "m1",
                                         "input_tokens": 20, "output_tokens": 10, "total_tokens": 30,
                                         "estimated_cost_usd": 0.0, "estimated_cost_chf": 0.0, "request_status": "ok"})

        res = self.client.get("/admin/usage?user_id=u1", headers=hdrs)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["aggregate"]["request_count"], 1)

    def test_usage_requires_admin(self):
        token = self._unlock()
        res = self.client.get(
            "/admin/usage",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "standard_user"},
        )
        self.assertIn(res.status_code, [401, 403])

    # ── GET /auth/me/billing ──────────────────────────────────────────────

    def test_me_billing_returns_balance_limits_usage(self):
        token, admin_id = self._bootstrap_admin()
        target_id, session_token = self._create_user_and_session(token, admin_id)

        # top up some credits
        self.client.post(
            "/admin/credits/topup",
            headers=self._admin_headers(token, admin_id),
            json={"user_id": target_id, "amount_chf": 7.5},
        )

        res = self.client.get(
            "/auth/me/billing",
            headers={"X-Jarvis-Session": session_token},
        )
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["user_id"], target_id)
        self.assertAlmostEqual(body["balance_chf"], 7.5)
        self.assertIn("limits", body)
        self.assertIsInstance(body["limits"], dict)
        self.assertIn("recent_usage", body)
        self.assertIsInstance(body["recent_usage"], list)

    def test_me_billing_zero_balance_for_new_user(self):
        token, admin_id = self._bootstrap_admin()
        _, session_token = self._create_user_and_session(token, admin_id, username="newuser")

        res = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertAlmostEqual(body["balance_chf"], 0.0)
        self.assertEqual(body["recent_usage"], [])

    def test_me_billing_requires_session(self):
        res = self.client.get("/auth/me/billing")
        self.assertIn(res.status_code, [401, 403, 422])

    def test_me_billing_limits_reflect_admin_update(self):
        token, admin_id = self._bootstrap_admin()
        target_id, session_token = self._create_user_and_session(token, admin_id, username="billinguser")

        self.client.put(
            f"/admin/users/{target_id}/limits",
            headers=self._admin_headers(token, admin_id),
            json={"chf_per_day": 3.0},
        )

        res = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertAlmostEqual(body["limits"]["chf_per_day"], 3.0)

    def test_me_billing_recent_usage_limit_10(self):
        token, admin_id = self._bootstrap_admin()
        target_id, session_token = self._create_user_and_session(token, admin_id, username="heavyuser")

        for i in range(15):
            jarvisappv4.usage_log_store.log({
                "user_id": target_id,
                "provider": "openrouter",
                "model": f"model-{i}",
                "input_tokens": 10,
                "output_tokens": 5,
                "total_tokens": 15,
                "estimated_cost_usd": 0.0,
                "estimated_cost_chf": 0.0,
                "request_status": "ok",
            })

        res = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertLessEqual(len(res.json()["recent_usage"]), 10)


if __name__ == "__main__":
    unittest.main()
