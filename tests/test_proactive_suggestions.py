from __future__ import annotations

from jarvis.proactive_suggestions import (
    IdleResourceTracker,
    SuggestionEngine,
    detect_backup_failure_streak,
    detect_repeated_skill_invocations,
    flatten_proxmox_items,
)


# ---------------------------------------------------------------------------
# detect_repeated_skill_invocations
# ---------------------------------------------------------------------------

def test_repeated_skill_invocation_flagged_above_threshold():
    learned = {
        "restart nginx": {"skill": "restart", "confidence": 6},
        "weather zurich": {"skill": "weather", "confidence": 1},
    }
    suggestions = detect_repeated_skill_invocations(learned, threshold=5)
    assert len(suggestions) == 1
    assert suggestions[0]["kind"] == "repeated_skill"
    assert suggestions[0]["key"] == "restart nginx"
    assert suggestions[0]["count"] == 6


def test_repeated_skill_invocation_empty_when_below_threshold():
    learned = {"restart nginx": {"skill": "restart", "confidence": 2}}
    assert detect_repeated_skill_invocations(learned, threshold=5) == []


def test_repeated_skill_invocation_handles_empty_input():
    assert detect_repeated_skill_invocations({}, threshold=5) == []
    assert detect_repeated_skill_invocations(None, threshold=5) == []  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# flatten_proxmox_items
# ---------------------------------------------------------------------------

def test_flatten_proxmox_items():
    health = {
        "hosts": [
            {
                "id": "host-1",
                "nodes": [
                    {
                        "node": "pve-01",
                        "vms": [{"vmid": 100, "name": "web", "status": "running", "cpu": 0.01}],
                        "containers": [{"vmid": 200, "name": "ct1", "status": "stopped", "cpu": 0.0}],
                    }
                ],
            }
        ]
    }
    items = flatten_proxmox_items(health)
    assert len(items) == 2
    vm = next(i for i in items if i["resource_type"] == "vm")
    assert vm["host_id"] == "host-1"
    assert vm["node"] == "pve-01"
    assert vm["vmid"] == 100


def test_flatten_proxmox_items_handles_missing_or_unconfigured():
    assert flatten_proxmox_items(None) == []
    assert flatten_proxmox_items({"configured": False}) == []


# ---------------------------------------------------------------------------
# detect_backup_failure_streak
# ---------------------------------------------------------------------------

def test_backup_failure_streak_detected():
    log = [{"ts": 1, "ok": True}, {"ts": 2, "ok": False}, {"ts": 3, "ok": False}, {"ts": 4, "ok": False}]
    result = detect_backup_failure_streak(log, streak_threshold=3)
    assert result is not None
    assert result["kind"] == "backup_failures"
    assert result["count"] == 3


def test_backup_failure_streak_not_detected_when_interrupted():
    log = [{"ts": 1, "ok": False}, {"ts": 2, "ok": True}, {"ts": 3, "ok": False}]
    assert detect_backup_failure_streak(log, streak_threshold=3) is None


def test_backup_failure_streak_not_detected_when_too_short():
    log = [{"ts": 1, "ok": False}]
    assert detect_backup_failure_streak(log, streak_threshold=3) is None


# ---------------------------------------------------------------------------
# IdleResourceTracker
# ---------------------------------------------------------------------------

def test_idle_resource_tracker_fires_after_days_threshold():
    tracker = IdleResourceTracker(idle_cpu_threshold=0.02, idle_days_threshold=3.0)
    items = [{"host_id": "h1", "node": "pve-01", "vmid": 100, "name": "idle-vm", "status": "running", "cpu": 0.0}]

    now = 1_000_000.0
    assert tracker.evaluate(items, now) == []  # just started tracking

    # 2 days later — still under threshold
    assert tracker.evaluate(items, now + 2 * 86400) == []

    # 3.5 days later — should fire
    suggestions = tracker.evaluate(items, now + 3.5 * 86400)
    assert len(suggestions) == 1
    assert suggestions[0]["kind"] == "idle_resource"
    assert suggestions[0]["idle_days"] >= 3.0


def test_idle_resource_tracker_resets_when_cpu_rises():
    tracker = IdleResourceTracker(idle_cpu_threshold=0.02, idle_days_threshold=1.0)
    idle_item = [{"host_id": "h1", "node": "pve-01", "vmid": 100, "name": "vm", "status": "running", "cpu": 0.0}]
    busy_item = [{"host_id": "h1", "node": "pve-01", "vmid": 100, "name": "vm", "status": "running", "cpu": 0.5}]

    now = 2_000_000.0
    tracker.evaluate(idle_item, now)
    tracker.evaluate(busy_item, now + 3600)  # cpu spikes — resets the timer
    result = tracker.evaluate(idle_item, now + 1.5 * 86400)
    assert result == []  # not idle long enough since the reset


def test_idle_resource_tracker_ignores_stopped_resources():
    tracker = IdleResourceTracker(idle_cpu_threshold=0.02, idle_days_threshold=1.0)
    items = [{"host_id": "h1", "node": "pve-01", "vmid": 100, "name": "vm", "status": "stopped", "cpu": 0.0}]
    now = 3_000_000.0
    assert tracker.evaluate(items, now) == []
    assert tracker.evaluate(items, now + 5 * 86400) == []


# ---------------------------------------------------------------------------
# SuggestionEngine (composition + cooldown)
# ---------------------------------------------------------------------------

def test_suggestion_engine_composes_all_heuristics():
    engine = SuggestionEngine(idle_days_threshold=1.0, cooldown_seconds=3600)
    now = 5_000_000.0
    learned = {"restart nginx": {"skill": "restart", "confidence": 6}}
    backup_log = [{"ts": now - 1, "ok": False}, {"ts": now - 2, "ok": False}, {"ts": now - 3, "ok": False}]

    events = engine.evaluate(
        learned_replies=learned,
        proxmox_health=None,
        backup_log=backup_log,
        now=now,
    )
    kinds = {e["kind"] for e in events}
    assert "repeated_skill" in kinds
    assert "backup_failures" in kinds
    for event in events:
        assert event["type"] == "suggestion"
        assert "suggestion_id" in event


def test_suggestion_engine_respects_cooldown():
    engine = SuggestionEngine(cooldown_seconds=3600)
    now = 6_000_000.0
    learned = {"restart nginx": {"skill": "restart", "confidence": 6}}

    first = engine.evaluate(learned_replies=learned, proxmox_health=None, backup_log=[], now=now)
    assert len(first) == 1

    # Same key, well within cooldown — should NOT refire
    second = engine.evaluate(learned_replies=learned, proxmox_health=None, backup_log=[], now=now + 60)
    assert second == []

    # Past cooldown — fires again
    third = engine.evaluate(learned_replies=learned, proxmox_health=None, backup_log=[], now=now + 3700)
    assert len(third) == 1
