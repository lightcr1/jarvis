"""Tests fuer die woechentlichen Messgroessen (Abschnitt 6.1)."""
from __future__ import annotations

from jarvis.agent_metrics import summarize, weekly_metrics


def test_summarize_counts_and_suggestions():
    tasks = [{"status": "done"}, {"status": "blocked"}, {"status": "open"}]
    reports = [{"outcome": "done"}, {"outcome": "blocked"}]
    approvals = ([{"capability": "service.restart", "status": "approved"}] * 3
                 + [{"capability": "email.send", "status": "rejected"}])
    m = summarize(tasks, reports, approvals, gpu_seconds=3600)
    assert m["tasks"] == {"total": 3, "done": 1, "blocked": 1, "done_rate": 0.333}
    assert m["rounds"]["blocked_rate"] == 0.5
    assert m["approvals"] == {"asked": 4, "approved": 3, "rejected": 1, "pending": 0}
    assert m["done_per_gpu_hour"] == 1.0
    assert m["standing_grant_suggestions"] == ["service.restart"]


def test_weekly_metrics_from_stores(tmp_path):
    from jarvis.agent_grants import AgentGrantStore
    from jarvis.autonomy_task_store import AutonomyTaskStore

    tasks = AutonomyTaskStore(tmp_path / "t.sqlite3")
    grants = AgentGrantStore(tmp_path / "g.sqlite3", clock=lambda: 0)
    task = tasks.create_task(title="A")
    tasks.record_report(task_id=task["id"], round_id="r1", outcome="done", summary="ok")
    req = grants.request_approval(capability="service.restart", target="x", tier="T2")
    grants.decide_approval(req["id"], actor="owner", approve=True)
    m = weekly_metrics(tasks, grants)
    assert m["tasks"]["done"] >= 1
    assert m["approvals"]["asked"] == 1 and m["approvals"]["approved"] == 1
