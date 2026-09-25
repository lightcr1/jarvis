"""Admin backlog CRUD + request-only agent task/report endpoints."""
from __future__ import annotations

import hmac
from typing import Callable

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .rate_limiter import _rate as _rate_limiter


class TaskCreate(BaseModel):
    title: str = Field(max_length=140)
    description: str = Field(default="", max_length=4000)
    area: str = Field(default="general", max_length=40)
    size: str = Field(default="medium", pattern="^(small|medium)$")
    priority: int = Field(default=100, ge=0, le=10000)


class TaskProposal(BaseModel):
    title: str = Field(max_length=140)
    description: str = Field(default="", max_length=4000)
    area: str = Field(default="general", max_length=40)
    size: str = Field(default="medium", pattern="^(small|medium)$")


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=140)
    description: str | None = Field(default=None, max_length=4000)
    area: str | None = Field(default=None, max_length=40)
    size: str | None = Field(default=None, pattern="^(small|medium)$")
    priority: int | None = Field(default=None, ge=0, le=10000)
    status: str | None = Field(
        default=None,
        pattern="^(proposed|open|in_progress|submitted|done|blocked|rejected)$",
    )


class TaskDecision(BaseModel):
    approve: bool


class TaskReview(BaseModel):
    decision: str = Field(pattern="^(merged|rejected)$")


class TaskClaim(BaseModel):
    round_id: str = Field(max_length=64)


class RoundReport(BaseModel):
    round_id: str = Field(default="", max_length=64)
    outcome: str = Field(pattern="^(done|partial|blocked|no_change|submitted|unknown)$")
    summary: str = Field(max_length=800)
    branch: str = Field(default="", max_length=200)
    files_changed: list[str] = Field(default_factory=list, max_length=100)
    tests: list[str] = Field(default_factory=list, max_length=50)
    next_step: str = Field(default="", max_length=800)
    owner_question: str = Field(default="", max_length=800)


def build_autonomy_tasks_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if hasattr(value, "get") else value

    def _admin_guard(
        x_jarvis_session: str | None,
        x_jarvis_user_id: str | None,
        x_jarvis_role: str | None,
        authorization: str | None,
    ) -> str:
        guard = deps.get("require_admin_access")
        if guard is not None:
            try:
                actor_id, _ = guard(x_jarvis_user_id, x_jarvis_role, authorization)
                return str(actor_id)
            except Exception:
                pass
        session = current("get_identity_session")(x_jarvis_session)
        if not session:
            raise HTTPException(401, "login required")
        if current("normalize_role")(session.get("role")) != "admin":
            raise HTTPException(403, "admin role required")
        return str(session.get("user_id") or session.get("id") or "")

    def agent(token: str | None) -> None:
        expected = current("agent_request_token")
        if not expected or not token or not hmac.compare_digest(token, expected):
            raise HTTPException(401, "agent request token required")

    def cap(token: str, key: str, limit: int = 30, window: float = 60) -> None:
        if not _rate_limiter.allow(f"agent-{key}:{token}", limit, window):
            raise HTTPException(429, "agent rate limit reached — slow down")

    def audit(event: str, actor: str, data: dict) -> None:
        fn: Callable = current("audit_admin_event")
        fn(event, actor, "admin" if actor != "agent" else "service_system", data)

    def store():
        return current("autonomy_task_store")

    # ---- Admin ---------------------------------------------------------

    @router.get("/admin/autonomy/tasks")
    def list_tasks(status: str | None = None, area: str | None = None,
                   x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return {"tasks": store().list_tasks(status=status, area=area)}

    @router.post("/admin/autonomy/tasks", status_code=201)
    def create_task(body: TaskCreate, x_jarvis_session: str | None = Header(default=None)):
        actor = _admin_guard(x_jarvis_session, None, None, None)
        try:
            task = store().create_task(source="owner", status="open", **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.task.created", actor, {"task_id": task["id"]})
        return {"task": task}

    @router.patch("/admin/autonomy/tasks/{task_id}")
    def update_task(task_id: str, body: TaskUpdate,
                    x_jarvis_session: str | None = Header(default=None)):
        actor = _admin_guard(x_jarvis_session, None, None, None)
        try:
            task = store().update_task(task_id, **body.model_dump(exclude_unset=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if task is None:
            raise HTTPException(404, "task not found")
        audit("agent.task.updated", actor, {"task_id": task_id})
        return {"task": task}

    @router.post("/admin/autonomy/tasks/{task_id}/decide")
    def decide_task(task_id: str, body: TaskDecision,
                    x_jarvis_session: str | None = Header(default=None)):
        actor = _admin_guard(x_jarvis_session, None, None, None)
        task = store().decide_task(task_id, actor=actor, approve=body.approve)
        if task is None:
            raise HTTPException(409, "task missing or already decided")
        audit("agent.task.decided", actor, {"task_id": task_id, "approved": body.approve})
        return {"task": task}

    @router.get("/admin/autonomy/reports")
    def list_reports(task_id: str | None = None,
                     x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return {"reports": store().list_reports(task_id=task_id)}

    @router.get("/admin/autonomy/stats")
    def list_stats(x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return {"areas": store().area_success_rates()}

    @router.get("/admin/autonomy/daily-report")
    def daily_report(x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return store().daily_summary()

    @router.post("/admin/autonomy/tasks/{task_id}/review")
    def review_task(task_id: str, body: TaskReview,
                    x_jarvis_session: str | None = Header(default=None)):
        actor = _admin_guard(x_jarvis_session, None, None, None)
        try:
            task = store().review_task(task_id, actor=actor, decision=body.decision)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if task is None:
            raise HTTPException(404, "task not found")
        audit("agent.task.reviewed", actor, {"task_id": task_id, "decision": body.decision})
        return {"task": task}

    # ---- Agent ---------------------------------------------------------

    @router.get("/agent/tasks/next")
    def next_task(focus: str | None = None, exclude: str | None = None,
                  exclude_area: str | None = None,
                  x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        cap(x_jarvis_agent_request_token, "task-next", 60)
        excluded = {item for item in (exclude or "").split(",") if item}
        blocked_areas = {item for item in (exclude_area or "").split(",") if item}
        # focus steuert den Rundentyp (engineering/ideas), nicht den Aufgabenbereich.
        task = store().next_open_task(area=None, exclude_ids=excluded,
                                      exclude_areas=blocked_areas)
        last_report = store().last_report(task["id"]) if task else None
        submitted = store().list_tasks(status="submitted", limit=20)
        in_progress = store().list_tasks(status="in_progress", limit=20)
        open_work = {
            "submitted": len(submitted),
            "in_progress": len(in_progress),
            "submitted_titles": [t["title"][:60] for t in submitted[:5]],
            "in_progress_titles": [t["title"][:60] for t in in_progress[:5]],
        }
        return {"task": task, "last_report": last_report, "open_work": open_work}

    @router.post("/agent/tasks", status_code=201)
    def propose_task(body: TaskProposal,
                     x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        cap(x_jarvis_agent_request_token, "task-propose", 10)
        try:
            task = store().propose_task(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.task.proposed", "agent", {"task_id": task["id"]})
        return {"task": task}

    @router.get("/agent/tasks/{task_id}")
    def get_agent_task(task_id: str,
                       x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        cap(x_jarvis_agent_request_token, "task-get", 60)
        task = store().get_task(task_id)
        if task is None:
            raise HTTPException(404, "task not found")
        return {"task": task, "last_report": store().last_report(task_id)}

    @router.post("/agent/tasks/{task_id}/claim")
    def claim_task(task_id: str, body: TaskClaim,
                   x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        cap(x_jarvis_agent_request_token, "task-claim", 30)
        task = store().claim_task(task_id, round_id=body.round_id)
        if task is None:
            raise HTTPException(409, "task not open or already claimed")
        audit("agent.task.claimed", "agent", {"task_id": task_id, "round_id": body.round_id})
        return {"task": task}

    @router.post("/agent/tasks/{task_id}/report", status_code=201)
    def report_round(task_id: str, body: RoundReport,
                     x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        cap(x_jarvis_agent_request_token, "task-report", 30)
        if store().get_task(task_id) is None:
            raise HTTPException(404, "task not found")
        try:
            report = store().record_report(task_id=task_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        audit("agent.task.reported", "agent", {"task_id": task_id, "outcome": body.outcome})
        return {"report": report, "task": store().get_task(task_id)}

    return router
