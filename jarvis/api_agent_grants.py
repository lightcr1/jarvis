"""Owner approval inbox; agent can request/check only, never grant rights."""
from __future__ import annotations

import hmac
from typing import Callable

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .router_dependencies import LiveRef


class GrantRequest(BaseModel):
    kind: str = Field(max_length=32)
    target: str = Field(max_length=180)
    operation: str = Field(max_length=180)
    reason: str = Field(max_length=1000)
    duration_seconds: int = Field(default=3600, ge=60, le=30 * 24 * 3600)


class GrantDecision(BaseModel):
    approve: bool


def build_agent_grants_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def owner(session_token: str | None) -> str:
        session = current("get_identity_session")(session_token)
        if not session:
            raise HTTPException(401, "login required")
        if current("normalize_role")(session.get("role")) != "admin":
            raise HTTPException(403, "owner role required")
        return str(session.get("user_id") or session.get("id") or "")

    def agent(token: str | None):
        expected = current("agent_request_token")
        if not expected or not token or not hmac.compare_digest(token, expected):
            raise HTTPException(401, "agent request token required")

    def audit(event: str, actor: str, data: dict):
        fn: Callable = current("audit_admin_event")
        fn(event, actor, "admin" if actor != "agent" else "service_system", data)

    @router.post("/agent/grants/requests", status_code=201)
    def request_grant(body: GrantRequest, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try:
            item = current("agent_grant_store").request(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.grant.requested", "agent", {"request_id": item["id"]})
        return {"request": item}

    @router.get("/agent/grants/requests/{request_id}")
    def request_status(request_id: str, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        item = current("agent_grant_store").get(request_id)
        if item is None:
            raise HTTPException(404, "request not found")
        return {"request": item}

    @router.get("/admin/agent-grants")
    def list_grants(x_jarvis_session: str | None = Header(default=None)):
        owner(x_jarvis_session)
        return {"requests": current("agent_grant_store").list_requests()}

    @router.post("/admin/agent-grants/{request_id}/decide")
    def decide(request_id: str, body: GrantDecision, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        item = current("agent_grant_store").decide(request_id, actor=actor, approve=body.approve)
        if item is None:
            raise HTTPException(409, "request missing, expired, or already decided")
        audit("agent.grant.decided", actor, {"request_id": request_id, "approved": body.approve})
        return {"request": item}

    @router.post("/admin/agent-grants/{request_id}/revoke")
    def revoke(request_id: str, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        item = current("agent_grant_store").revoke(request_id, actor=actor)
        if item is None:
            raise HTTPException(409, "request missing or not approved")
        audit("agent.grant.revoked", actor, {"request_id": request_id})
        return {"request": item}

    return router
