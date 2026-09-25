"""Agent monitor + owner request endpoints (Jarvis admin web UI)."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .agent_monitor import (
    MonitorError,
    decide_owner_request,
    list_owner_requests,
    list_sessions,
    loop_version,
    session_action,
    session_status,
)


class RequestDecision(BaseModel):
    number: int
    decision: str = Field(pattern="^(approved|rejected)$")


def build_agent_monitor_router(deps: dict) -> APIRouter:
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
        """Accept either the short-lived admin bearer token (legacy) or the
        normal logged-in admin identity session. The web UI logs in with the
        identity session; requiring a separate token made the monitor
        unreachable for regular admin logins."""
        try:
            return current("require_admin_access")(
                x_jarvis_user_id, x_jarvis_role, authorization
            )
        except Exception:
            session = current("get_identity_session")(x_jarvis_session)
            if not session:
                raise HTTPException(401, "login required")
            role = current("normalize_role")(session.get("role"))
            if role != "admin":
                raise HTTPException(403, "admin role required")
            return str(session.get("user_id") or session.get("id") or ""), "admin"

    @router.get("/agent/sessions")
    def get_sessions(
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        _admin_guard(x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization)
        api_key = current("openhands_api_key")
        sessions = list_sessions(api_key)
        return {
            "sessions": [s for s in (session_status(s) for s in sessions) if s["id"]],
            "count": len(sessions),
        }

    @router.post("/agent/sessions/{conv_id}/{action}")
    def act_on_session(
        conv_id: str,
        action: str,
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        """Pause/Run/Interrupt einer OpenHands-Session (nur eigene Runden)."""
        actor_id, actor_role = _admin_guard(
            x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization
        )
        api_key = current("openhands_api_key")
        try:
            session_action(api_key, conv_id, action)
        except MonitorError as exc:
            raise HTTPException(502, str(exc)) from exc
        fn = current("audit_admin_event")
        fn("agent.session.action", actor_id, actor_role,
           {"conversation_id": conv_id, "action": action})
        return {"ok": True, "action": action}

    @router.get("/agent/loop-version")
    def get_loop_version(
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        """Versioned loop hash vs. installed/running loop hash (drift warning)."""
        _admin_guard(x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization)
        return loop_version()

    @router.get("/agent/requests")
    def get_requests(
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        _admin_guard(x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization)
        token = current("github_token")
        return list_owner_requests(token)

    @router.post("/agent/requests/{number}/decide")
    def decide(
        number: int,
        body: RequestDecision,
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        actor_id, actor_role = _admin_guard(
            x_jarvis_session, x_jarvis_user_id, x_jarvis_role, authorization
        )
        token = current("github_token")
        result = decide_owner_request(number, body.decision, token)
        fn = current("audit_admin_event")
        fn(
            "agent.request.decided",
            actor_id,
            actor_role,
            {"number": number, "decision": body.decision},
        )
        return {"ok": True, **result}

    return router
