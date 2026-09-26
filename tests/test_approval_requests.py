"""Tests fuer kanaaluebergreifende Freigabe-Anfragen (Abschnitt 3.3)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router


class _Broadcaster:
    def __init__(self):
        self.calls = []
    async def notify_user(self, user_id, payload):
        self.calls.append((user_id, payload))


def _client(tmp_path, broadcaster=None, totp_store=None):
    store = AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: 1000)
    deps = {
        "agent_grant_store": store,
        "get_identity_session": lambda token: {"user_id": "owner", "role": "admin"} if token == "owner" else None,
        "normalize_role": lambda role: role,
        "agent_request_token": "agent",
        "github_write_token": "", "web_search_token": "",
        "owner_user_id": "owner",
        "audit_admin_event": lambda *a: None,
    }
    if broadcaster is not None:
        deps["alert_broadcaster"] = broadcaster
    if totp_store is not None:
        deps["totp_store"] = totp_store
    app = FastAPI(); app.include_router(build_agent_grants_router(deps))
    return store, TestClient(app)


OWNER = {"X-Jarvis-Session": "owner"}
AGENT = {"X-Jarvis-Agent-Request-Token": "agent"}


def test_store_first_answer_wins(tmp_path):
    store = AgentGrantStore(tmp_path / "g.sqlite3", clock=lambda: 1000)
    req = store.request_approval(capability="service.restart", target="jarvis-web",
                                 params={"a": 1}, reason="restart", created_by="agent")
    assert req["status"] == "pending" and req["tier"] == "T2" and len(req["digest"]) == 64
    decided = store.decide_approval(req["id"], actor="owner", approve=True, channel="chat")
    assert decided["status"] == "approved" and decided["channel"] == "chat"
    # zweite Antwort (anderer Kanal) wird ignoriert
    assert store.decide_approval(req["id"], actor="owner", approve=False, channel="push") is None


def test_always_creates_standing_grant_only_for_t1_t2(tmp_path):
    store = AgentGrantStore(tmp_path / "g.sqlite3", clock=lambda: 1000)
    t2 = store.request_approval(capability="service.restart", target="jarvis*", tier="T2")
    store.decide_approval(t2["id"], actor="owner", approve=True, always=True, grant_store=store)
    assert store.match_standing_grant("service.restart", "jarvis-web") is not None
    t3 = store.request_approval(capability="email.send", target="*", tier="T3")
    store.decide_approval(t3["id"], actor="owner", approve=True, always=True, grant_store=store)
    assert store.match_standing_grant("email.send", "*") is None  # T3 nie per Freigabe


def test_api_request_decide_and_notify(tmp_path):
    broadcaster = _Broadcaster()
    store, client = _client(tmp_path, broadcaster=broadcaster)
    created = client.post("/agent/approval-requests", headers=AGENT, json={
        "capability": "service.restart", "target": "jarvis-web", "reason": "restart",
    })
    assert created.status_code == 201
    request = created.json()["request"]
    assert request["tier"] == "T2"
    assert broadcaster.calls and broadcaster.calls[0][0] == "owner"

    listed = client.get("/admin/approval-requests", headers=OWNER).json()["requests"]
    assert [r["id"] for r in listed] == [request["id"]]

    decided = client.post(f"/admin/approval-requests/{request['id']}/decide", headers=OWNER,
                          json={"approve": True, "always": True})
    assert decided.status_code == 200
    assert decided.json()["request"]["status"] == "approved"
    assert store.match_standing_grant("service.restart", "jarvis-web") is not None
    # nicht doppelt entscheidbar
    assert client.post(f"/admin/approval-requests/{request['id']}/decide", headers=OWNER,
                       json={"approve": False}).status_code == 409


def test_api_t3_tier_and_auth(tmp_path):
    _store, client = _client(tmp_path)
    assert client.post("/agent/approval-requests", json={"capability": "x"}).status_code == 401
    created = client.post("/agent/approval-requests", headers=AGENT, json={"capability": "email.send"})
    assert created.json()["request"]["tier"] == "T3"
    assert client.get("/admin/approval-requests", headers=AGENT).status_code == 401


def test_t3_approval_requires_totp_when_enabled(tmp_path):
    from jarvis import totp
    from jarvis.totp_store import TotpStore
    ts = TotpStore(tmp_path / "2fa.json")
    secret = ts.start_enrollment("owner")
    ts.activate("owner", totp.totp(secret))
    _store, client = _client(tmp_path, totp_store=ts)
    created = client.post("/agent/approval-requests", headers=AGENT, json={"capability": "email.send"})
    req_id = created.json()["request"]["id"]
    assert created.json()["request"]["tier"] == "T3"
    assert client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER,
                       json={"approve": True}).status_code == 403
    ok = client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER,
                     json={"approve": True, "totp": totp.totp(secret)})
    assert ok.status_code == 200 and ok.json()["request"]["status"] == "approved"
