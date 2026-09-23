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


def test_approved_project_groups_exact_safe_operations_and_is_revocable(tmp_path):
    store = AgentGrantStore(tmp_path / "projects.sqlite3", clock=lambda: 1000)
    project = store.request_project(kind="other_project", target="owner/repo", title="Documentation sprint",
                                    operations=["read_metadata", "edit_docs"], duration_seconds=3600)
    assert not store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    store.decide_project(project["id"], actor="owner", approve=True)
    assert store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    assert store.authorize(kind="other_project", target="owner/repo", operation="read_metadata")
    assert not store.authorize(kind="other_project", target="owner/repo", operation="deploy")
    assert not store.authorize(kind="other_project", target="other/repo", operation="edit_docs")
    store.revoke_project(project["id"], actor="owner")
    assert not store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    try:
        store.request_project(kind="other_project", target="owner/repo", title="Unsafe",
                              operations=["edit_docs", "payment"])
    except ValueError:
        pass
    else:
        raise AssertionError("reserved project operation accepted")


def test_research_quota_is_bounded_and_recovers_after_day(tmp_path):
    now = [1000]
    store = AgentGrantStore(tmp_path / "quota.sqlite3", clock=lambda: now[0])
    assert store.consume_research_quota("business:a", daily_limit=2)
    assert store.consume_research_quota("business:a", daily_limit=2)
    assert not store.consume_research_quota("business:a", daily_limit=2)
    assert store.consume_research_quota("business:b", daily_limit=2)
    now[0] += 24 * 3600 + 1
    assert store.consume_research_quota("business:a", daily_limit=2)


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


def test_ideas_from_both_sources_are_not_grants(tmp_path):
    store = AgentGrantStore(tmp_path / "ideas.sqlite3", clock=lambda: 1000)
    agent_idea = store.propose_idea(source="agent", kind="business", title="Research a market",
                                   summary="Assess demand", benefit="Possible demand", risks="Unknown cost",
                                   next_step="Compare sources")
    owner_idea = store.propose_idea(source="owner", kind="other_project", title="Help on my repo",
                                   summary="Evaluate the codebase", benefit="To be researched",
                                   risks="To be assessed", next_step="Plan only")
    assert [idea["id"] for idea in store.list_ideas()][:2] == [owner_idea["id"], agent_idea["id"]]
    assert not store.authorize(kind="other_project", target="owner/repo", operation="edit_docs")
    for index in range(2):
        store.propose_idea(source="agent", kind="business", title=f"Candidate {index}",
                           summary="Assess demand", benefit="Potential value", risks="Unknown",
                           next_step="Research")
    try:
        store.propose_idea(source="agent", kind="business", title="Spam",
                           summary="Assess demand", benefit="Potential value", risks="Unknown",
                           next_step="Research")
    except ValueError:
        pass
    else:
        raise AssertionError("agent spam limit bypassed")
    assert store.review_idea(agent_idea["id"], actor="owner", status="shortlisted")


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
    idea = client.post("/agent/ideas", json={
        "kind": "business", "title": "Market research", "summary": "Look for demand",
        "benefit": "Possible new income", "risks": "No validated customers yet",
        "next_step": "Research potential customers without contacting them",
    }, headers=agent)
    assert idea.status_code == 201
    idea_id = idea.json()["idea"]["id"]
    assert client.get("/agent/ideas", headers=agent).status_code == 200
    assert client.post(f"/admin/ideas/{idea_id}/review", json={"status": "shortlisted"}, headers=agent).status_code == 401
    assert client.post(f"/admin/ideas/{idea_id}/review", json={"status": "shortlisted"}, headers=owner).status_code == 200
    own_idea = client.post("/admin/ideas", json={
        "title": "My project", "summary": "Please investigate this idea",
    }, headers=owner)
    assert own_idea.status_code == 201
    assert own_idea.json()["idea"]["source"] == "owner"
    assert [event[0] for event in events] == [
        "agent.grant.requested", "agent.grant.decided", "agent.grant.revoked",
        "agent.idea.proposed", "agent.idea.reviewed", "agent.idea.owner_submitted",
    ]
