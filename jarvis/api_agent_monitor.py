"""Agent monitor + owner request endpoints (Jarvis admin web UI)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .agent_monitor import decide_owner_request, list_owner_requests, list_sessions


class RequestDecision(BaseModel):
    number: int
    decision: str = Field(pattern="^(approved|rejected)$")


def build_agent_monitor_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if hasattr(value, "get") else value

    @router.get("/agent/sessions")
    def get_sessions(
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        require_admin = current("require_admin_access")
        require_admin(x_jarvis_user_id, x_jarvis_role, authorization)
        api_key = current("openhands_api_key")
        sessions = list_sessions(api_key)
        return {
            "sessions": [s for s in (session_status(s) for s in sessions) if s["id"]],
            "count": len(sessions),
        }

    @router.get("/agent/requests")
    def get_requests(
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        require_admin = current("require_admin_access")
        require_admin(x_jarvis_user_id, x_jarvis_role, authorization)
        token = current("github_token")
        return list_owner_requests(token)

    @router.post("/agent/requests/{number}/decide")
    def decide(
        number: int,
        body: RequestDecision,
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ):
        require_admin = current("require_admin_access")
        actor_id, actor_role = require_admin(x_jarvis_user_id, x_jarvis_role, authorization)
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
