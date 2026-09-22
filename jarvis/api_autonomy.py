"""Autonomy control endpoints (web UI toggle for the agent switch)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field


class AutonomyUpdate(BaseModel):
    enabled: bool
    note: str = Field(default="", max_length=500)


def build_autonomy_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if hasattr(value, "get") else value

    @router.get("/autonomy")
    def get_autonomy(
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        require_admin = current("require_admin_access")
        actor_id, actor_role = require_admin(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"status": current("autonomy_store").status()}

    @router.put("/autonomy")
    def set_autonomy(
        body: AutonomyUpdate,
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        require_admin = current("require_admin_access")
        actor_id, actor_role = require_admin(x_jarvis_user_id, x_jarvis_role, authorization)
        status = current("autonomy_store").set_mode(
            body.enabled, actor=actor_id, note=body.note
        )
        fn = current("audit_admin_event")
        fn(
            "autonomy.changed",
            actor_id,
            actor_role,
            {"enabled": body.enabled, "note": body.note},
        )
        return {"status": status}

    return router
