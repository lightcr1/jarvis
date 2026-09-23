"""Public repository research must be strictly scoped and read-only."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router
from jarvis.github_gateway import GithubGatewayError, canonical_repo, validate_agent_branch, validate_branch_file


@pytest.mark.parametrize("owner,repo", [
    ("https://evil.invalid", "repo"), ("..", "repo"),
    ("owner", ".."), ("owner", "repo/name"), ("owner", "repo?x=1"),
])
def test_reject_unsafe_repository_names(owner, repo):
    with pytest.raises(GithubGatewayError):
        canonical_repo(owner, repo)


def test_normalize_github_names():
    assert canonical_repo("Owner", "My.Repo") == "owner/my.repo"


def test_agent_branch_validator():
    validate_agent_branch("agent/docs")
    for branch in ("main", "dev", "agent/../main", "/agent/x"):
        with pytest.raises(GithubGatewayError): validate_agent_branch(branch)


def test_branch_file_validator_blocks_protected_paths_and_non_agent_branches():
    validate_branch_file("docs/guide.md", "agent/docs", "text", "Update docs")
    for path, branch in (("AGENTS.md", "agent/x"), (".github/workflows/x.yml", "agent/x"),
                         ("deploy/app.yml", "agent/x"), ("docs/x", "main"), ("../x", "agent/x")):
        with pytest.raises(GithubGatewayError):
            validate_branch_file(path, branch, "text", "Update")


def test_agent_read_requires_exact_owner_grant_before_network(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    app = FastAPI()
    app.include_router(build_agent_grants_router({
        "agent_grant_store": store,
        "get_identity_session": lambda _: None,
        "normalize_role": lambda role: role,
        "agent_request_token": "request-only", "github_write_token": "server-token",
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

    branches = []
    monkeypatch.setattr("jarvis.api_agent_grants.create_agent_branch", lambda owner, repo, **kwargs: branches.append((owner, repo, kwargs)) or {"sha": "base"})
    branch_url = "/agent/repositories/Owner/Project/branches"
    assert client.post(branch_url, headers=agent, json={"branch": "agent/docs", "base": "dev"}).status_code == 403
    branch_project = store.request_project(kind="other_project", target="owner/project", title="Branch",
                                           operations=["create_branch"], duration_seconds=3600)
    store.decide_project(branch_project["id"], actor="owner", approve=True)
    assert client.post(branch_url, headers=agent, json={"branch": "agent/docs", "base": "dev"}).status_code == 200
    assert branches[0][2]["token"] == "server-token"

    writes = []
    monkeypatch.setattr("jarvis.api_agent_grants.write_branch_file", lambda owner, repo, **kwargs: writes.append((owner, repo, kwargs)) or {"commit": "abc"})
    file_url = "/agent/repositories/Owner/Project/files"
    file_payload = {"path": "docs/readme.md", "branch": "agent/docs", "content": "new", "message": "Update docs"}
    assert client.put(file_url, headers=agent, json=file_payload).status_code == 403
    project = store.request_project(kind="other_project", target="owner/project", title="Docs",
                                    operations=["write_branch_file"], duration_seconds=3600)
    store.decide_project(project["id"], actor="owner", approve=True)
    assert client.put(file_url, headers=agent, json=file_payload).status_code == 200
    assert writes[0][2]["token"] == "server-token"

    store.revoke(request["id"], actor="owner")
    assert client.get(url, headers=agent).status_code == 403
    assert calls == [("Owner", "Project")]
