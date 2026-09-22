import json

import pytest

from jarvis.agent_monitor import (
    list_owner_requests,
    list_sessions,
    decide_owner_request,
    MonitorError,
)

# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

def test_list_sessions_returns_items(monkeypatch):
    captured = {}

    def fake_oh(path, key=None):
        captured["path"] = path
        captured["key"] = key
        return {"items": [{"conversation_id": "1111", "title": "Autonomie-Runde", "status": "running"}]}

    monkeypatch.setattr("jarvis.agent_monitor._oh_request", fake_oh)
    monkeypatch.setenv("OPENHANDS_API_KEY", "sekret")

    sessions = list_sessions("sekret")
    assert len(sessions) == 1
    assert sessions[0]["conversation_id"] == "1111"
    assert captured["key"] == "sekret"


def test_list_sessions_handles_empty(monkeypatch):
    monkeypatch.setattr("jarvis.agent_monitor._oh_request", lambda *a, **k: {"items": []})
    assert list_sessions() == []


def test_list_sessions_raises_on_error(monkeypatch):
    def boom(path, key=None):
        raise MonitorError("kaputt")

    monkeypatch.setattr("jarvis.agent_monitor._oh_request", boom)
    with pytest.raises(MonitorError):
        list_sessions()


# ---------------------------------------------------------------------------
# list_owner_requests
# ---------------------------------------------------------------------------

def test_list_owner_requests_reads_issues(monkeypatch):
    fake = {
        "https://api.github.com/repos/lightcr1/jarvis/issues?state=open&labels=owner-input&per_page=50": [
            {
                "number": 42,
                "title": "Grosser Umbau vorschlagen",
                "created_at": "2026-09-22T10:00:00Z",
                "labels": [{"name": "owner-input"}],
                "html_url": "https://github.com/lightcr1/jarvis/issues/42",
            }
        ]
    }

    def fake_gh(method, url, token, payload=None):
        assert method == "GET"
        assert token == "tok-1"
        return fake[url]

    monkeypatch.setattr("jarvis.agent_monitor._gh_request", fake_gh)
    result = list_owner_requests("tok-1")
    assert result["readonly"] is False
    assert result["requests"][0]["number"] == 42
    assert result["requests"][0]["labels"] == ["owner-input"]


def test_list_owner_requests_readonly_without_token(monkeypatch):
    monkeypatch.setattr("jarvis.agent_monitor._gh_request", lambda *a, **k: [])
    result = list_owner_requests(token=None)
    assert result["readonly"] is True
    assert result["requests"] == []


def test_list_owner_requests_handles_api_error(monkeypatch):
    def boom(method, url, token, payload=None):
        raise MonitorError("GitHub API 403")

    monkeypatch.setattr("jarvis.agent_monitor._gh_request", boom)
    result = list_owner_requests("tok")
    assert result["readonly"] is True
    assert "error" in result


# ---------------------------------------------------------------------------
# decide_owner_request
# ---------------------------------------------------------------------------

def test_decide_owner_request_sets_label(monkeypatch):
    captured = {}

    def fake_gh(method, url, token, payload=None):
        captured["method"] = method
        captured["url"] = url
        captured["token"] = token
        captured["payload"] = payload
        return {}

    monkeypatch.setattr("jarvis.agent_monitor._gh_request", fake_gh)
    result = decide_owner_request(42, "approved", "tok-1")
    assert result == {"number": 42, "decision": "approved"}
    assert captured["method"] == "POST"
    assert captured["payload"] == {"labels": ["approved"]}
    assert "issues/42/labels" in captured["url"]


def test_decide_owner_request_requires_token():
    with pytest.raises(MonitorError, match="GITHUB_TOKEN"):
        decide_owner_request(1, "approved", token=None)


def test_decide_owner_request_rejects_bad_decision():
    with pytest.raises(MonitorError, match="Ungueltige Entscheidung"):
        decide_owner_request(1, "maybe", "tok")


# ---------------------------------------------------------------------------
# session_status (metadaten only)
# ---------------------------------------------------------------------------

def test_session_status_compat(monkeypatch):
    monkeypatch.setattr("jarvis.agent_monitor._oh_request", lambda *a, **k: {"items": [
        {"id": "abc", "title": "T", "state": "pending"}
    ]})
    s = list_sessions()[0]
    assert s["id"] == "abc"
