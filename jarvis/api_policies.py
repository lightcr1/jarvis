from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Header, HTTPException

from .api_models import PlaybookCreate, PlaybookUpdate, PolicyCreate, PolicyUpdate
from .router_dependencies import LiveRef


def build_policies_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    def _admin_guard(
        x_jarvis_user_id: str | None = None,
        x_jarvis_role: str | None = None,
        authorization: str | None = None,
    ) -> tuple[str, str]:
        require_admin = current("require_admin_access")
        return require_admin(x_jarvis_user_id, x_jarvis_role, authorization)

    def _audit(event: str, actor_user_id: str, actor_role: str, payload: dict | None = None) -> None:
        fn: Callable = current("audit_admin_event")
        fn(event, actor_user_id, actor_role, payload)

    # -----------------------------------------------------------------
    # Policies
    # -----------------------------------------------------------------
    @router.get("/admin/policies")
    def list_policies(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"policies": current("policy_store").list_policies()}

    @router.post("/admin/policies", status_code=201)
    def create_policy(
        body: PolicyCreate,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        policy = current("policy_store").create_policy(body.model_dump())
        _audit("policy.created", actor_id, actor_role, {"policy_id": policy["id"], "name": policy["name"]})
        return {"policy": policy}

    @router.patch("/admin/policies/{policy_id}")
    def update_policy(
        policy_id: str,
        body: PolicyUpdate,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        updated = current("policy_store").update_policy(policy_id, patch)
        if updated is None:
            raise HTTPException(404, "Policy not found")
        _audit("policy.updated", actor_id, actor_role, {"policy_id": policy_id, "patch": list(patch.keys())})
        return {"policy": updated}

    @router.delete("/admin/policies/{policy_id}")
    def delete_policy(
        policy_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        deleted = current("policy_store").delete_policy(policy_id)
        if not deleted:
            raise HTTPException(404, "Policy not found")
        _audit("policy.deleted", actor_id, actor_role, {"policy_id": policy_id})
        return {"ok": True, "id": policy_id}

    @router.post("/admin/policies/{policy_id}/test")
    async def test_policy(
        policy_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        policy = current("policy_store").get_policy(policy_id)
        if policy is None:
            raise HTTPException(404, "Policy not found")
        outcome = await current("policy_engine").fire_test(policy)
        _audit("policy.tested", actor_id, actor_role, {"policy_id": policy_id})
        return {"ok": True, "event": outcome["event"], "escalated": outcome["escalated"]}

    @router.get("/admin/policies/history")
    def policy_history(
        limit: int = 100,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"events": current("policy_engine").get_history(limit=min(limit, 500))}

    # -----------------------------------------------------------------
    # Playbooks
    # -----------------------------------------------------------------
    @router.get("/admin/playbooks")
    def list_playbooks(
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"playbooks": current("playbook_store").list_playbooks()}

    @router.post("/admin/playbooks", status_code=201)
    def create_playbook(
        body: PlaybookCreate,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        playbook = current("playbook_store").create_playbook(body.model_dump())
        _audit("playbook.created", actor_id, actor_role, {"playbook_id": playbook["id"], "name": playbook["name"]})
        return {"playbook": playbook}

    @router.patch("/admin/playbooks/{playbook_id}")
    def update_playbook(
        playbook_id: str,
        body: PlaybookUpdate,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        patch = {k: v for k, v in body.model_dump().items() if v is not None}
        updated = current("playbook_store").update_playbook(playbook_id, patch)
        if updated is None:
            raise HTTPException(404, "Playbook not found")
        _audit("playbook.updated", actor_id, actor_role, {"playbook_id": playbook_id, "patch": list(patch.keys())})
        return {"playbook": updated}

    @router.delete("/admin/playbooks/{playbook_id}")
    def delete_playbook(
        playbook_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        deleted = current("playbook_store").delete_playbook(playbook_id)
        if not deleted:
            raise HTTPException(404, "Playbook not found")
        _audit("playbook.deleted", actor_id, actor_role, {"playbook_id": playbook_id})
        return {"ok": True, "id": playbook_id}

    @router.post("/admin/playbooks/{playbook_id}/execute")
    async def execute_playbook(
        playbook_id: str,
        dry_run: bool | None = None,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        if current("playbook_store").get_playbook(playbook_id) is None:
            raise HTTPException(404, "Playbook not found")
        _audit("playbook.execute.requested", actor_id, actor_role, {"playbook_id": playbook_id, "dry_run": dry_run})
        try:
            run = await current("playbook_executor").run(playbook_id, dry_run=dry_run)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        return {"run": run}

    @router.post("/admin/playbooks/runs/{run_id}/resume")
    async def resume_playbook_run(
        run_id: str,
        confirm: bool = True,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        actor_id, actor_role = _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        try:
            run = await current("playbook_executor").resume(run_id, confirm=confirm)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc
        _audit("playbook.run.resumed", actor_id, actor_role, {"run_id": run_id, "confirm": confirm})
        return {"run": run}

    @router.get("/admin/playbooks/{playbook_id}/runs")
    def list_playbook_runs(
        playbook_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        return {"runs": current("playbook_store").list_runs(playbook_id)}

    @router.get("/admin/playbooks/runs/{run_id}")
    def get_playbook_run(
        run_id: str,
        x_jarvis_user_id: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        authorization: str | None = Header(default=None),
    ):
        _admin_guard(x_jarvis_user_id, x_jarvis_role, authorization)
        run = current("playbook_store").get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return {"run": run}

    return router
