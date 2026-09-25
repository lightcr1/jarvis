"""Admin backlog CRUD + request-only agent task/report endpoints."""
from __future__ import annotations

import hmac
import json
import time
from pathlib import Path
from typing import Callable

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .rate_limiter import _rate as _rate_limiter
from .github_gateway import GithubGatewayError, list_labeled_issues


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


class RoundMetrics(BaseModel):
    task_id: str | None = None
    started_at: int | None = None
    ended_at: int | None = None
    gpu_seconds: float = Field(default=0.0, ge=0, le=7 * 24 * 3600)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    cost_estimate: float = Field(default=0.0, ge=0)
    status: str = Field(default="unknown", max_length=40)


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

    async def notify_owner_question(task_id: str, question: str) -> None:
        """7.3: Besitzer per bestehendem Notification-System benachrichtigen."""
        broadcaster = deps.get("alert_broadcaster")
        owner = str(deps.get("owner_user_id") or "")
        if broadcaster is None or not owner:
            return
        payload = {
            "type": "agent_question",
            "severity": "warning",
            "user_id": owner,
            "message": f"Der Agent braucht eine Entscheidung ({task_id[:8]}): {question[:200]}",
            "timestamp": int(time.time()),
        }
        try:
            await broadcaster.notify_user(owner, payload)
        except Exception:  # noqa: BLE001 - notification must never break the report
            pass

    def post_to_chat(task: dict | None, text: str) -> None:
        """7.2 Rueckkanal: Rundenbericht/Rueckfrage in den Ursprungs-Chat schreiben."""
        history = deps.get("chat_history")
        session_id = str((task or {}).get("origin_session_id") or "")
        if history is None or not session_id or not text:
            return
        try:
            history.append_message(session_id, "jarvis", text,
                                   owner_user_id=str(deps.get("owner_user_id") or "") or None)
        except Exception:  # noqa: BLE001 - Chat-Zustellung darf den Report nicht brechen
            pass

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

    @router.get("/admin/autonomy/metrics/weekly")
    def weekly_metrics_endpoint(gpu_seconds: float = 0.0,
                                x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        from .agent_metrics import weekly_metrics
        return weekly_metrics(store(), deps.get("agent_grant_store"), gpu_seconds=gpu_seconds)

    @router.get("/admin/autonomy/stats")
    def list_stats(x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return {"areas": store().area_success_rates()}

    @router.get("/admin/autonomy/daily-report")
    def daily_report(x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return store().daily_summary()

    @router.post("/admin/autonomy/loop-rollout")
    def request_loop_rollout(x_jarvis_session: str | None = Header(default=None)):
        """7.5: nur eine Anforderung schreiben; der Host-Timer installiert."""
        actor = _admin_guard(x_jarvis_session, None, None, None)
        marker = str(deps.get("loop_rollout_marker") or "")
        if not marker:
            raise HTTPException(503, "JARVIS_LOOP_ROLLOUT_MARKER not configured")
        path = Path(marker)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"requested_by": actor, "ts": int(time.time())}) + "\n",
                            encoding="utf-8")
        except OSError as exc:
            raise HTTPException(502, f"marker not writable: {exc}") from exc
        audit("agent.loop.rollout_requested", actor, {"marker": marker})
        return {"requested": True, "marker": marker}

    @router.get("/admin/autonomy/round-metrics")
    def round_metrics(since: int | None = None,
                      x_jarvis_session: str | None = Header(default=None)):
        _admin_guard(x_jarvis_session, None, None, None)
        return {"aggregate": store().aggregate_metrics(since=since),
                "metrics": store().list_metrics()}

    @router.post("/agent/rounds/{round_id}/metrics", status_code=201)
    def record_round_metrics(round_id: str, body: RoundMetrics,
                             x_jarvis_agent_request_token: str | None = Header(default=None)):
        agent(x_jarvis_agent_request_token)
        cap(x_jarvis_agent_request_token, "round-metrics", 60)
        try:
            metrics = store().record_metrics(round_id=round_id, **body.model_dump())
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"metrics": metrics}

    @router.post("/admin/autonomy/import-issues")
    def import_issues(label: str = "agent",
                      x_jarvis_session: str | None = Header(default=None)):
        """3.4: Issues mit Label als source=issue-Aufgaben importieren (read-only)."""
        actor = _admin_guard(x_jarvis_session, None, None, None)
        repository = str(deps.get("github_repo") or "lightcr1/jarvis")
        token = str(deps.get("github_token") or "")
        if "/" not in repository:
            raise HTTPException(503, "GITHUB_REPO not configured")
        owner_name, repo_name = repository.split("/", 1)
        try:
            issues = list_labeled_issues(owner_name, repo_name, label=label, token=token)
        except GithubGatewayError as exc:
            raise HTTPException(502, str(exc)) from exc
        imported = skipped = 0
        for issue in issues:
            external_id = f"{repository}#{issue['number']}"
            if store().find_by_external(external_id) is not None:
                skipped += 1
                continue
            try:
                store().create_task(title=issue["title"], description=issue["body"],
                                    area="general", size="medium", source="issue",
                                    status="open", external_id=external_id)
                imported += 1
            except ValueError:
                skipped += 1
        audit("agent.tasks.issues_imported", actor, {"repository": repository,
                                                     "imported": imported, "skipped": skipped})
        return {"imported": imported, "skipped": skipped, "issues": len(issues)}

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
    async def report_round(task_id: str, body: RoundReport,
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
        task = store().get_task(task_id)
        lines = [f"Autonomie-Runde ({body.outcome}): {body.summary}".strip()]
        if body.next_step:
            lines.append(f"Naechster Schritt: {body.next_step}")
        if body.owner_question:
            lines.append(f"Rueckfrage: {body.owner_question}")
        post_to_chat(task, "\n".join(lines))
        if body.owner_question or body.outcome == "blocked":
            await notify_owner_question(task_id, body.owner_question or "Aufgabe blockiert")
        return {"report": report, "task": task}

    return router
