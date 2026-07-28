from __future__ import annotations

import os
import tempfile

import pytest

from jarvis.playbook_store import PlaybookStore
from jarvis.playbook_executor import PlaybookExecutor, build_default_action_dispatch


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_PLAYBOOK_STORE_PATH"] = tmp
    yield PlaybookStore()
    os.environ.pop("JARVIS_PLAYBOOK_STORE_PATH", None)
    try:
        os.unlink(tmp)
    except OSError:
        pass


class _Recorder:
    def __init__(self):
        self.events: list[dict] = []
        self.audits: list[tuple] = []

    async def broadcast(self, event: dict) -> None:
        self.events.append(event)

    def audit(self, event, actor, role, payload=None) -> None:
        self.audits.append((event, payload))


def _make_executor(store, recorder, dispatch, *, emergency_stop=False) -> PlaybookExecutor:
    return PlaybookExecutor(
        store=store,
        action_dispatch=dispatch,
        audit_admin_event=recorder.audit,
        emergency_stop_enabled=lambda: emergency_stop,
        broadcast_fn=recorder.broadcast,
    )


# ---------------------------------------------------------------------------
# Sequential execution + dry-run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_sequential_execution_all_succeed(store):
    pb = store.create_playbook({
        "name": "simple",
        "dry_run": False,
        "steps": [
            {"step_id": "s1", "action": {"type": "noop", "params": {}}},
            {"step_id": "s2", "action": {"type": "noop", "params": {}}},
        ],
    })
    recorder = _Recorder()
    executor = _make_executor(store, recorder, {"noop": lambda p: {"ok": True}})
    run = await executor.run(pb["id"])
    assert run["status"] == "completed"
    assert [s["status"] for s in run["steps"]] == ["succeeded", "succeeded"]
    assert recorder.events[-1]["type"] == "playbook_result"
    assert recorder.events[-1]["status"] == "completed"


@pytest.mark.asyncio
async def test_dry_run_marks_would_execute_and_never_calls_dispatch(store):
    pb = store.create_playbook({
        "name": "dry",
        "dry_run": True,
        "steps": [{"step_id": "s1", "action": {"type": "restart_service", "params": {"service": "nginx"}}}],
    })
    called = []
    executor = _make_executor(store, _Recorder(), {"restart_service": lambda p: called.append(p) or {"ok": True}})
    run = await executor.run(pb["id"])
    assert run["status"] == "completed"
    assert run["steps"][0]["status"] == "would_execute"
    assert called == []


@pytest.mark.asyncio
async def test_execute_override_forces_live_even_if_playbook_defaults_dry(store):
    pb = store.create_playbook({
        "name": "override",
        "dry_run": True,
        "steps": [{"step_id": "s1", "action": {"type": "noop", "params": {}}}],
    })
    calls = []
    executor = _make_executor(store, _Recorder(), {"noop": lambda p: calls.append(p) or {"ok": True}})
    run = await executor.run(pb["id"], dry_run=False)
    assert run["steps"][0]["status"] == "succeeded"
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Confirmation gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_confirmation_required_step_pauses_run(store):
    pb = store.create_playbook({
        "name": "gated",
        "dry_run": False,
        "steps": [
            {"step_id": "s1", "action": {"type": "noop", "params": {}}},
            {"step_id": "s2", "action": {"type": "noop", "params": {}}, "requires_confirmation": True},
            {"step_id": "s3", "action": {"type": "noop", "params": {}}},
        ],
    })
    recorder = _Recorder()
    executor = _make_executor(store, recorder, {"noop": lambda p: {"ok": True}})
    run = await executor.run(pb["id"])
    assert run["status"] == "awaiting_confirmation"
    assert [s["status"] for s in run["steps"]] == ["succeeded", "pending", "pending"]
    assert recorder.events[-1]["type"] == "playbook_awaiting_confirmation"


@pytest.mark.asyncio
async def test_resume_with_confirmation_continues_past_gate(store):
    pb = store.create_playbook({
        "name": "gated",
        "dry_run": False,
        "steps": [
            {"step_id": "s1", "action": {"type": "noop", "params": {}}, "requires_confirmation": True},
            {"step_id": "s2", "action": {"type": "noop", "params": {}}},
        ],
    })
    executor = _make_executor(store, _Recorder(), {"noop": lambda p: {"ok": True}})
    run = await executor.run(pb["id"])
    assert run["status"] == "awaiting_confirmation"

    resumed = await executor.resume(run["id"], confirm=True)
    assert resumed["status"] == "completed"
    assert [s["status"] for s in resumed["steps"]] == ["succeeded", "succeeded"]


@pytest.mark.asyncio
async def test_resume_without_confirmation_cancels_run(store):
    pb = store.create_playbook({
        "name": "gated",
        "dry_run": False,
        "steps": [{"step_id": "s1", "action": {"type": "noop", "params": {}}, "requires_confirmation": True}],
    })
    executor = _make_executor(store, _Recorder(), {"noop": lambda p: {"ok": True}})
    run = await executor.run(pb["id"])
    assert run["status"] == "awaiting_confirmation"

    cancelled = await executor.resume(run["id"], confirm=False)
    assert cancelled["status"] == "cancelled"


# ---------------------------------------------------------------------------
# Failure + resume-after-failure (checkpoint persistence across a fresh executor,
# simulating a process restart)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_step_failure_halts_run_and_persists_checkpoint(store):
    pb = store.create_playbook({
        "name": "flaky",
        "dry_run": False,
        "steps": [
            {"step_id": "s1", "action": {"type": "noop", "params": {}}},
            {"step_id": "s2", "action": {"type": "boom", "params": {}}},
            {"step_id": "s3", "action": {"type": "noop", "params": {}}},
        ],
    })

    def boom(params):
        raise RuntimeError("simulated failure")

    recorder = _Recorder()
    executor = _make_executor(store, recorder, {"noop": lambda p: {"ok": True}, "boom": boom})
    run = await executor.run(pb["id"])
    assert run["status"] == "failed"
    assert [s["status"] for s in run["steps"]] == ["succeeded", "failed", "pending"]
    assert recorder.events[-1]["type"] == "playbook_result"
    assert recorder.events[-1]["status"] == "failed"
    assert any(e == "playbook.step.failed" for e, _ in recorder.audits)


@pytest.mark.asyncio
async def test_resume_after_failure_retries_failed_step(store):
    pb = store.create_playbook({
        "name": "flaky",
        "dry_run": False,
        "steps": [
            {"step_id": "s1", "action": {"type": "noop", "params": {}}},
            {"step_id": "s2", "action": {"type": "flaky", "params": {}}},
            {"step_id": "s3", "action": {"type": "noop", "params": {}}},
        ],
    })

    attempts = {"n": 0}

    def flaky(params):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("transient")
        return {"ok": True}

    dispatch = {"noop": lambda p: {"ok": True}, "flaky": flaky}
    executor = _make_executor(store, _Recorder(), dispatch)
    run = await executor.run(pb["id"])
    assert run["status"] == "failed"

    # Simulate a process restart: fresh store read + fresh executor instance.
    fresh_store = PlaybookStore()
    fresh_executor = _make_executor(fresh_store, _Recorder(), dispatch)
    resumed = await fresh_executor.resume(run["id"])
    assert resumed["status"] == "completed"
    assert [s["status"] for s in resumed["steps"]] == ["succeeded", "succeeded", "succeeded"]


@pytest.mark.asyncio
async def test_resume_on_non_resumable_run_is_a_noop(store):
    pb = store.create_playbook({
        "name": "simple",
        "dry_run": False,
        "steps": [{"step_id": "s1", "action": {"type": "noop", "params": {}}}],
    })
    executor = _make_executor(store, _Recorder(), {"noop": lambda p: {"ok": True}})
    run = await executor.run(pb["id"])
    assert run["status"] == "completed"

    resumed = await executor.resume(run["id"])
    assert resumed["status"] == "completed"  # unchanged, no-op


# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_stop_halts_live_step(store):
    pb = store.create_playbook({
        "name": "gated-by-estop",
        "dry_run": False,
        "steps": [{"step_id": "s1", "action": {"type": "restart_service", "params": {"service": "nginx"}}}],
    })
    called = []
    recorder = _Recorder()
    executor = _make_executor(
        store, recorder,
        {"restart_service": lambda p: called.append(p) or {"ok": True}},
        emergency_stop=True,
    )
    run = await executor.run(pb["id"])
    assert run["status"] == "failed"
    assert run["steps"][0]["status"] == "failed"
    assert run["steps"][0]["error"] == "emergency_stop"
    assert called == []
    assert any(e == "playbook.blocked_emergency_stop" for e, _ in recorder.audits)


# ---------------------------------------------------------------------------
# build_default_action_dispatch
# ---------------------------------------------------------------------------

def test_build_default_action_dispatch_includes_restart_and_noop():
    dispatch = build_default_action_dispatch(lambda cmd, timeout=8: "active", lambda service: None)
    assert "restart_service" in dispatch
    assert "noop" in dispatch
    result = dispatch["restart_service"]({"service": "nginx"})
    assert result["healthy"] is True
