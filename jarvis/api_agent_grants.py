"""Owner approval inbox; agent can request/check only, never grant rights."""
from __future__ import annotations

import hmac
from typing import Callable

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .router_dependencies import LiveRef
from .research_gateway import ResearchError, search_web
from .github_gateway import GithubGatewayError, canonical_repo, create_agent_branch, create_pull_request, public_repository_metadata, write_branch_file


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


class ResearchQuery(BaseModel):
    project_target: str = Field(max_length=180)
    query: str = Field(max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class ProjectRequest(BaseModel):
    kind: str = Field(max_length=32)
    target: str = Field(max_length=180)
    title: str = Field(max_length=200)
    operations: list[str] = Field(min_length=1, max_length=20)
    duration_seconds: int = Field(default=7 * 24 * 3600, ge=3600, le=30 * 24 * 3600)


class BranchCreate(BaseModel):
    branch: str = Field(max_length=200)
    base: str = Field(max_length=200)


class BranchFileWrite(BaseModel):
    path: str = Field(max_length=300)
    branch: str = Field(max_length=200)
    content: str = Field(max_length=262144)
    message: str = Field(max_length=200)


class PullRequestAction(BaseModel):
    repository: str = Field(max_length=201)
    title: str = Field(max_length=200)
    body: str = Field(max_length=10000)
    head: str = Field(max_length=200)
    base: str = Field(max_length=200)


class ActionDecision(BaseModel):
    approve: bool


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
        actor = str(session.get("user_id") or session.get("id") or "")
        configured_owner = current("owner_user_id")
        if not configured_owner:
            raise HTTPException(503, "JARVIS_OWNER_USER_ID is not configured")
        if not hmac.compare_digest(actor, configured_owner):
            raise HTTPException(403, "configured owner required")
        return actor

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

    @router.get("/agent/repositories/{repo_owner}/{repo_name}/metadata")
    def github_metadata(repo_owner: str, repo_name: str,
                        x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try:
            target = canonical_repo(repo_owner, repo_name)
        except GithubGatewayError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not current("agent_grant_store").authorize(
            kind="other_project", target=target, operation="read_metadata",
        ):
            raise HTTPException(403, "owner grant required for this repository")
        try:
            result = public_repository_metadata(repo_owner, repo_name)
        except GithubGatewayError as exc:
            raise HTTPException(502, str(exc)) from exc
        audit("agent.repository.metadata_read", "agent", {"repository": target})
        return {"metadata": result}

    @router.post("/agent/research/search")
    def research(body: ResearchQuery, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        store = current("agent_grant_store")
        if not store.authorize(kind="business_research", target=body.project_target, operation="web_search"):
            raise HTTPException(403, "approved research project required")
        if not store.consume_research_quota(body.project_target):
            raise HTTPException(429, "daily research quota reached")
        try: results = search_web(body.query, current("web_search_token"), limit=body.limit)
        except ResearchError as exc: raise HTTPException(502, str(exc)) from exc
        audit("agent.research.searched", "agent", {"project_target": body.project_target, "query_length": len(body.query), "result_count": len(results)})
        return {"results": results, "untrusted": True}

    @router.post("/agent/projects", status_code=201)
    def request_project(body: ProjectRequest, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try:
            item = current("agent_grant_store").request_project(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.project.requested", "agent", {"project_id": item["id"]})
        return {"project": item}

    @router.get("/agent/projects/{project_id}")
    def project_status(project_id: str, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        item = current("agent_grant_store").get_project(project_id)
        if item is None: raise HTTPException(404, "project not found")
        return {"project": item}

    @router.get("/admin/agent-projects")
    def projects(x_jarvis_session: str | None = Header(default=None)):
        owner(x_jarvis_session); return {"projects": current("agent_grant_store").list_projects()}

    @router.post("/admin/agent-projects/{project_id}/decide")
    def decide_project(project_id: str, body: GrantDecision, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        item = current("agent_grant_store").decide_project(project_id, actor=actor, approve=body.approve)
        if item is None: raise HTTPException(409, "project missing, expired, or already decided")
        audit("agent.project.decided", actor, {"project_id": project_id, "approved": body.approve})
        return {"project": item}

    @router.post("/admin/agent-projects/{project_id}/revoke")
    def revoke_project(project_id: str, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        item = current("agent_grant_store").revoke_project(project_id, actor=actor)
        if item is None: raise HTTPException(409, "project missing or not approved")
        audit("agent.project.revoked", actor, {"project_id": project_id})
        return {"project": item}

    @router.post("/agent/repositories/{repo_owner}/{repo_name}/branches")
    def create_branch(repo_owner: str, repo_name: str, body: BranchCreate,
                      x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try: target = canonical_repo(repo_owner, repo_name)
        except GithubGatewayError as exc: raise HTTPException(422, str(exc)) from exc
        if not current("agent_grant_store").authorize(kind="other_project", target=target, operation="create_branch"):
            raise HTTPException(403, "approved project operation required")
        try: result = create_agent_branch(repo_owner, repo_name, token=current("github_write_token"), **body.model_dump())
        except GithubGatewayError as exc: raise HTTPException(502, str(exc)) from exc
        audit("agent.repository.branch_created", "agent", {"repository": target, "branch": body.branch, "base": body.base})
        return {"result": result}

    @router.put("/agent/repositories/{repo_owner}/{repo_name}/files")
    def write_file(repo_owner: str, repo_name: str, body: BranchFileWrite,
                   x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try: target = canonical_repo(repo_owner, repo_name)
        except GithubGatewayError as exc: raise HTTPException(422, str(exc)) from exc
        if not current("agent_grant_store").authorize(kind="other_project", target=target, operation="write_branch_file"):
            raise HTTPException(403, "approved project operation required")
        try: result = write_branch_file(repo_owner, repo_name, token=current("github_write_token"), **body.model_dump())
        except GithubGatewayError as exc: raise HTTPException(502, str(exc)) from exc
        audit("agent.repository.file_written", "agent", {"repository": target, "path": body.path, "branch": body.branch, "commit": result["commit"]})
        return {"result": result}

    @router.post("/agent/actions/github-pull-request", status_code=201)
    def request_pull_request(body: PullRequestAction, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        try:
            owner_name, repo_name = body.repository.split("/", 1)
            target = canonical_repo(owner_name, repo_name)
            item = current("agent_grant_store").request_one_time_action(
                kind="github_create_pr", target=target,
                payload=body.model_dump(exclude={"repository"}),
            )
        except (ValueError, GithubGatewayError) as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.action.requested", "agent", {"action_id": item["id"], "digest": item["digest"]})
        return {"action": item}

    @router.post("/admin/agent-actions/{action_id}/decide")
    def decide_action(action_id: str, body: ActionDecision, x_jarvis_session: str | None = Header(default=None)):
        actor = owner(x_jarvis_session)
        item = current("agent_grant_store").decide_one_time_action(action_id, actor=actor, approve=body.approve)
        if item is None:
            raise HTTPException(409, "action missing, expired, or already decided")
        audit("agent.action.decided", actor, {"action_id": action_id, "approved": body.approve, "digest": item["digest"]})
        return {"action": item}

    @router.post("/agent/actions/{action_id}/execute")
    def execute_action(action_id: str, x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        item = current("agent_grant_store").consume_one_time_action(action_id)
        if item is None:
            raise HTTPException(403, "approved, unused action required")
        payload = __import__("json").loads(item["payload"])
        owner_name, repo_name = item["target"].split("/", 1)
        try:
            result = create_pull_request(owner_name, repo_name, payload, current("github_write_token"))
        except GithubGatewayError as exc:
            audit("agent.action.failed", "agent", {"action_id": action_id, "digest": item["digest"]})
            raise HTTPException(502, str(exc)) from exc
        audit("agent.action.executed", "agent", {"action_id": action_id, "digest": item["digest"], "result": result})
        return {"result": result}

    @router.get("/admin/agent-actions")
    def list_actions(x_jarvis_session: str | None = Header(default=None)):
        owner(x_jarvis_session)
        return {"actions": current("agent_grant_store").list_one_time_actions()}

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
