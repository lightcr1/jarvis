from __future__ import annotations

import logging
import time
from typing import Callable

from jarvis.infra_actions import restart_service

logger = logging.getLogger("jarvis.playbook_executor")


def _restart_service_step(params: dict, *, run_cmd: Callable, ensure_service_allowed: Callable) -> dict:
    service = params.get("service", "")
    return restart_service(service, run_cmd=run_cmd, ensure_service_allowed=ensure_service_allowed)


def _noop_step(params: dict) -> dict:
    return {"ok": True, "note": params.get("note", "")}


def build_default_action_dispatch(run_cmd: Callable, ensure_service_allowed: Callable) -> dict[str, Callable[[dict], dict]]:
    return {
        "restart_service": lambda params: _restart_service_step(params, run_cmd=run_cmd, ensure_service_allowed=ensure_service_allowed),
        "noop": _noop_step,
    }


class PlaybookExecutor:
    """Runs a playbook's steps sequentially, persisting per-step checkpoints via
    `PlaybookStore` so a service restart mid-run can resume from the first
    non-terminal step rather than starting over. Confirmation-gated steps pause the
    run (`awaiting_confirmation`) until `resume(run_id, confirm=True)` is called —
    mirrors the `ActionPlan`/`Skill` confirmation flow already used by dangerous chat
    skills, without introducing a second confirmation primitive.
    """

    def __init__(
        self,
        store: object,
        action_dispatch: dict[str, Callable[[dict], dict]],
        audit_admin_event: Callable,
        emergency_stop_enabled: Callable[[], bool],
        broadcast_fn: Callable | None = None,
    ) -> None:
        self._store = store
        self._dispatch = action_dispatch
        self._audit = audit_admin_event
        self._emergency_stop_enabled = emergency_stop_enabled
        self._broadcast_fn = broadcast_fn

    async def _broadcast(self, event: dict) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(event)
            except Exception as exc:
                logger.warning("Playbook broadcast failed: %s", exc)

    def start(self, playbook_id: str, *, dry_run: bool | None = None) -> dict:
        playbook = self._store.get_playbook(playbook_id)
        if playbook is None:
            raise ValueError(f"Playbook not found: {playbook_id}")
        effective_dry_run = playbook.get("dry_run", True) if dry_run is None else dry_run
        run = self._store.start_run(playbook, effective_dry_run)
        return run

    async def run(self, playbook_id: str, *, dry_run: bool | None = None) -> dict:
        run = self.start(playbook_id, dry_run=dry_run)
        return await self._advance(run["id"])

    async def resume(self, run_id: str, *, confirm: bool = True) -> dict:
        """Continues a paused/failed run from its first non-terminal step — covers both
        "user confirmed a gated step" and "admin fixed the underlying issue, retry the
        step that failed" (e.g. after a restart mid-playbook, or a transient failure).
        """
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        if run["status"] not in {"awaiting_confirmation", "failed"}:
            return run
        if run["status"] == "awaiting_confirmation" and not confirm:
            updated = self._store.update_run(run_id, {"status": "cancelled", "finished_at": int(time.time())})
            self._audit("playbook.run.cancelled", "system", "system", {"run_id": run_id})
            return updated or run
        # The step currently paused on a confirmation gate has already been confirmed —
        # don't re-trigger the same gate on this resume; later steps still respect it.
        skip_gate_for_resumed_step = run["status"] == "awaiting_confirmation"
        self._store.update_run(run_id, {"status": "running", "finished_at": None})
        return await self._advance(run_id, resuming=True, skip_confirmation_for_first=skip_gate_for_resumed_step)

    async def _advance(self, run_id: str, *, resuming: bool = False, skip_confirmation_for_first: bool = False) -> dict:
        run = self._store.get_run(run_id)
        if run is None:
            raise ValueError(f"Run not found: {run_id}")
        playbook = self._store.get_playbook(run["playbook_id"])
        if playbook is None:
            raise ValueError(f"Playbook not found: {run['playbook_id']}")

        steps = playbook.get("steps", [])
        step_status = {s["step_id"]: s for s in run.get("steps", [])}
        start_index = 0
        if resuming:
            for i, step in enumerate(steps):
                if step_status.get(step["step_id"], {}).get("status") not in {"succeeded", "skipped", "would_execute"}:
                    start_index = i
                    break

        for offset, step in enumerate(steps[start_index:]):
            skip_gate = skip_confirmation_for_first and offset == 0
            outcome = await self._run_step(run_id, playbook, step, run.get("dry_run", True), skip_confirmation=skip_gate)
            if outcome == "stop":
                return self._store.get_run(run_id) or run

        finished = self._store.update_run(run_id, {"status": "completed", "finished_at": int(time.time())})
        await self._broadcast({
            "type": "playbook_result",
            "run_id": run_id,
            "playbook_id": playbook["id"],
            "playbook_name": playbook.get("name", ""),
            "status": "completed",
            "message": f"Playbook '{playbook.get('name')}' completed.",
            "timestamp": int(time.time()),
        })
        return finished or run

    async def _run_step(self, run_id: str, playbook: dict, step: dict, dry_run: bool, *, skip_confirmation: bool = False) -> str:
        step_id = step["step_id"]

        if dry_run:
            self._store.update_step(run_id, step_id, {"status": "would_execute", "output": {"note": "dry run — not executed"}})
            return "continue"

        if step.get("requires_confirmation") and not skip_confirmation:
            self._store.update_run(run_id, {"status": "awaiting_confirmation"})
            self._store.update_step(run_id, step_id, {"status": "pending"})
            await self._broadcast({
                "type": "playbook_awaiting_confirmation",
                "run_id": run_id,
                "playbook_id": playbook["id"],
                "step_id": step_id,
                "message": f"Playbook '{playbook.get('name')}' is waiting for confirmation on step: {step.get('description') or step_id}.",
                "timestamp": int(time.time()),
            })
            return "stop"

        if self._emergency_stop_enabled():
            self._store.update_step(run_id, step_id, {"status": "failed", "error": "emergency_stop"})
            self._store.update_run(run_id, {"status": "failed", "finished_at": int(time.time())})
            self._audit("playbook.blocked_emergency_stop", "system", "system", {"run_id": run_id, "step_id": step_id})
            await self._broadcast({
                "type": "policy_escalation",
                "run_id": run_id,
                "playbook_id": playbook["id"],
                "severity": "critical",
                "message": f"Sir, playbook '{playbook.get('name')}' halted — JARVIS_EMERGENCY_STOP is active.",
                "timestamp": int(time.time()),
            })
            return "stop"

        self._store.update_step(run_id, step_id, {"status": "running", "started_at": int(time.time())})
        action = step.get("action", {})
        handler = self._dispatch.get(action.get("type"))
        try:
            if handler is None:
                raise ValueError(f"Unsupported step action type: {action.get('type')!r}")
            output = handler(action.get("params", {}))
            self._store.update_step(run_id, step_id, {"status": "succeeded", "finished_at": int(time.time()), "output": output})
            self._audit("playbook.step.succeeded", "system", "system", {"run_id": run_id, "step_id": step_id})
            return "continue"
        except Exception as exc:
            self._store.update_step(run_id, step_id, {"status": "failed", "finished_at": int(time.time()), "error": str(exc)})
            self._store.update_run(run_id, {"status": "failed", "finished_at": int(time.time())})
            self._audit("playbook.step.failed", "system", "system", {"run_id": run_id, "step_id": step_id, "error": str(exc)})
            await self._broadcast({
                "type": "playbook_result",
                "run_id": run_id,
                "playbook_id": playbook["id"],
                "playbook_name": playbook.get("name", ""),
                "status": "failed",
                "message": f"Playbook '{playbook.get('name')}' failed at step: {step.get('description') or step_id}.",
                "timestamp": int(time.time()),
            })
            return "stop"
