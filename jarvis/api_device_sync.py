from __future__ import annotations

from fastapi import APIRouter, Header

from .router_dependencies import LiveRef


def build_device_sync_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    require_identity_session = deps["require_identity_session"]

    @router.post("/sync/briefing-seen")
    async def briefing_seen(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        updated = current("user_preferences_store").mark_briefing_seen(user_id)
        broadcaster = current("alert_broadcaster")
        await broadcaster.broadcast_to_user(user_id, {
            "type": "briefing_seen",
            "last_briefing_seen_ts": updated["last_briefing_seen_ts"],
        })
        return {"preferences": updated}

    return router
