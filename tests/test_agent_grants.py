"""Approval requests cannot confer authority without a real owner decision."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router


def test_grant_lifecycle_exact_scope_expiry_and_revoke(tmp_path):
    now = [1000]
    store = AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: now[0])
    req = store.request(kind="other_project", target="owner/repo", operation="edit_docs",
                        reason="Documentation task", duration_seconds=60)
    assert not store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    assert store.decide(req["id"], actor="owner", approve=True)["status"] == "approved"
    assert store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    assert not store.authorize(kind="other_project", target="owner/repo2", operation="edit_docs")
    assert not store.authorize(kind="other_project", target="owner/repo", operation="deploy")
    assert store.decide(req["id"], actor="agent", approve=True) is None  # cannot decide twice
    assert store.revoke(req["id"], actor="owner")["status"] == "revoked"
    assert not store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    req = store.request(kind="workspace", target="workspace-A", operation="edit_docs",
                        reason="Owner project", duration_seconds=60)
    now[0] += 60
    assert store.decide(req["id"], actor="owner", approve=True) is None
    assert not store.authorize(kind="workspace", target="workspace-A", operation="edit_docs")


def test_reject_reserved_and_wildcard_operations(tmp_path):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    for kind, target, operation in (
        ("repository", "repo/*", "edit_docs"), ("repository", "repo", "payment"),
        ("repository", "repo", "actions.publish"), ("runpod", "repo", "edit_docs"),
    ):
        try:
            store.request(kind=kind, target=target, operation=operation, reason="test")
        except ValueError:
            pass
        else:
            raise AssertionError("invalid grant was accepted")
        assert not store.authorize(kind=kind, target=target, operation=operation)


def test_separate_owner_and_agent_auth_and_audit(tmp_path):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    events = []
    app = FastAPI()
    app.include_router(build_agent_grants_router({
        "agent_grant_store": store,
        "get_identity_session": lambda token: {"user_id": "owner", "role": "admin"} if token == "owner" else None,
        "normalize_role": lambda role: role,
        "agent_request_token": "agent-request-only",
        "audit_admin_event": lambda *args: events.append(args),
    }))
    client = TestClient(app)
    payload = {"kind": "repository", "target": "owner/repo", "operation": "edit_docs", "reason": "Fix docs"}
    assert client.post("/agent/grants/requests", json=payload).status_code == 401
    agent = {"X-Jarvis-Agent-Request-Token": "agent-request-only"}
    owner = {"X-Jarvis-Session": "owner"}
    response = client.post("/agent/grants/requests", json=payload, headers=agent)
    assert response.status_code == 201
    request_id = response.json()["request"]["id"]
    url = f"/admin/agent-grants/{request_id}/decide"
    assert client.post(url, json={"approve": True}, headers=agent).status_code == 401
    assert client.post(url, json={"approve": True}, headers=owner).status_code == 200
    assert store.authorize(kind="repository", target="owner/repo", operation="edit_docs")
    assert client.post(f"/admin/agent-grants/{request_id}/revoke", headers=owner).status_code == 200
    assert not store.authorize(kind="repository", target="owner/repo", operation="edit_docs")
    assert [event[0] for event in events] == ["agent.grant.requested", "agent.grant.decided", "agent.grant.revoked"]
