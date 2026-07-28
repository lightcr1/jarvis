from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

from .router_dependencies import LiveRef


def build_weather_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    require_identity_session = deps["require_identity_session"]
    fetch_weather = deps["fetch_weather"]

    @router.get("/weather")
    def get_weather(city: str | None = None, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id: str = session["user"]["id"]
        resolved_city = (city or "").strip()
        if not resolved_city:
            prefs = current("user_preferences_store").get(user_id)
            resolved_city = (prefs.get("location") or "").strip()
        if not resolved_city:
            raise HTTPException(400, "No city provided and no saved location on file.")
        result = fetch_weather(resolved_city)
        if not result:
            raise HTTPException(502, "Weather lookup failed.")
        return {"weather": result}

    return router
