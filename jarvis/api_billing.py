from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from .billing.stripe_client import (
    STRIPE_CREDENTIAL_INTEGRATION,
    STRIPE_CREDENTIAL_OWNER,
    StripeAPIError,
    StripeWebhookError,
    check_balance,
    create_checkout_session,
    verify_webhook_signature,
)
from .plan_service import assign_plan
from .router_dependencies import LiveRef


def _token_hint(secret: str) -> str:
    if len(secret) <= 10:
        return "***"
    return f"{secret[:7]}…{secret[-4:]}"


def build_billing_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def require_billing_access(x_jarvis_session: str | None) -> dict:
        session = current("require_identity_session")(x_jarvis_session)
        user = session["user"]
        effective = current("resolve_effective_permissions")(
            user["role"], user["id"], current("membership_store"), current("permission_store"),
        )
        if "billing.manage" not in effective:
            raise HTTPException(403, "missing permission: billing.manage")
        return session

    @router.get("/billing/stripe/status")
    def stripe_status(x_jarvis_session: str | None = Header(default=None)):
        require_billing_access(x_jarvis_session)
        creds = current("integration_credential_store").get_credentials(STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION)
        status = current("integration_credential_store").status(STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION)
        secret_key = (creds or {}).get("secret_key", "")
        return {
            "configured": bool(secret_key),
            "secret_key_hint": _token_hint(secret_key) if secret_key else "",
            "has_webhook_secret": bool((creds or {}).get("webhook_secret")),
            "updated_at": status["updated_at"],
        }

    @router.put("/billing/stripe/credentials")
    def set_stripe_credentials(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = require_billing_access(x_jarvis_session)
        secret_key = str((payload or {}).get("secret_key") or "").strip()
        webhook_secret = str((payload or {}).get("webhook_secret") or "").strip()
        if not secret_key or not webhook_secret:
            raise HTTPException(400, "secret_key and webhook_secret are both required")
        current("integration_credential_store").set_credentials(
            STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION,
            {"secret_key": secret_key, "webhook_secret": webhook_secret},
        )
        current("audit_log").write("billing_stripe_credentials_set", {"actor_user_id": session["user"]["id"]})
        return {"configured": True}

    @router.delete("/billing/stripe/credentials")
    def clear_stripe_credentials(x_jarvis_session: str | None = Header(default=None)):
        session = require_billing_access(x_jarvis_session)
        current("integration_credential_store").delete_credentials(STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION)
        current("audit_log").write("billing_stripe_credentials_cleared", {"actor_user_id": session["user"]["id"]})
        return {"configured": False}

    @router.post("/billing/stripe/test")
    def test_stripe_connection(x_jarvis_session: str | None = Header(default=None)):
        require_billing_access(x_jarvis_session)
        creds = current("integration_credential_store").get_credentials(STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION)
        if not creds or not creds.get("secret_key"):
            return {"ok": False}
        return {"ok": check_balance(creds["secret_key"])}

    @router.post("/billing/checkout-session")
    def create_checkout(payload: dict[str, object], x_jarvis_session: str | None = Header(default=None)):
        session = current("require_identity_session")(x_jarvis_session)
        user_id = session["user"]["id"]
        plan_id = str((payload or {}).get("plan_id") or "")
        plan = current("plan_store").get_plan(plan_id)
        if not plan:
            raise HTTPException(404, "plan not found")
        if not plan.get("stripe_price_id"):
            raise HTTPException(400, "this plan has no Stripe price configured")
        creds = current("integration_credential_store").get_credentials(STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION)
        if not creds or not creds.get("secret_key"):
            raise HTTPException(503, "Stripe is not configured")
        base_url = str((payload or {}).get("return_url") or "").strip()
        try:
            result = create_checkout_session(
                creds["secret_key"],
                price_id=plan["stripe_price_id"],
                user_id=user_id,
                plan_id=plan_id,
                success_url=f"{base_url}?billing=success" if base_url else "https://jarvis.local/?screen=settings&billing=success",
                cancel_url=f"{base_url}?billing=cancel" if base_url else "https://jarvis.local/?screen=settings&billing=cancel",
            )
        except StripeAPIError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {"checkout_url": result.get("url")}

    @router.post("/webhooks/stripe")
    async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="Stripe-Signature")):
        creds = current("integration_credential_store").get_credentials(STRIPE_CREDENTIAL_OWNER, STRIPE_CREDENTIAL_INTEGRATION)
        if not creds or not creds.get("webhook_secret"):
            raise HTTPException(503, "Stripe is not configured")
        raw_body = await request.body()
        try:
            event = verify_webhook_signature(raw_body, stripe_signature or "", creds["webhook_secret"])
        except StripeWebhookError as exc:
            raise HTTPException(400, str(exc)) from exc

        event_type = event.get("type")
        obj = ((event.get("data") or {}).get("object")) or {}
        metadata = obj.get("metadata") or {}
        user_id = metadata.get("user_id")
        plan_id = metadata.get("plan_id")

        if event_type == "checkout.session.completed" and obj.get("mode") == "subscription" and user_id and plan_id:
            assign_plan(user_id, plan_id, plan_store=current("plan_store"), user_limits_store=current("user_limits_store"), credit_store=current("credit_store"))
            current("audit_log").write("billing_subscription_started", {"user_id": user_id, "plan_id": plan_id})
        elif event_type == "customer.subscription.deleted" and user_id:
            assign_plan(user_id, "", plan_store=current("plan_store"), user_limits_store=current("user_limits_store"), credit_store=current("credit_store"))
            current("audit_log").write("billing_subscription_cancelled", {"user_id": user_id})

        return {"received": True}

    return router
