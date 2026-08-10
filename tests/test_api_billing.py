from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.secret_crypto import generate_master_key


class _FakeStripeServer:
    def __init__(self, status: int = 200, response_body: dict | None = None):
        self.response_body = response_body if response_body is not None else {"id": "cs_test_1", "url": "https://checkout.stripe.com/pay/cs_test_1"}
        self.status = status
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self):
                content_length = int(self.headers.get("Content-Length", "0"))
                if content_length:
                    self.rfile.read(content_length)
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(outer.response_body).encode("utf-8"))

            def do_GET(self):  # noqa: N802
                self._handle()

            def do_POST(self):  # noqa: N802
                self._handle()

            def log_message(self, format, *args):  # noqa: A003
                return

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        os.environ["JARVIS_STRIPE_API_BASE"] = f"http://127.0.0.1:{self.server.server_port}"
        return self

    def __exit__(self, *exc):
        os.environ.pop("JARVIS_STRIPE_API_BASE", None)
        self.server.shutdown()
        self.thread.join(timeout=2)


class BillingApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_PLAN_STORE_PATH"] = os.path.join(base, "plans.json")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_CREDIT_STORE_PATH"] = os.path.join(base, "credits.json")
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "integration_credentials.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.plan_store = jarvisappv4.PlanStore()
        jarvisappv4.user_limits_store = jarvisappv4.UserLimitsStore()
        jarvisappv4.credit_store = jarvisappv4.CreditStore()
        jarvisappv4.integration_credential_store = jarvisappv4.IntegrationCredentialStore()
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

        self.admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()

    def tearDown(self):
        os.environ.pop("JARVIS_STRIPE_API_BASE", None)
        self.tmpdir.cleanup()

    def _admin_headers(self):
        return {"Authorization": f"Bearer {self.admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": self.admin["user_id"]}

    def _create_user(self, username, *, permissions=None):
        created = self.client.post("/admin/users", headers=self._admin_headers(),
                                    json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pw"})
        user_id = created.json()["id"]
        if permissions:
            self.client.put(f"/admin/permissions/users/{user_id}", headers=self._admin_headers(), json={"permissions": permissions})
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pw"})
        return user_id, login.json()["session_token"]

    def _create_plan(self, *, stripe_price_id=""):
        return self.client.post("/admin/plans", headers=self._admin_headers(),
                                 json={"name": "Pro", "price_chf_per_month": 20, "ai_credit_chf_monthly": 10, "storage_gb_included": 50, "stripe_price_id": stripe_price_id}).json()["plan"]

    def test_no_permission_user_gets_403(self):
        _, token = self._create_user("noperm")
        resp = self.client.get("/billing/stripe/status", headers={"X-Jarvis-Session": token})
        self.assertEqual(403, resp.status_code)

    def test_billing_manage_user_can_configure_and_test_stripe(self):
        _, token = self._create_user("finance", permissions=["billing.manage"])
        headers = {"X-Jarvis-Session": token}

        unset = self.client.get("/billing/stripe/status", headers=headers)
        self.assertEqual(200, unset.status_code)
        self.assertFalse(unset.json()["configured"])

        put = self.client.put("/billing/stripe/credentials", headers=headers,
                               json={"secret_key": "sk_test_abcdefghijklmnop", "webhook_secret": "whsec_test123"})
        self.assertEqual(200, put.status_code)

        status = self.client.get("/billing/stripe/status", headers=headers).json()
        self.assertTrue(status["configured"])
        self.assertTrue(status["has_webhook_secret"])
        self.assertNotIn("sk_test_abcdefghijklmnop", json.dumps(status))

        with _FakeStripeServer(200, {"object": "balance"}):
            test_result = self.client.post("/billing/stripe/test", headers=headers)
        self.assertTrue(test_result.json()["ok"])

        cleared = self.client.delete("/billing/stripe/credentials", headers=headers)
        self.assertFalse(cleared.json()["configured"])

    def test_admin_can_configure_stripe_without_explicit_grant(self):
        admin_login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(200, admin_login.status_code)
        session_headers = {"X-Jarvis-Session": admin_login.json()["session_token"]}
        put = self.client.put("/billing/stripe/credentials", headers=session_headers,
                               json={"secret_key": "sk_test_admin", "webhook_secret": "whsec_admin"})
        self.assertEqual(200, put.status_code)

    def test_checkout_session_requires_plan_with_stripe_price(self):
        _, token = self._create_user("buyer1")
        plan = self._create_plan(stripe_price_id="")
        resp = self.client.post("/billing/checkout-session", headers={"X-Jarvis-Session": token}, json={"plan_id": plan["id"]})
        self.assertEqual(400, resp.status_code)

    def test_checkout_session_requires_stripe_configured(self):
        _, token = self._create_user("buyer2")
        plan = self._create_plan(stripe_price_id="price_123")
        resp = self.client.post("/billing/checkout-session", headers={"X-Jarvis-Session": token}, json={"plan_id": plan["id"]})
        self.assertEqual(503, resp.status_code)

    def test_checkout_session_happy_path(self):
        _, finance_token = self._create_user("finance2", permissions=["billing.manage"])
        self.client.put("/billing/stripe/credentials", headers={"X-Jarvis-Session": finance_token},
                         json={"secret_key": "sk_test_ok", "webhook_secret": "whsec_ok"})
        _, buyer_token = self._create_user("buyer3")
        plan = self._create_plan(stripe_price_id="price_123")

        with _FakeStripeServer(200, {"id": "cs_1", "url": "https://checkout.stripe.com/pay/cs_1"}):
            resp = self.client.post("/billing/checkout-session", headers={"X-Jarvis-Session": buyer_token}, json={"plan_id": plan["id"]})
        self.assertEqual(200, resp.status_code)
        self.assertEqual("https://checkout.stripe.com/pay/cs_1", resp.json()["checkout_url"])

    def _sign(self, payload: bytes, secret: str) -> str:
        timestamp = int(time.time())
        signed_payload = f"{timestamp}.".encode("utf-8") + payload
        signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={signature}"

    def test_webhook_without_stripe_configured_returns_503(self):
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode()
        resp = self.client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": "t=1,v1=x"})
        self.assertEqual(503, resp.status_code)

    def test_webhook_assigns_plan_on_checkout_completed(self):
        _, finance_token = self._create_user("finance3", permissions=["billing.manage"])
        self.client.put("/billing/stripe/credentials", headers={"X-Jarvis-Session": finance_token},
                         json={"secret_key": "sk_test_ok", "webhook_secret": "whsec_ok"})
        buyer_id, _ = self._create_user("buyer4")
        plan = self._create_plan(stripe_price_id="price_123")

        payload = json.dumps({
            "type": "checkout.session.completed",
            "data": {"object": {"mode": "subscription", "metadata": {"user_id": buyer_id, "plan_id": plan["id"]}}},
        }).encode()
        signature = self._sign(payload, "whsec_ok")
        resp = self.client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature, "Content-Type": "application/json"})
        self.assertEqual(200, resp.status_code)

        credits = self.client.get(f"/admin/credits/{buyer_id}", headers=self._admin_headers()).json()
        self.assertAlmostEqual(10.0, credits["balance_chf"])

    def test_webhook_rejects_bad_signature(self):
        _, finance_token = self._create_user("finance4", permissions=["billing.manage"])
        self.client.put("/billing/stripe/credentials", headers={"X-Jarvis-Session": finance_token},
                         json={"secret_key": "sk_test_ok", "webhook_secret": "whsec_ok"})
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode()
        resp = self.client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": "t=1,v1=deadbeef"})
        self.assertEqual(400, resp.status_code)

    def test_webhook_unassigns_plan_on_subscription_deleted(self):
        _, finance_token = self._create_user("finance5", permissions=["billing.manage"])
        self.client.put("/billing/stripe/credentials", headers={"X-Jarvis-Session": finance_token},
                         json={"secret_key": "sk_test_ok", "webhook_secret": "whsec_ok"})
        buyer_id, buyer_token = self._create_user("buyer5")
        plan = self._create_plan(stripe_price_id="price_123")
        self.client.put(f"/admin/users/{buyer_id}/plan", headers=self._admin_headers(), json={"plan_id": plan["id"]})

        payload = json.dumps({
            "type": "customer.subscription.deleted",
            "data": {"object": {"metadata": {"user_id": buyer_id}}},
        }).encode()
        signature = self._sign(payload, "whsec_ok")
        resp = self.client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature})
        self.assertEqual(200, resp.status_code)

        billing = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": buyer_token}).json()
        self.assertIsNone(billing.get("plan"))

    def test_webhook_unassigns_plan_on_subscription_past_due(self):
        # Regression coverage: a failed renewal charge does not delete the
        # subscription — Stripe marks it past_due/unpaid and retries for days
        # or weeks before ever sending .deleted. Without handling .updated,
        # the user kept their plan (and its monthly AI credit) the whole time.
        _, finance_token = self._create_user("finance6", permissions=["billing.manage"])
        self.client.put("/billing/stripe/credentials", headers={"X-Jarvis-Session": finance_token},
                         json={"secret_key": "sk_test_ok", "webhook_secret": "whsec_ok"})
        buyer_id, buyer_token = self._create_user("buyer6")
        plan = self._create_plan(stripe_price_id="price_123")
        self.client.put(f"/admin/users/{buyer_id}/plan", headers=self._admin_headers(), json={"plan_id": plan["id"]})

        payload = json.dumps({
            "type": "customer.subscription.updated",
            "data": {"object": {"status": "past_due", "metadata": {"user_id": buyer_id}}},
        }).encode()
        signature = self._sign(payload, "whsec_ok")
        resp = self.client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature})
        self.assertEqual(200, resp.status_code)

        billing = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": buyer_token}).json()
        self.assertIsNone(billing.get("plan"))

    def test_webhook_keeps_plan_when_subscription_still_active(self):
        _, finance_token = self._create_user("finance7", permissions=["billing.manage"])
        self.client.put("/billing/stripe/credentials", headers={"X-Jarvis-Session": finance_token},
                         json={"secret_key": "sk_test_ok", "webhook_secret": "whsec_ok"})
        buyer_id, buyer_token = self._create_user("buyer7")
        plan = self._create_plan(stripe_price_id="price_123")
        self.client.put(f"/admin/users/{buyer_id}/plan", headers=self._admin_headers(), json={"plan_id": plan["id"]})

        payload = json.dumps({
            "type": "customer.subscription.updated",
            "data": {"object": {"status": "active", "metadata": {"user_id": buyer_id}}},
        }).encode()
        signature = self._sign(payload, "whsec_ok")
        resp = self.client.post("/webhooks/stripe", content=payload, headers={"Stripe-Signature": signature})
        self.assertEqual(200, resp.status_code)

        billing = self.client.get("/auth/me/billing", headers={"X-Jarvis-Session": buyer_token}).json()
        self.assertIsNotNone(billing.get("plan"))
        self.assertEqual(plan["id"], billing["plan"]["id"])


if __name__ == "__main__":
    unittest.main()
