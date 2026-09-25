"""Autonomy control endpoints (web UI toggle for the agent switch)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field


class AutonomyUpdate(BaseModel):
    enabled: bool
    note: str = Field(default="", max_length=500)
    max_gpu_hours_per_day: float | None = Field(default=None, gt=0, le=24 * 31)
    allowed_windows: list[str] | None = Field(default=None, max_length=24)
    max_rounds_per_pod_session: int | None = Field(default=None, ge=0, le=1000)


def build_autonomy_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if hasattr(value, "get") else value

    def _admin_guard(
        x_jarvis_session: str | None,
        x_jarvis_user_id: str | None,
        x_jarvis_role: str | None,
        authorization: str | None,
    ) -> tuple[str, str]:
        try:
            require_admin = current("require_admin_access")
            return require_admin(x_jarvis_user_id, x_jarvis_role, authorization)
        except Exception:
            session = current("get_identity_session")(x_jarvis_session)
            if not session:
                raise HTTPException(401, "login required")
            role = current("normalize_role")(session.get("role"))
            if role != "admin":
                raise HTTPException(403, "admin role required")
            return str(session.get("user_id") or session.get("id") or ""), "admin"

    @router.get("/autonomy")
    def get_autonomy(
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        _admin_guard(x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization)
        return {"status": current("autonomy_store").status()}

    @router.put("/autonomy")
    def set_autonomy(
        body: AutonomyUpdate,
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        actor_id, actor_role = _admin_guard(
            x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization
        )
        status = current("autonomy_store").set_mode(
            body.enabled, actor=actor_id, note=body.note
        )
        try:
            status = current("autonomy_store").set_policy(
                actor=actor_id,
                max_gpu_hours_per_day=body.max_gpu_hours_per_day,
                allowed_windows=body.allowed_windows,
                max_rounds_per_pod_session=body.max_rounds_per_pod_session,
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        fn = current("audit_admin_event")
        fn(
            "autonomy.changed",
            actor_id,
            actor_role,
            {"enabled": body.enabled, "note": body.note},
        )
        return {"status": status}

    return router
