from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

STRIPE_CREDENTIAL_OWNER = "system"
STRIPE_CREDENTIAL_INTEGRATION = "stripe"

_DEFAULT_API_BASE = "https://api.stripe.com"


class StripeAPIError(Exception):
    pass


class StripeWebhookError(ValueError):
    pass


def _api_base() -> str:
    return (os.getenv("JARVIS_STRIPE_API_BASE") or _DEFAULT_API_BASE).rstrip("/")


def _flatten_form(data: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Flattens a nested dict/list into Stripe's bracket-notation form fields,
    e.g. {"line_items": [{"price": "x"}]} -> [("line_items[0][price]", "x")]."""
    pairs: list[tuple[str, str]] = []
    for key, value in data.items():
        field = f"{prefix}[{key}]" if prefix else str(key)
        if isinstance(value, dict):
            pairs.extend(_flatten_form(value, field))
        elif isinstance(value, list):
            for index, item in enumerate(value):
                indexed = f"{field}[{index}]"
                if isinstance(item, dict):
                    pairs.extend(_flatten_form(item, indexed))
                else:
                    pairs.append((indexed, str(item)))
        elif value is not None:
            pairs.append((field, str(value)))
    return pairs


def _request(secret_key: str, method: str, path: str, *, form: dict | None = None) -> dict:
    url = f"{_api_base()}{path}"
    body = None
    headers = {"Authorization": f"Bearer {secret_key}"}
    if form is not None:
        body = urllib.parse.urlencode(_flatten_form(form)).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise StripeAPIError(f"Stripe API error ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise StripeAPIError(f"Stripe API unreachable: {exc}") from exc


def check_balance(secret_key: str) -> bool:
    try:
        _request(secret_key, "GET", "/v1/balance")
        return True
    except StripeAPIError:
        return False


def create_checkout_session(
    secret_key: str,
    *,
    price_id: str,
    user_id: str,
    plan_id: str,
    success_url: str,
    cancel_url: str,
) -> dict:
    metadata = {"user_id": user_id, "plan_id": plan_id}
    form = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": user_id,
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
    }
    return _request(secret_key, "POST", "/v1/checkout/sessions", form=form)


def _parse_signature_header(header: str) -> tuple[int | None, list[str]]:
    timestamp: int | None = None
    signatures: list[str] = []
    for part in header.split(","):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip()
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                timestamp = None
        elif key == "v1":
            signatures.append(value.strip())
    return timestamp, signatures


def verify_webhook_signature(payload: bytes, sig_header: str, secret: str, *, tolerance: int = 300) -> dict:
    """Verifies a Stripe webhook per Stripe's documented manual-verification algorithm
    (https://stripe.com/docs/webhooks#verify-manually) and returns the parsed event."""
    timestamp, signatures = _parse_signature_header(sig_header or "")
    if timestamp is None or not signatures:
        raise StripeWebhookError("malformed Stripe-Signature header")
    if abs(time.time() - timestamp) > tolerance:
        raise StripeWebhookError("webhook timestamp outside tolerance")
    signed_payload = f"{timestamp}.".encode("utf-8") + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in signatures):
        raise StripeWebhookError("signature mismatch")
    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise StripeWebhookError("invalid JSON payload") from exc
