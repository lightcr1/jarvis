from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from jarvis.billing.stripe_client import (
    StripeAPIError,
    StripeWebhookError,
    _flatten_form,
    check_balance,
    create_checkout_session,
    verify_webhook_signature,
)


class FlattenFormTests(unittest.TestCase):
    def test_flattens_nested_dicts_and_lists_in_stripe_bracket_notation(self):
        data = {
            "mode": "subscription",
            "line_items": [{"price": "price_123", "quantity": 1}],
            "metadata": {"user_id": "u1", "plan_id": "plan-pro"},
        }
        pairs = dict(_flatten_form(data))
        self.assertEqual("subscription", pairs["mode"])
        self.assertEqual("price_123", pairs["line_items[0][price]"])
        self.assertEqual("1", pairs["line_items[0][quantity]"])
        self.assertEqual("u1", pairs["metadata[user_id]"])
        self.assertEqual("plan-pro", pairs["metadata[plan_id]"])


class _FakeStripeServer:
    def __init__(self, status: int, response_body: dict):
        self.requests: list[tuple[str, str, dict]] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def _handle(self):
                content_length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_length).decode("utf-8") if content_length else ""
                parsed = {k: v[0] for k, v in urllib.parse.parse_qs(raw).items()}
                outer.requests.append((self.command, self.path, parsed))
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response_body).encode("utf-8"))

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


class StripeApiCallTests(unittest.TestCase):
    def test_check_balance_true_on_200(self):
        with _FakeStripeServer(200, {"object": "balance"}):
            self.assertTrue(check_balance("sk_test_ok"))

    def test_check_balance_false_on_error_status(self):
        with _FakeStripeServer(401, {"error": {"message": "invalid key"}}):
            self.assertFalse(check_balance("sk_test_bad"))

    def test_create_checkout_session_sends_subscription_line_items(self):
        with _FakeStripeServer(200, {"id": "cs_test_1", "url": "https://checkout.stripe.com/pay/cs_test_1"}) as fake:
            result = create_checkout_session(
                "sk_test_ok",
                price_id="price_123",
                user_id="user-1",
                plan_id="plan-pro",
                success_url="https://jarvis.local/settings?billing=success",
                cancel_url="https://jarvis.local/settings?billing=cancel",
            )
            self.assertEqual("https://checkout.stripe.com/pay/cs_test_1", result["url"])
            method, path, body = fake.requests[0]
            self.assertEqual("POST", method)
            self.assertEqual("/v1/checkout/sessions", path)
            self.assertEqual("subscription", body["mode"])
            self.assertEqual("price_123", body["line_items[0][price]"])
            self.assertEqual("user-1", body["client_reference_id"])

    def test_api_error_raised_on_http_error(self):
        with _FakeStripeServer(500, {"error": {"message": "boom"}}):
            with self.assertRaises(StripeAPIError):
                create_checkout_session(
                    "sk_test_ok", price_id="p", user_id="u", plan_id="pl",
                    success_url="https://x", cancel_url="https://y",
                )


class WebhookSignatureTests(unittest.TestCase):
    def _sign(self, payload: bytes, secret: str, timestamp: int) -> str:
        signed_payload = f"{timestamp}.".encode("utf-8") + payload
        signature = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
        return f"t={timestamp},v1={signature}"

    def test_valid_signature_returns_parsed_event(self):
        secret = "whsec_test123"
        payload = json.dumps({"type": "checkout.session.completed", "data": {"object": {}}}).encode("utf-8")
        header = self._sign(payload, secret, int(time.time()))
        event = verify_webhook_signature(payload, header, secret)
        self.assertEqual("checkout.session.completed", event["type"])

    def test_wrong_secret_rejected(self):
        payload = json.dumps({"type": "checkout.session.completed"}).encode("utf-8")
        header = self._sign(payload, "whsec_correct", int(time.time()))
        with self.assertRaises(StripeWebhookError):
            verify_webhook_signature(payload, header, "whsec_wrong")

    def test_stale_timestamp_rejected(self):
        secret = "whsec_test123"
        payload = json.dumps({"type": "x"}).encode("utf-8")
        header = self._sign(payload, secret, int(time.time()) - 1000)
        with self.assertRaises(StripeWebhookError):
            verify_webhook_signature(payload, header, secret, tolerance=300)

    def test_malformed_header_rejected(self):
        with self.assertRaises(StripeWebhookError):
            verify_webhook_signature(b"{}", "not-a-valid-header", "whsec_test123")

    def test_tampered_payload_rejected(self):
        secret = "whsec_test123"
        original = json.dumps({"type": "checkout.session.completed"}).encode("utf-8")
        header = self._sign(original, secret, int(time.time()))
        tampered = json.dumps({"type": "customer.subscription.deleted"}).encode("utf-8")
        with self.assertRaises(StripeWebhookError):
            verify_webhook_signature(tampered, header, secret)


if __name__ == "__main__":
    unittest.main()
