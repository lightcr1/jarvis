from __future__ import annotations

import os
import tempfile

import pytest

from jarvis.playbook_store import PlaybookStore


_BASE_PLAYBOOK = {
    "name": "Nginx maintenance",
    "description": "Restart nginx safely",
    "dry_run": True,
    "steps": [
        {"step_id": "s1", "description": "check", "action": {"type": "noop", "params": {}}},
        {"step_id": "s2", "description": "restart", "action": {"type": "restart_service", "params": {"service": "nginx"}}, "requires_confirmation": True},
    ],
}


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


def test_create_playbook(store):
    pb = store.create_playbook(_BASE_PLAYBOOK)
    assert pb["id"].startswith("playbook-")
    assert len(pb["steps"]) == 2
    assert pb["steps"][1]["requires_confirmation"] is True
    assert pb["dry_run"] is True


def test_create_playbook_auto_assigns_step_ids_when_missing(store):
    payload = {**_BASE_PLAYBOOK, "steps": [{"description": "no id given", "action": {"type": "noop", "params": {}}}]}
    pb = store.create_playbook(payload)
    assert pb["steps"][0]["step_id"] == "step-1"


def test_get_playbook(store):
    created = store.create_playbook(_BASE_PLAYBOOK)
    assert store.get_playbook(created["id"])["name"] == "Nginx maintenance"


def test_update_playbook(store):
    created = store.create_playbook(_BASE_PLAYBOOK)
    updated = store.update_playbook(created["id"], {"dry_run": False})
    assert updated["dry_run"] is False
    assert len(updated["steps"]) == 2  # untouched fields survive


def test_delete_playbook(store):
    created = store.create_playbook(_BASE_PLAYBOOK)
    assert store.delete_playbook(created["id"]) is True
    assert store.get_playbook(created["id"]) is None


def test_delete_missing_playbook_returns_false(store):
    assert store.delete_playbook("nope") is False


def test_start_run_creates_pending_steps(store):
    pb = store.create_playbook(_BASE_PLAYBOOK)
    run = store.start_run(pb, dry_run=False)
    assert run["id"].startswith("run-")
    assert run["status"] == "running"
    assert len(run["steps"]) == 2
    assert all(s["status"] == "pending" for s in run["steps"])


def test_update_step_persists(store):
    pb = store.create_playbook(_BASE_PLAYBOOK)
    run = store.start_run(pb, dry_run=False)
    store.update_step(run["id"], "s1", {"status": "succeeded", "output": {"ok": True}})
    fetched = store.get_run(run["id"])
    step = next(s for s in fetched["steps"] if s["step_id"] == "s1")
    assert step["status"] == "succeeded"
    assert step["output"] == {"ok": True}


def test_list_runs_filters_by_playbook(store):
    pb1 = store.create_playbook(_BASE_PLAYBOOK)
    pb2 = store.create_playbook({**_BASE_PLAYBOOK, "name": "Other"})
    store.start_run(pb1, dry_run=False)
    store.start_run(pb2, dry_run=False)
    assert len(store.list_runs(pb1["id"])) == 1
    assert len(store.list_runs()) == 2


def test_run_and_steps_persist_across_fresh_instance(store):
    pb = store.create_playbook(_BASE_PLAYBOOK)
    run = store.start_run(pb, dry_run=False)
    store.update_step(run["id"], "s1", {"status": "succeeded"})

    fresh = PlaybookStore()
    fetched = fresh.get_run(run["id"])
    assert fetched is not None
    assert fetched["steps"][0]["status"] == "succeeded"
