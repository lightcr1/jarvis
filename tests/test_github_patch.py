"""Tests for atomic patch submission (parse/validate/apply + API)."""
from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis import github_gateway
from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router
from jarvis.github_gateway import (
    GithubGatewayError,
    apply_unified_diff,
    parse_patch,
    submit_patch,
    validate_patch,
)

MODIFY_PATCH = (
    "diff --git a/jarvis/foo.py b/jarvis/foo.py\n"
    "--- a/jarvis/foo.py\n"
    "+++ b/jarvis/foo.py\n"
    "@@ -1 +1 @@\n"
    "-old\n"
    "+new\n"
)


def test_parse_and_apply_modify():
    files = parse_patch(MODIFY_PATCH)
    assert [f["path"] for f in files] == ["jarvis/foo.py"]
    assert apply_unified_diff("old\n", files[0]["hunks"]) == "new\n"


def test_parse_and_apply_new_file():
    patch = (
        "diff --git a/docs/new.md b/docs/new.md\n"
        "new file mode 100644\n"
        "--- /dev/null\n"
        "+++ b/docs/new.md\n"
        "@@ -0,0 +1,2 @@\n"
        "+line one\n"
        "+line two\n"
    )
    files = parse_patch(patch)
    assert files[0]["new"] is True
    assert apply_unified_diff("", files[0]["hunks"]) == "line one\nline two"


def test_validate_rejects_protected_and_denied_paths():
    protected = MODIFY_PATCH.replace("jarvis/foo.py", "AGENTS.md")
    with pytest.raises(GithubGatewayError, match="protected path"):
        validate_patch(protected, branch="agent/x")

    denied = MODIFY_PATCH.replace("jarvis/foo.py", ".env")
    with pytest.raises(GithubGatewayError, match="denied path"):
        validate_patch(denied, branch="agent/x")


def test_validate_rejects_binary_and_bad_branch():
    binary = MODIFY_PATCH + "GIT binary patch\n"
    with pytest.raises(GithubGatewayError, match="binary"):
        validate_patch(binary, branch="agent/x")
    with pytest.raises(GithubGatewayError):
        validate_patch(MODIFY_PATCH, branch="main")


def test_submit_patch_creates_one_commit(monkeypatch):
    calls: list[tuple] = []

    def fake_gh(method, url, token, payload=None):
        calls.append((method, url, payload))
        if url.endswith("/git/ref/heads/dev"):
            return {"object": {"sha": "base-sha"}}
        if url.endswith("/git/commits/base-sha"):
            return {"tree": {"sha": "base-tree"}}
        if "/contents/" in url:
            return {"content": base64.b64encode(b"old\n").decode()}
        if url.endswith("/git/blobs"):
            return {"sha": "blob-1"}
        if url.endswith("/git/trees"):
            return {"sha": "new-tree"}
        if url.endswith("/git/commits"):
            return {"sha": "commit-1"}
        if "/git/refs/heads/" in url:
            return {}
        raise AssertionError(url)

    monkeypatch.setattr(github_gateway, "_gh_json", fake_gh)
    result = submit_patch("owner", "repo", branch="agent/fix", base="dev",
                          patch_text=MODIFY_PATCH, message="Fix", token="tok")
    assert result["commit"] == "commit-1"
    assert result["commit_count"] == 1
    assert result["paths"] == ["jarvis/foo.py"]
    commit_posts = [c for c in calls if c[0] == "POST" and c[1].endswith("/git/commits")]
    ref_patches = [c for c in calls if c[0] == "PATCH" and "/git/refs/heads/" in c[1]]
    assert len(commit_posts) == 1
    assert len(ref_patches) == 1
    assert ref_patches[0][2]["force"] is False


def _client(tmp_path, monkeypatch, review_store=None):
    store = AgentGrantStore(tmp_path / "grants.sqlite3")
    deps = {
        "agent_grant_store": store,
        "get_identity_session": lambda token: {"user_id": "owner", "role": "admin"} if token == "owner" else None,
        "normalize_role": lambda role: role,
        "agent_request_token": "agent",
        "github_write_token": "server-secret",
        "owner_user_id": "owner",
        "audit_admin_event": lambda *args: None,
    }
    if review_store is not None:
        deps["patch_review_store"] = review_store
    app = FastAPI()
    app.include_router(build_agent_grants_router(deps))
    return store, TestClient(app)


def _approve_write(store):
    project = store.request_project(kind="other_project", target="owner/repo",
                                    title="Work", operations=["write"])
    store.decide_project(project["id"], actor="owner", approve=True)


def test_patch_endpoint_requires_grant_then_creates_commit(tmp_path, monkeypatch):
    store, client = _client(tmp_path, monkeypatch)
    agent = {"X-Jarvis-Agent-Request-Token": "agent"}
    body = {"branch": "agent/fix", "base": "dev", "patch": MODIFY_PATCH, "message": "Fix"}

    assert client.post("/agent/repositories/owner/repo/patches", headers=agent, json=body).status_code == 403

    _approve_write(store)
    captured = {}

    def fake_submit(owner, repo, *, branch, base, patch_text, message, token):
        captured.update(owner=owner, repo=repo, branch=branch, token=token)
        return {"repository": "owner/repo", "branch": branch, "base": base,
                "commit": "c1", "paths": ["jarvis/foo.py"], "commit_count": 1}

    monkeypatch.setattr("jarvis.api_agent_grants.submit_patch", fake_submit)
    response = client.post("/agent/repositories/owner/repo/patches", headers=agent, json=body)
    assert response.status_code == 201
    assert response.json()["result"]["commit"] == "c1"
    assert captured["token"] == "server-secret"


def test_patch_endpoint_rejects_protected_path(tmp_path, monkeypatch):
    store, client = _client(tmp_path, monkeypatch)
    _approve_write(store)
    agent = {"X-Jarvis-Agent-Request-Token": "agent"}
    body = {"branch": "agent/fix", "base": "dev",
            "patch": MODIFY_PATCH.replace("jarvis/foo.py", "AGENTS.md"), "message": "Fix"}
    # Echte Validierung (kein Mock von submit_patch) -> geschuetzter Pfad -> 403.
    assert client.post("/agent/repositories/owner/repo/patches", headers=agent, json=body).status_code == 403


from jarvis.patch_review_store import PatchReviewStore  # noqa: E402


def test_patch_submission_is_queued_for_review(tmp_path, monkeypatch):
    review = PatchReviewStore(tmp_path / "review.sqlite3")
    store, client = _client(tmp_path, monkeypatch, review_store=review)
    _approve_write(store)
    monkeypatch.setattr("jarvis.api_agent_grants.submit_patch", lambda *a, **k: {
        "repository": "owner/repo", "branch": "agent/fix", "base": "dev",
        "commit": "c1", "paths": ["jarvis/foo.py"], "commit_count": 1,
    })
    agent = {"X-Jarvis-Agent-Request-Token": "agent"}
    owner = {"X-Jarvis-Session": "owner"}
    body = {"branch": "agent/fix", "base": "dev", "patch": MODIFY_PATCH, "message": "Fix"}
    assert client.post("/agent/repositories/owner/repo/patches", headers=agent, json=body).status_code == 201

    listed = client.get("/admin/agent-patches", headers=owner).json()["patches"]
    assert len(listed) == 1 and "patch" not in listed[0]
    detail = client.get(f"/admin/agent-patches/{listed[0]['id']}", headers=owner).json()["patch"]
    assert detail["patch"] == MODIFY_PATCH


def test_patch_review_creates_pr(tmp_path, monkeypatch):
    review = PatchReviewStore(tmp_path / "review.sqlite3")
    _store, client = _client(tmp_path, monkeypatch, review_store=review)
    item = review.record(repository="owner/repo", branch="agent/fix", base="dev",
                         commit="c1", message="Fix", patch=MODIFY_PATCH, paths=["a.py"])
    calls = []
    monkeypatch.setattr("jarvis.api_agent_grants.create_pull_request",
                        lambda o, r, p, t: calls.append((o, r, p, t)) or {
                            "number": 7, "url": "u", "repository": "owner/repo"})
    owner = {"X-Jarvis-Session": "owner"}
    response = client.post(f"/admin/agent-patches/{item['id']}/decide", headers=owner,
                           json={"approve": True})
    assert response.status_code == 200
    assert response.json()["patch"]["status"] == "pr_requested"
    assert response.json()["patch"]["pr_number"] == 7
    assert calls and calls[0][3] == "server-secret"


def test_patch_review_reject(tmp_path, monkeypatch):
    review = PatchReviewStore(tmp_path / "review.sqlite3")
    _store, client = _client(tmp_path, monkeypatch, review_store=review)
    item = review.record(repository="owner/repo", branch="agent/fix", base="dev",
                         commit="c1", message="Fix", patch=MODIFY_PATCH, paths=["a.py"])
    owner = {"X-Jarvis-Session": "owner"}
    response = client.post(f"/admin/agent-patches/{item['id']}/decide", headers=owner,
                           json={"approve": False})
    assert response.status_code == 200
    assert response.json()["patch"]["status"] == "rejected"


def test_list_labeled_issues_skips_pull_requests(monkeypatch):
    monkeypatch.setattr(github_gateway, "_gh_json", lambda method, url, token, payload=None: [
        {"number": 1, "title": "Real issue", "body": "Details"},
        {"number": 2, "title": "A PR", "pull_request": {}},
    ])
    issues = github_gateway.list_labeled_issues("owner", "repo")
    assert issues == [{"number": 1, "title": "Real issue", "body": "Details"}]


def test_agent_token_opens_no_patch_admin_endpoint(tmp_path, monkeypatch):
    review = PatchReviewStore(tmp_path / "review.sqlite3")
    _store, client = _client(tmp_path, monkeypatch, review_store=review)
    agent = {"X-Jarvis-Agent-Request-Token": "agent"}
    assert client.get("/admin/agent-patches", headers=agent).status_code == 401
    assert client.get("/admin/agent-patches/missing", headers=agent).status_code == 401
    assert client.post("/admin/agent-patches/missing/decide", headers=agent,
                       json={"approve": True}).status_code == 401
    assert client.get("/admin/agent-actions", headers=agent).status_code == 401
