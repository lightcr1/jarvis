from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .api_models import PushSubscriptionIn
from .router_dependencies import LiveRef


def build_notifications_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    require_identity_session = deps["require_identity_session"]

    @router.get("/notifications/vapid-public-key")
    def vapid_public_key():
        keys = current("vapid_keys")
        return {"public_key": keys.get("public_key", "")}

    @router.post("/notifications/subscribe", status_code=201)
    def subscribe(payload: PushSubscriptionIn, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user = session["user"]
        store = current("push_subscription_store")
        entry = store.add(user["id"], payload.model_dump())
        current("audit_admin_event")(
            "notifications.subscribed",
            user["id"],
            user.get("role", ""),
            {"endpoint_fingerprint": entry["endpoint"][-12:]},
        )
        return {"ok": True}

    @router.delete("/notifications/subscribe")
    def unsubscribe(endpoint: str, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user = session["user"]
        store = current("push_subscription_store")
        removed = store.remove(user["id"], endpoint)
        if not removed:
            raise HTTPException(404, "Subscription not found")
        current("audit_admin_event")(
            "notifications.unsubscribed",
            user["id"],
            user.get("role", ""),
            {"endpoint_fingerprint": endpoint[-12:]},
        )
        return {"ok": True}

    return router
