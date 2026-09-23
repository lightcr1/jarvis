"""Public repository research must be strictly scoped and read-only."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router
from jarvis.github_gateway import GithubGatewayError, canonical_repo


@pytest.mark.parametrize("owner,repo", [
    ("https://evil.invalid", "repo"), ("..", "repo"),
    ("owner", ".."), ("owner", "repo/name"), ("owner", "repo?x=1"),
])
def test_reject_unsafe_repository_names(owner, repo):
    with pytest.raises(GithubGatewayError):
        canonical_repo(owner, repo)


def test_normalize_github_names():
    assert canonical_repo("Owner", "My.Repo") == "owner/my.repo"


def test_agent_read_requires_exact_owner_grant_before_network(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    app = FastAPI()
    app.include_router(build_agent_grants_router({
        "agent_grant_store": store,
        "get_identity_session": lambda _: None,
        "normalize_role": lambda role: role,
        "agent_request_token": "request-only",
        "audit_admin_event": lambda *args: None,
    }))
    calls = []

    def fake_metadata(owner, repo):
        calls.append((owner, repo))
        return {"repository": canonical_repo(owner, repo), "description": "public"}

    monkeypatch.setattr("jarvis.api_agent_grants.public_repository_metadata", fake_metadata)
    client = TestClient(app)
    url = "/agent/repositories/Owner/Project/metadata"
    agent = {"X-Jarvis-Agent-Request-Token": "request-only"}
    assert client.get(url).status_code == 401
    assert client.get(url, headers=agent).status_code == 403
    assert calls == []
    request = store.request(kind="other_project", target="owner/project",
                            operation="read_metadata", reason="Owner project research")
    assert client.get(url, headers=agent).status_code == 403
    store.decide(request["id"], actor="owner", approve=True)
    assert client.get(url, headers=agent).json()["metadata"]["repository"] == "owner/project"
    assert calls == [("Owner", "Project")]
    assert client.get("/agent/repositories/Owner/Another/metadata", headers=agent).status_code == 403
    store.revoke(request["id"], actor="owner")
    assert client.get(url, headers=agent).status_code == 403
    assert calls == [("Owner", "Project")]
