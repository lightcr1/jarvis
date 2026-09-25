"""Tests for the autonomy backlog store + round reports."""
from __future__ import annotations

import pytest

from jarvis.autonomy_task_store import (
    AutonomyTaskStore,
    MAX_TASK_ATTEMPTS,
    AGENT_PROPOSAL_LIMIT,
)


def _store(tmp_path):
    return AutonomyTaskStore(tmp_path / "tasks.sqlite3")


def test_create_list_and_priority_order(tmp_path):
    store = _store(tmp_path)
    low = store.create_task(title="Low", area="tasks", priority=1)
    high = store.create_task(title="High", area="tasks", priority=50)
    assert [t["id"] for t in store.list_tasks()] == [high["id"], low["id"]]
    assert store.next_open_task()["id"] == high["id"]


def test_area_filter_falls_back_to_general(tmp_path):
    store = _store(tmp_path)
    general = store.create_task(title="General", area="general", priority=10)
    other = store.create_task(title="Other", area="billing", priority=99)
    assert store.next_open_task(area="tasks")["id"] == general["id"]
    assert store.next_open_task(area="billing")["id"] == other["id"]


def test_update_and_decide_proposal(tmp_path):
    store = _store(tmp_path)
    task = store.propose_task(title="Agent proposal", area="autonomy")
    assert task["status"] == "proposed"
    updated = store.update_task(task["id"], priority=42, size="small")
    assert updated["priority"] == 42 and updated["size"] == "small"
    approved = store.decide_task(task["id"], actor="owner", approve=True)
    assert approved["status"] == "open"
    assert store.decide_task(task["id"], actor="owner", approve=False) is None


def test_claim_increments_attempts_and_escalates(tmp_path):
    store = _store(tmp_path)
    task = store.create_task(title="Hard", area="tasks")
    for round_id in ("r1", "r2", "r3"):
        claimed = store.claim_task(task["id"], round_id=round_id)
        assert claimed is not None
        # Noch nicht in_progress -> erneut oeffnen fuer den naechsten Versuch.
        store.record_report(task_id=task["id"], round_id=round_id, outcome="no_change",
                            summary="no luck")
    assert store.get_task(task["id"])["status"] == "blocked"
    assert store.claim_task(task["id"], round_id="r4") is None


def test_claim_is_single_use(tmp_path):
    store = _store(tmp_path)
    task = store.create_task(title="Once", area="tasks")
    assert store.claim_task(task["id"], round_id="r1") is not None
    assert store.claim_task(task["id"], round_id="r2") is None


def test_record_report_outcome_updates_task_status(tmp_path):
    store = _store(tmp_path)
    done = store.create_task(title="Done", area="tasks")
    store.claim_task(done["id"], round_id="r1")
    store.record_report(task_id=done["id"], round_id="r1", outcome="done", summary="ok")
    assert store.get_task(done["id"])["status"] == "done"

    blocked = store.create_task(title="Blocked", area="tasks")
    store.claim_task(blocked["id"], round_id="r2")
    store.record_report(task_id=blocked["id"], round_id="r2", outcome="blocked",
                        summary="needs owner", owner_question="Which key?")
    assert store.get_task(blocked["id"])["status"] == "blocked"

    submitted = store.create_task(title="Submitted", area="tasks")
    store.claim_task(submitted["id"], round_id="r3")
    store.record_report(task_id=submitted["id"], round_id="r3", outcome="submitted",
                        summary="PR #1")
    assert store.get_task(submitted["id"])["status"] == "submitted"


def test_last_report_returns_newest(tmp_path):
    store = _store(tmp_path)
    task = store.create_task(title="Notes", area="tasks")
    store.claim_task(task["id"], round_id="r1")
    store.record_report(task_id=task["id"], round_id="r1", outcome="partial", summary="first")
    store.claim_task(task["id"], round_id="r2")
    store.record_report(task_id=task["id"], round_id="r2", outcome="partial", summary="second")
    assert store.last_report(task["id"])["summary"] == "second"
    assert store.last_report("missing") is None


def test_agent_proposal_limit(tmp_path):
    store = _store(tmp_path)
    for index in range(AGENT_PROPOSAL_LIMIT):
        store.propose_task(title=f"Idea {index}", area="autonomy")
    with pytest.raises(ValueError, match="proposal limit"):
        store.propose_task(title="One too many", area="autonomy")


def test_validation_rejects_bad_input(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.create_task(title="  padded  ")
    with pytest.raises(ValueError):
        store.create_task(title="bad size", size="huge")
    with pytest.raises(ValueError):
        store.update_task("missing", size="tiny")


def test_summary_is_capped_at_800(tmp_path):
    store = _store(tmp_path)
    report = store.record_report(task_id=None, round_id="r1", outcome="unknown",
                                 summary="x" * 5000)
    assert len(report["summary"]) == 800
    assert MAX_TASK_ATTEMPTS == 3


def test_next_open_task_excludes_ids_and_areas(tmp_path):
    store = _store(tmp_path)
    a = store.create_task(title="A", area="tasks", priority=10)
    b = store.create_task(title="B", area="billing", priority=9)
    assert store.next_open_task(exclude_areas={"tasks"})["id"] == b["id"]
    assert store.next_open_task(exclude_ids={a["id"]})["id"] == b["id"]
    assert store.next_open_task(exclude_ids={a["id"]}, exclude_areas={"billing"}) is None


def test_escalates_after_two_failures_and_hides_task(tmp_path):
    store = _store(tmp_path)
    task = store.create_task(title="Hard", area="tasks")
    for round_id in ("r1", "r2"):
        store.claim_task(task["id"], round_id=round_id)
        store.record_report(task_id=task["id"], round_id=round_id, outcome="no_change",
                            summary="no luck")
    assert store.get_task(task["id"])["escalated"] == 1
    assert store.next_open_task() is None


def test_review_task_writes_merge_result_back(tmp_path):
    store = _store(tmp_path)
    merged = store.create_task(title="Merged", area="tasks")
    assert store.review_task(merged["id"], actor="owner", decision="merged")["status"] == "done"
    rejected = store.create_task(title="Rejected", area="tasks")
    assert store.review_task(rejected["id"], actor="owner", decision="rejected")["status"] == "rejected"
    with pytest.raises(ValueError):
        store.review_task("missing", actor="owner", decision="maybe")


def test_area_success_rates(tmp_path):
    store = _store(tmp_path)
    good = store.create_task(title="Good", area="tasks")
    store.review_task(good["id"], actor="owner", decision="merged")
    bad = store.create_task(title="Bad", area="tasks")
    store.review_task(bad["id"], actor="owner", decision="rejected")
    rates = store.area_success_rates()
    assert rates["tasks"]["success_rate"] == 0.5


def test_migration_adds_escalated_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE autonomy_tasks (id TEXT PRIMARY KEY, title TEXT, description TEXT, "
               "area TEXT, size TEXT, priority INTEGER, status TEXT, source TEXT, attempts INTEGER, "
               "last_round_id TEXT, created_at INTEGER, updated_at INTEGER)")
    db.commit()
    db.close()
    store = AutonomyTaskStore(path)
    with store._connect() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(autonomy_tasks)")}
    assert "escalated" in columns
