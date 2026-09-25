"""API tests for the autonomy backlog router (admin + request-only agent)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.autonomy_task_store import AutonomyTaskStore
from jarvis.api_autonomy_tasks import build_autonomy_tasks_router


def _client(tmp_path):
    store = AutonomyTaskStore(tmp_path / "tasks.sqlite3")
    app = FastAPI()
    app.include_router(build_autonomy_tasks_router({
        "autonomy_task_store": store,
        "require_admin_access": None,
        "get_identity_session": lambda token: ({"user_id": "owner", "role": "admin"}
                                               if token == "owner" else None),
        "normalize_role": lambda role: role,
        "agent_request_token": "agent-token",
        "audit_admin_event": lambda *args, **kwargs: None,
    }))
    return store, TestClient(app)


AGENT = {"X-Jarvis-Agent-Request-Token": "agent-token"}
OWNER = {"X-Jarvis-Session": "owner"}


def test_admin_create_and_agent_flow(tmp_path):
    store, client = _client(tmp_path)
    created = client.post("/admin/autonomy/tasks", headers=OWNER, json={
        "title": "Fix store bug", "area": "tasks", "size": "small", "priority": 7,
    })
    assert created.status_code == 201
    task_id = created.json()["task"]["id"]

    listing = client.get("/admin/autonomy/tasks", headers=OWNER)
    assert [t["id"] for t in listing.json()["tasks"]] == [task_id]

    nxt = client.get("/agent/tasks/next", headers=AGENT, params={"focus": "tasks"})
    assert nxt.status_code == 200
    assert nxt.json()["task"]["id"] == task_id

    claimed = client.post(f"/agent/tasks/{task_id}/claim", headers=AGENT,
                          json={"round_id": "round-1"})
    assert claimed.status_code == 200
    assert claimed.json()["task"]["status"] == "in_progress"

    reported = client.post(f"/agent/tasks/{task_id}/report", headers=AGENT, json={
        "round_id": "round-1", "outcome": "done", "summary": "Fixed",
        "branch": "agent/fix", "files_changed": ["jarvis/tasks/store.py"],
        "tests": ["tests/test_tasks.py"],
    })
    assert reported.status_code == 201
    assert reported.json()["task"]["status"] == "done"


def test_agent_proposal_requires_owner_approval(tmp_path):
    store, client = _client(tmp_path)
    proposed = client.post("/agent/tasks", headers=AGENT, json={
        "title": "Idea", "description": "Do something", "area": "autonomy", "size": "medium",
    })
    assert proposed.status_code == 201
    task_id = proposed.json()["task"]["id"]
    assert proposed.json()["task"]["status"] == "proposed"

    # Offene Arbeit bleibt verborgen, bis der Besitzer freigibt.
    assert client.get("/agent/tasks/next", headers=AGENT).json()["task"] is None

    decided = client.post(f"/admin/autonomy/tasks/{task_id}/decide", headers=OWNER,
                          json={"approve": True})
    assert decided.status_code == 200
    assert decided.json()["task"]["status"] == "open"


def test_agent_requires_token(tmp_path):
    _store, client = _client(tmp_path)
    assert client.get("/agent/tasks/next").status_code == 401
    assert client.post("/agent/tasks", json={"title": "x"}).status_code == 401


def test_admin_requires_login(tmp_path):
    _store, client = _client(tmp_path)
    assert client.get("/admin/autonomy/tasks").status_code == 401
    assert client.post("/admin/autonomy/tasks", json={"title": "x"}).status_code == 401


def test_report_for_unknown_task_is_404(tmp_path):
    _store, client = _client(tmp_path)
    response = client.post("/agent/tasks/missing/report", headers=AGENT, json={
        "outcome": "unknown", "summary": "n/a",
    })
    assert response.status_code == 404


def test_admin_patch_and_reports_listing(tmp_path):
    _store, client = _client(tmp_path)
    task = client.post("/admin/autonomy/tasks", headers=OWNER,
                       json={"title": "Patch me"}).json()["task"]
    patched = client.patch(f"/admin/autonomy/tasks/{task['id']}", headers=OWNER,
                           json={"priority": 5, "status": "blocked"})
    assert patched.json()["task"]["priority"] == 5
    assert patched.json()["task"]["status"] == "blocked"
    assert client.get("/admin/autonomy/reports", headers=OWNER).status_code == 200
