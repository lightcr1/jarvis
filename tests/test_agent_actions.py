from __future__ import annotations

import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router


def _app(store, monkeypatch, calls):
    monkeypatch.setattr("jarvis.api_agent_grants.create_pull_request",
                        lambda owner, repo, payload, token: calls.append((owner, repo, payload, token)) or {"number": 1})
    app = FastAPI()
    app.include_router(build_agent_grants_router({
        "agent_grant_store": store, "get_identity_session": lambda token: {"user_id": "owner", "role": "admin"} if token == "owner" else None,
        "normalize_role": lambda role: role, "agent_request_token": "agent", "github_write_token": "server-secret",
        "owner_user_id": "owner",
        "audit_admin_event": lambda *args: None,
    }))
    return TestClient(app)


def test_exact_pull_request_needs_owner_and_is_single_use(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "actions.sqlite3")
    calls = []
    client = _app(store, monkeypatch, calls)
    agent = {"X-Jarvis-Agent-Request-Token": "agent"}; owner = {"X-Jarvis-Session": "owner"}
    payload = {"repository": "owner/repo", "title": "Safe change", "body": "Tests pass", "head": "agent/safe", "base": "dev"}
    requested = client.post("/agent/actions/github-pull-request", headers=agent, json=payload)
    assert requested.status_code == 201
    action = requested.json()["action"]
    assert "server-secret" not in json.dumps(action)
    url = f"/agent/actions/{action['id']}/execute"
    assert client.post(url, headers=agent).status_code == 403
    assert client.post(f"/admin/agent-actions/{action['id']}/decide", headers=agent, json={"approve": True}).status_code == 401
    assert client.post(f"/admin/agent-actions/{action['id']}/decide", headers=owner, json={"approve": True}).status_code == 200
    assert client.post(url, headers=agent).status_code == 200
    assert calls == [("owner", "repo", {"base": "dev", "body": "Tests pass", "head": "agent/safe", "title": "Safe change"}, "server-secret")]
    assert client.post(url, headers=agent).status_code == 403
    assert len(calls) == 1


def test_email_send_is_owner_approved_single_use_and_masks_contents(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "actions.sqlite3")
    calls = []

    class _Email:
        def create_draft(self, payload, *, user_id, role):
            calls.append(("draft", payload["to"]))
            return {"draft": {"id": "d-1"}}

        def send_draft(self, draft_id, *, user_id, role, confirm):
            calls.append(("send", draft_id, confirm))
            return {"status": "sent"}

    app = FastAPI(); app.include_router(build_agent_grants_router({
        "agent_grant_store": store, "get_identity_session": lambda t: {"user_id": "owner", "role": "admin"} if t == "owner" else None,
        "normalize_role": lambda r: r, "agent_request_token": "agent", "github_write_token": "",
        "owner_user_id": "owner", "email_service": _Email(), "audit_admin_event": lambda *a: None,
    }))
    client = TestClient(app); agent = {"X-Jarvis-Agent-Request-Token": "agent"}; owner = {"X-Jarvis-Session": "owner"}
    payload = {"to": "someone@example.com", "subject": "Update", "body": "Here is the report."}
    response = client.post("/agent/actions/email-send", headers=agent, json=payload)
    assert response.status_code == 201
    action = response.json()["action"]
    assert "Here is the report" in action["payload"]  # owner reviews the full content
    url = f"/agent/actions/{action['id']}/execute"
    assert client.post(url, headers=agent).status_code == 403
    assert client.post(f"/admin/agent-actions/{action['id']}/decide", headers=owner, json={"approve": True}).status_code == 200
    assert client.post(url, headers=agent).status_code == 200
    assert calls == [("draft", "someone@example.com"), ("send", "d-1", True)]
    assert client.post(url, headers=agent).status_code == 403
    assert calls == [("draft", "someone@example.com"), ("send", "d-1", True)]
    try:
        store.request_one_time_action(kind="email_send", target="someone@example.com", payload={**payload, "to": "not-an-email"})
    except ValueError:
        pass
    else:
        raise AssertionError("invalid email payload accepted")


def test_changed_or_dangerous_pull_request_is_not_covered(tmp_path):
    store = AgentGrantStore(tmp_path / "actions.sqlite3")
    valid = {"title": "T", "body": "B", "head": "agent/x", "base": "dev"}
    item = store.request_one_time_action(kind="github_create_pr", target="owner/repo", payload=valid)
    store.decide_one_time_action(item["id"], actor="owner", approve=True)
    with store._connect() as db:  # simulate storage corruption/tampering
        db.execute("UPDATE one_time_actions SET payload=? WHERE id=?", (json.dumps({**valid, "base": "main"}), item["id"]))
    try:
        store.consume_one_time_action(item["id"])
    except ValueError as exc:
        assert "digest" in str(exc)
    else:
        raise AssertionError("tampered action consumed")
