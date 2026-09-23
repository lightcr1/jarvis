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


class IdeaProposal(BaseModel):
    kind: str = Field(max_length=32)
    title: str = Field(max_length=140)
    summary: str = Field(max_length=2000)
    benefit: str = Field(max_length=2000)
    risks: str = Field(max_length=2000)
    next_step: str = Field(max_length=2000)


class OwnerIdea(BaseModel):
    kind: str = Field(default="business", max_length=32)
    title: str = Field(max_length=140)
    summary: str = Field(max_length=2000)


class IdeaReview(BaseModel):
    status: str = Field(pattern="^(shortlisted|dismissed)$")


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

    @router.post("/agent/ideas", status_code=201)
    def propose_idea(body: IdeaProposal, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try:
            item = current("agent_grant_store").propose_idea(source="agent", **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.idea.proposed", "agent", {"idea_id": item["id"]})
        return {"idea": item}

    @router.get("/agent/ideas")
    def agent_ideas(x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        return {"ideas": current("agent_grant_store").list_ideas()}

    @router.get("/agent/ideas/{idea_id}")
    def idea_status(idea_id: str, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        item = current("agent_grant_store").get_idea(idea_id)
        if item is None:
            raise HTTPException(404, "idea not found")
        return {"idea": item}

    @router.get("/admin/ideas")
    def list_ideas(x_jarvis_session: str | None = Header(default=None)):
        owner(x_jarvis_session)
        return {"ideas": current("agent_grant_store").list_ideas()}

    @router.post("/admin/ideas", status_code=201)
    def owner_idea(body: OwnerIdea, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        try:
            item = current("agent_grant_store").propose_idea(
                source="owner", **body.model_dump(), benefit="To be researched",
                risks="To be assessed", next_step="Research and propose a safe plan",
            )
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.idea.owner_submitted", actor, {"idea_id": item["id"]})
        return {"idea": item}

    @router.post("/admin/ideas/{idea_id}/review")
    def review_idea(idea_id: str, body: IdeaReview, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        item = current("agent_grant_store").review_idea(idea_id, actor=actor, status=body.status)
        if item is None:
            raise HTTPException(409, "idea missing or already reviewed")
        audit("agent.idea.reviewed", actor, {"idea_id": idea_id, "status": body.status})
        return {"idea": item}

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
