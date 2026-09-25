"""API tests for the autonomy backlog router (admin + request-only agent)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.autonomy_task_store import AutonomyTaskStore
from jarvis.api_autonomy_tasks import build_autonomy_tasks_router


def _client(tmp_path, broadcaster=None, owner=None, marker=None):
    store = AutonomyTaskStore(tmp_path / "tasks.sqlite3")
    deps = {
        "autonomy_task_store": store,
        "require_admin_access": None,
        "get_identity_session": lambda token: ({"user_id": "owner", "role": "admin"}
                                               if token == "owner" else None),
        "normalize_role": lambda role: role,
        "agent_request_token": "agent-token",
        "audit_admin_event": lambda *args, **kwargs: None,
    }
    if broadcaster is not None:
        deps["alert_broadcaster"] = broadcaster
    if owner is not None:
        deps["owner_user_id"] = owner
    if marker is not None:
        deps["loop_rollout_marker"] = marker
    app = FastAPI()
    app.include_router(build_autonomy_tasks_router(deps))
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


def test_admin_review_and_stats(tmp_path):
    _store, client = _client(tmp_path)
    task = client.post("/admin/autonomy/tasks", headers=OWNER,
                       json={"title": "Review me", "area": "tasks"}).json()["task"]
    reviewed = client.post(f"/admin/autonomy/tasks/{task['id']}/review", headers=OWNER,
                           json={"decision": "merged"})
    assert reviewed.status_code == 200
    assert reviewed.json()["task"]["status"] == "done"
    stats = client.get("/admin/autonomy/stats", headers=OWNER)
    assert stats.status_code == 200
    assert stats.json()["areas"]["tasks"]["done"] == 1
    assert client.post(f"/admin/autonomy/tasks/{task['id']}/review", headers=AGENT,
                       json={"decision": "merged"}).status_code == 401


def test_admin_daily_report(tmp_path):
    _store, client = _client(tmp_path)
    response = client.get("/admin/autonomy/daily-report", headers=OWNER)
    assert response.status_code == 200
    assert "rounds" in response.json()


class _FakeBroadcaster:
    def __init__(self):
        self.calls = []

    async def notify_user(self, user_id, payload):
        self.calls.append((user_id, payload))


def test_owner_question_notifies_owner(tmp_path):
    broadcaster = _FakeBroadcaster()
    _store, client = _client(tmp_path, broadcaster=broadcaster, owner="owner")
    task = client.post("/admin/autonomy/tasks", headers=OWNER,
                       json={"title": "Needs input", "area": "tasks"}).json()["task"]
    client.post(f"/agent/tasks/{task['id']}/claim", headers=AGENT, json={"round_id": "r1"})
    response = client.post(f"/agent/tasks/{task['id']}/report", headers=AGENT, json={
        "round_id": "r1", "outcome": "blocked", "summary": "stuck",
        "owner_question": "Which API key?",
    })
    assert response.status_code == 201
    assert broadcaster.calls
    user_id, payload = broadcaster.calls[0]
    assert user_id == "owner"
    assert "Which API key?" in payload["message"]


def test_blocked_outcome_notifies_without_question(tmp_path):
    broadcaster = _FakeBroadcaster()
    _store, client = _client(tmp_path, broadcaster=broadcaster, owner="owner")
    task = client.post("/admin/autonomy/tasks", headers=OWNER,
                       json={"title": "Blocked"}).json()["task"]
    client.post(f"/agent/tasks/{task['id']}/claim", headers=AGENT, json={"round_id": "r1"})
    client.post(f"/agent/tasks/{task['id']}/report", headers=AGENT, json={
        "round_id": "r1", "outcome": "blocked", "summary": "blocked",
    })
    assert broadcaster.calls and "blockiert" in broadcaster.calls[0][1]["message"]


def test_admin_imports_labeled_issues_once(tmp_path, monkeypatch):
    store, client = _client(tmp_path)
    monkeypatch.setattr("jarvis.api_autonomy_tasks.list_labeled_issues", lambda *a, **k: [
        {"number": 1, "title": "Fix bug", "body": "Details"},
        {"number": 2, "title": "Add tests", "body": ""},
    ])
    first = client.post("/admin/autonomy/import-issues", headers=OWNER)
    assert first.status_code == 200
    assert first.json() == {"imported": 2, "skipped": 0, "issues": 2}
    second = client.post("/admin/autonomy/import-issues", headers=OWNER)
    assert second.json() == {"imported": 0, "skipped": 2, "issues": 2}
    tasks = store.list_tasks()
    assert all(t["source"] == "issue" for t in tasks)


def test_agent_records_round_metrics_and_admin_reads(tmp_path):
    _store, client = _client(tmp_path)
    recorded = client.post("/agent/rounds/round-1/metrics", headers=AGENT, json={
        "task_id": "t1", "gpu_seconds": 120, "prompt_tokens": 10,
        "completion_tokens": 5, "cost_estimate": 0.5, "status": "round",
    })
    assert recorded.status_code == 201
    admin = client.get("/admin/autonomy/round-metrics", headers=OWNER)
    assert admin.status_code == 200
    assert admin.json()["aggregate"]["total_tokens"] == 15
    assert client.get("/admin/autonomy/round-metrics").status_code == 401


def test_agent_token_opens_no_admin_endpoint(tmp_path):
    _store, client = _client(tmp_path)
    for path in ("/admin/autonomy/tasks", "/admin/autonomy/stats",
                 "/admin/autonomy/daily-report", "/admin/autonomy/round-metrics",
                 "/admin/autonomy/reports"):
        assert client.get(path, headers=AGENT).status_code == 401
    assert client.post("/admin/autonomy/tasks", headers=AGENT,
                       json={"title": "x"}).status_code == 401
    assert client.post("/admin/autonomy/tasks/missing/review", headers=AGENT,
                       json={"decision": "merged"}).status_code == 401


def test_loop_rollout_writes_marker_only_for_owner(tmp_path):
    marker = tmp_path / "rollout-requested"
    _store, client = _client(tmp_path, marker=str(marker))
    assert client.post("/admin/autonomy/loop-rollout", headers=AGENT).status_code == 401
    response = client.post("/admin/autonomy/loop-rollout", headers=OWNER)
    assert response.status_code == 200
    assert response.json()["requested"] is True
    assert marker.exists()


def test_loop_rollout_unconfigured_is_503(tmp_path):
    _store, client = _client(tmp_path)
    assert client.post("/admin/autonomy/loop-rollout", headers=OWNER).status_code == 503


def _client_with_history(store, history):
    deps = {
        "autonomy_task_store": store,
        "require_admin_access": None,
        "get_identity_session": lambda token: None,
        "normalize_role": lambda role: role,
        "agent_request_token": "agent-token",
        "audit_admin_event": lambda *a, **k: None,
        "owner_user_id": "owner",
        "chat_history": history,
    }
    app = FastAPI(); app.include_router(build_autonomy_tasks_router(deps))
    return TestClient(app)


class _History:
    def __init__(self):
        self.posted = []
    def append_message(self, session_id, role, text, owner_key="guest:anonymous", owner_user_id=None):
        self.posted.append((session_id, role, text))


def test_round_report_posts_into_origin_chat(tmp_path):
    store = AutonomyTaskStore(tmp_path / "t.sqlite3")
    history = _History()
    client = _client_with_history(store, history)
    task = store.create_task(title="Aus Chat", origin_session_id="sess-9")
    resp = client.post(f"/agent/tasks/{task['id']}/report",
                       headers={"X-Jarvis-Agent-Request-Token": "agent-token"},
                       json={"outcome": "done", "summary": "fertig", "next_step": "nichts"})
    assert resp.status_code == 201
    assert history.posted and history.posted[0][0] == "sess-9"
    assert "fertig" in history.posted[0][2] and history.posted[0][1] == "jarvis"


def test_round_report_without_origin_session_is_silent(tmp_path):
    store = AutonomyTaskStore(tmp_path / "t.sqlite3")
    history = _History()
    client = _client_with_history(store, history)
    task = store.create_task(title="Ohne Chat")
    resp = client.post(f"/agent/tasks/{task['id']}/report",
                       headers={"X-Jarvis-Agent-Request-Token": "agent-token"},
                       json={"outcome": "done", "summary": "x"})
    assert resp.status_code == 201 and history.posted == []


def test_weekly_metrics_endpoint(tmp_path):
    store, client = _client(tmp_path)
    store.create_task(title="A")
    resp = client.get("/admin/autonomy/metrics/weekly", headers={"X-Jarvis-Session": "owner"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["tasks"]["total"] >= 1 and "standing_grant_suggestions" in body
