from __future__ import annotations

import os
import tempfile
import time

import pytest

from jarvis.policy_store import PolicyStore
from jarvis.policy_engine import PolicyEngine


@pytest.fixture
def store():
    tmp = tempfile.mktemp(suffix=".json")
    os.environ["JARVIS_POLICY_STORE_PATH"] = tmp
    yield PolicyStore()
    os.environ.pop("JARVIS_POLICY_STORE_PATH", None)
    try:
        os.unlink(tmp)
    except OSError:
        pass


class _Recorder:
    def __init__(self):
        self.events: list[dict] = []
        self.audits: list[tuple] = []
        self.restart_calls: list[list[str]] = []
        self.restarted = False
        self.recovers_after_restart = False

    async def broadcast(self, event: dict) -> None:
        self.events.append(event)

    def audit(self, event, actor_user_id, actor_role, payload=None) -> None:
        self.audits.append((event, payload))

    def run_cmd(self, cmd: list[str], timeout: int = 8) -> str:
        self.restart_calls.append(cmd)
        if "restart" in cmd:
            self.restarted = True
        if "is-active" in cmd:
            if self.restarted and self.recovers_after_restart:
                return "active"
            return self.active_state
        return ""


def _make_engine(store, recorder, *, active_state="failed", emergency_stop=False, permission=True, escalate_after=2, recovers_after_restart=False):
    recorder.active_state = active_state
    recorder.recovers_after_restart = recovers_after_restart
    return PolicyEngine(
        policy_store=store,
        run_cmd=recorder.run_cmd,
        ensure_service_allowed=lambda service: None,
        emergency_stop_enabled=lambda: emergency_stop,
        write_permission_check=lambda: permission,
        audit_admin_event=recorder.audit,
        broadcast_fn=recorder.broadcast,
        escalate_after_incidents=escalate_after,
    )


def _make_policy(store, **overrides):
    payload = {
        "name": "nginx self-heal",
        "condition": {"metric": "service_status", "comparator": "equals", "threshold": "failed", "duration_sec": 0},
        "action": {"type": "restart_service", "params": {"service": "nginx"}},
        "enabled": True,
        "dry_run": False,
        "cooldown_sec": 60,
    }
    payload.update(overrides)
    return store.create_policy(payload)


# ---------------------------------------------------------------------------
# Threshold / comparator evaluation (reused _evaluate_condition, sanity-checked here
# against a policy shape rather than an AlertRule shape)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_above_threshold_fires(store):
    recorder = _Recorder()
    policy = _make_policy(
        store,
        condition={"metric": "service_status", "comparator": "above", "threshold": 50.0, "duration_sec": 0},
        action={"type": "restart_service", "params": {"service": "nginx"}},
    )
    engine = _make_engine(store, recorder)
    engine._sources["service_status"] = lambda p: 99.0  # override to a numeric reading
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert len(recorder.events) == 1


@pytest.mark.asyncio
async def test_below_threshold_does_not_fire_when_above(store):
    recorder = _Recorder()
    policy = _make_policy(
        store,
        condition={"metric": "service_status", "comparator": "below", "threshold": 50.0, "duration_sec": 0},
    )
    engine = _make_engine(store, recorder)
    engine._sources["service_status"] = lambda p: 99.0
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert recorder.events == []


# ---------------------------------------------------------------------------
# Duration gate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duration_gate_delays_fire(store):
    recorder = _Recorder()
    policy = _make_policy(store, condition={"metric": "service_status", "comparator": "equals", "threshold": "failed", "duration_sec": 300})
    engine = _make_engine(store, recorder)
    now = time.time()

    await engine._evaluate_policy(store.get_policy(policy["id"]), now)
    assert recorder.events == []  # threshold just crossed, duration not met

    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 100)
    assert recorder.events == []  # still not 300s

    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 301)
    assert len(recorder.events) == 1


# ---------------------------------------------------------------------------
# Cooldown gate (persisted via PolicyStore.last_fired_at)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_respected_across_evaluations(store):
    recorder = _Recorder()
    policy = _make_policy(store, cooldown_sec=600)
    engine = _make_engine(store, recorder)
    now = time.time()

    await engine._evaluate_policy(store.get_policy(policy["id"]), now)
    assert len(recorder.events) == 1

    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 10)
    assert len(recorder.events) == 1  # within cooldown — no second fire

    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 601)
    assert len(recorder.events) == 2  # cooldown passed


@pytest.mark.asyncio
async def test_cooldown_survives_fresh_store_instance(store):
    """last_fired_at is persisted, so cooldown holds even across a fresh PolicyEngine
    built on a freshly-loaded store (simulates a process restart)."""
    recorder = _Recorder()
    policy = _make_policy(store, cooldown_sec=600)
    engine = _make_engine(store, recorder)
    now = time.time()
    await engine._evaluate_policy(store.get_policy(policy["id"]), now)
    assert len(recorder.events) == 1

    fresh_store = PolicyStore()
    fresh_engine = _make_engine(fresh_store, recorder)
    await fresh_engine._evaluate_policy(fresh_store.get_policy(policy["id"]), now + 30)
    assert len(recorder.events) == 1  # still within cooldown


# ---------------------------------------------------------------------------
# Self-healing: restart-then-escalate
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_restart_attempted_on_live_policy(store):
    recorder = _Recorder()
    policy = _make_policy(store)
    engine = _make_engine(store, recorder, active_state="failed")
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert any("restart" in " ".join(c) for c in recorder.restart_calls)
    assert ("policy.self_heal.restart_attempted", None) not in recorder.audits  # payload non-None, just checking event name present
    assert any(e == "policy.self_heal.restart_attempted" for e, _ in recorder.audits)


@pytest.mark.asyncio
async def test_successful_restart_does_not_escalate(store):
    recorder = _Recorder()
    policy = _make_policy(store)
    # Service reads "failed" until restarted, then recovers to "active" — matches how
    # a real successful `systemctl restart` would behave.
    engine = _make_engine(store, recorder, active_state="failed", recovers_after_restart=True)
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert recorder.events[-1]["type"] == "policy_action"
    assert any("restart" in c for c in recorder.restart_calls)


@pytest.mark.asyncio
async def test_repeated_failure_escalates_within_retry_window(store):
    recorder = _Recorder()
    policy = _make_policy(store, cooldown_sec=60)
    engine = _make_engine(store, recorder, active_state="failed", escalate_after=2)
    now = time.time()

    await engine._evaluate_policy(store.get_policy(policy["id"]), now)
    assert recorder.events[-1]["type"] == "policy_action"  # first failure, not yet escalated

    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 61)
    assert recorder.events[-1]["type"] == "policy_escalation"  # second failure within window


@pytest.mark.asyncio
async def test_no_escalation_outside_retry_window(store):
    recorder = _Recorder()
    policy = _make_policy(store, cooldown_sec=60)
    engine = _make_engine(store, recorder, active_state="failed", escalate_after=2)
    engine._retry_window_sec = 100  # tight window
    now = time.time()

    await engine._evaluate_policy(store.get_policy(policy["id"]), now)
    assert recorder.events[-1]["type"] == "policy_action"

    # Second incident well outside the retry window — counter should reset, no escalation
    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 500)
    assert recorder.events[-1]["type"] == "policy_action"


# ---------------------------------------------------------------------------
# Emergency stop
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_emergency_stop_blocks_restart(store):
    recorder = _Recorder()
    policy = _make_policy(store)
    engine = _make_engine(store, recorder, active_state="failed", emergency_stop=True)
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())

    restart_cmds = [c for c in recorder.restart_calls if "restart" in c]
    assert restart_cmds == []  # no live systemctl restart was ever issued
    assert recorder.events[-1]["type"] == "policy_escalation"
    assert any(e == "policy.blocked_emergency_stop" for e, _ in recorder.audits)


@pytest.mark.asyncio
async def test_missing_write_permission_blocks_restart(store):
    recorder = _Recorder()
    policy = _make_policy(store)
    engine = _make_engine(store, recorder, active_state="failed", permission=False)
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())

    restart_cmds = [c for c in recorder.restart_calls if "restart" in c]
    assert restart_cmds == []
    assert any(e == "policy.blocked_permission_denied" for e, _ in recorder.audits)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dry_run_never_executes_restart(store):
    recorder = _Recorder()
    policy = _make_policy(store, dry_run=True)
    engine = _make_engine(store, recorder, active_state="failed")
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())

    restart_cmds = [c for c in recorder.restart_calls if "restart" in c]
    assert restart_cmds == []
    assert recorder.events[-1]["type"] == "policy_dry_run"


@pytest.mark.asyncio
async def test_dry_run_does_not_persist_last_fired_at(store):
    recorder = _Recorder()
    policy = _make_policy(store, dry_run=True)
    engine = _make_engine(store, recorder, active_state="failed")
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert store.get_policy(policy["id"])["last_fired_at"] is None


# ---------------------------------------------------------------------------
# Missing signal / disabled policies / unregistered metric
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_missing_signal_value_resets_duration_tracking(store):
    recorder = _Recorder()
    policy = _make_policy(store, condition={"metric": "service_status", "comparator": "equals", "threshold": "failed", "duration_sec": 300})
    engine = _make_engine(store, recorder, active_state="failed")
    now = time.time()
    await engine._evaluate_policy(store.get_policy(policy["id"]), now)
    assert policy["id"] in engine._threshold_crossed_at

    engine._sources["service_status"] = lambda p: None
    await engine._evaluate_policy(store.get_policy(policy["id"]), now + 50)
    assert policy["id"] not in engine._threshold_crossed_at
    assert recorder.events == []


@pytest.mark.asyncio
async def test_unregistered_metric_skipped_gracefully(store):
    recorder = _Recorder()
    policy = _make_policy(store, condition={"metric": "no_such_metric", "comparator": "above", "threshold": 1, "duration_sec": 0})
    engine = _make_engine(store, recorder)
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert recorder.events == []


@pytest.mark.asyncio
async def test_unsupported_action_type_reported_not_crashed(store):
    recorder = _Recorder()
    # Use a metric independent of action.params.service, since this action has none.
    policy = _make_policy(
        store,
        condition={"metric": "custom_test_metric", "comparator": "above", "threshold": 0, "duration_sec": 0},
        action={"type": "send_email", "params": {}},
    )
    engine = _make_engine(store, recorder)
    engine._sources["custom_test_metric"] = lambda p: 99
    await engine._evaluate_policy(store.get_policy(policy["id"]), time.time())
    assert recorder.events[-1]["type"] == "policy_action_unsupported"


# ---------------------------------------------------------------------------
# fire_test (admin "test" button) — bypasses gates, doesn't mutate cooldown state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fire_test_bypasses_cooldown_and_does_not_persist(store):
    recorder = _Recorder()
    policy = _make_policy(store, dry_run=True)
    engine = _make_engine(store, recorder, active_state="failed")
    outcome = await engine.fire_test(store.get_policy(policy["id"]))
    assert "[TEST]" in outcome["event"]["message"]
    assert store.get_policy(policy["id"])["last_fired_at"] is None
