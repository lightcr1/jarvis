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


def _client(tmp_path, broadcaster=None, totp_store=None, pod_control=None, pod_budget_store=None):
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
    if pod_control is not None:
        deps["pod_control"] = pod_control
    if pod_budget_store is not None:
        deps["pod_budget_store"] = pod_budget_store
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


def test_t3_approval_requires_totp_when_enabled(tmp_path, monkeypatch):
    from jarvis import totp
    from jarvis.secret_crypto import generate_master_key
    from jarvis.totp_store import TotpStore
    monkeypatch.setenv("JARVIS_SECRET_KEY", generate_master_key())
    now = [1_000_020.0]
    monkeypatch.setattr(totp.time, "time", lambda: now[0])
    ts = TotpStore(tmp_path / "2fa.json")
    secret = ts.start_enrollment("owner")
    ts.activate("owner", totp.totp(secret))
    now[0] += 30  # Enrollment consumed the previous time step.
    _store, client = _client(tmp_path, totp_store=ts)
    created = client.post("/agent/approval-requests", headers=AGENT, json={"capability": "email.send"})
    req_id = created.json()["request"]["id"]
    assert created.json()["request"]["tier"] == "T3"
    assert client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER,
                       json={"approve": True}).status_code == 403
    ok = client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER,
                     json={"approve": True, "totp": totp.totp(secret)})
    assert ok.status_code == 200 and ok.json()["request"]["status"] == "approved"


class _Totp:
    def enabled(self, user_id):
        return True
    def verify(self, user_id, code):
        return code == "123456"


class _FakePod:
    def __init__(self):
        self.starts = []
    def start(self, profile="default"):
        self.starts.append(profile)
        return {"status": "starting"}
    def status(self):
        return {"pod": {"id": "pod-1"}}


def _budget_store(tmp_path):
    from jarvis.pod_budget import PodBudgetStore
    return PodBudgetStore(tmp_path / "pod_budget.sqlite3")


def test_pod_start_approval_starts_within_budget(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "20")
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "2")
    monkeypatch.setenv("JARVIS_POD_PLANNED_HOURS", "1")
    pod = _FakePod()
    budget = _budget_store(tmp_path)
    _store, client = _client(tmp_path, pod_control=pod, totp_store=_Totp(), pod_budget_store=budget)
    # Anfrage-Parameter duerfen das Budget nicht mehr bestimmen.
    created = client.post("/agent/approval-requests", headers=AGENT,
                          json={"capability": "pod.start",
                                "params": {"estimated_chf": 999, "spent_chf": 0, "profile": "default"}})
    req_id = created.json()["request"]["id"]
    ok = client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER, json={"approve": True, "totp": "123456"})
    assert ok.status_code == 200 and pod.starts == ["default"]
    assert ok.json()["pod_budget"]["estimate_chf"] == 2.0
    assert budget.has_open_session() is True


def test_pod_start_budget_exceeded_blocks(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "5")
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "4")
    monkeypatch.setenv("JARVIS_POD_PLANNED_HOURS", "2")
    pod = _FakePod()
    budget = _budget_store(tmp_path)
    _store, client = _client(tmp_path, pod_control=pod, totp_store=_Totp(), pod_budget_store=budget)
    created = client.post("/agent/approval-requests", headers=AGENT,
                          json={"capability": "pod.start",
                                "params": {"profile": "default"}})
    req_id = created.json()["request"]["id"]
    resp = client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER,
                       json={"approve": True, "totp": "123456"})
    assert resp.status_code == 409 and pod.starts == []
    assert budget.has_open_session() is False


def test_pod_start_without_known_rate_is_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "50")
    monkeypatch.delenv("JARVIS_POD_COST_PER_HOUR_CHF", raising=False)
    pod = _FakePod()
    _store, client = _client(tmp_path, pod_control=pod, totp_store=_Totp(),
                             pod_budget_store=_budget_store(tmp_path))
    req_id = client.post("/agent/approval-requests", headers=AGENT,
                         json={"capability": "pod.start"}).json()["request"]["id"]
    resp = client.post(f"/admin/approval-requests/{req_id}/decide", headers=OWNER,
                       json={"approve": True, "totp": "123456"})
    assert resp.status_code == 409 and pod.starts == []


def test_t3_without_enrollment_cannot_be_approved_but_can_be_rejected(tmp_path):
    store, client = _client(tmp_path)
    req = store.request_approval(capability="email.send", tier="T3")
    url = f"/admin/approval-requests/{req['id']}/decide"
    assert client.post(url, headers=OWNER, json={"approve": True, "totp": "123456"}).status_code == 403
    assert store.get_approval(req["id"])["status"] == "pending"
    assert client.post(url, headers=OWNER, json={"approve": False}).status_code == 200


def test_chat_t3_is_bound_to_user_tool_and_params_and_consumed_once(tmp_path, monkeypatch):
    from jarvis.tool_registry import Tool, ToolExecutionContext, execute_tool
    from jarvis.jarvis_engine import RiskLevel
    import jarvis.tool_registry as registry
    monkeypatch.setattr(registry, "permission_decision", lambda *a, **k: {"allowed": True})
    monkeypatch.setattr(registry, "emergency_stop_enabled", lambda: False)
    store, client = _client(tmp_path, totp_store=_Totp())
    calls = []
    tool = Tool(name="send", description="Send a message", parameters={}, required_permission="email.write",
                risk=RiskLevel.WRITE, capability="email.send",
                handler=lambda ctx, args: calls.append(args) or {"data": {"route": "sent"}})
    ctx = ToolExecutionContext(user_id="u", role="admin", deps={})
    kwargs = dict(audit_log=None, membership_store=None, permission_store=None, agent_grant_store=store)
    pending = execute_tool(tool, ctx, {"body": "hello"}, confirm=True, **kwargs)
    assert pending["data"]["route"] == "tool_approval_required" and calls == []
    req_id = pending["data"]["request_id"]
    assert execute_tool(tool, ctx, {"body": "hello"}, confirm=True, **kwargs)["data"]["request_id"] == req_id
    url = f"/admin/approval-requests/{req_id}/decide"
    assert client.post(url, headers=OWNER, json={"approve": True}).status_code == 403
    assert client.post(url, headers=OWNER, json={"approve": True, "totp": "123456"}).status_code == 200
    # Changing args or the requesting user cannot reuse that approval.
    assert execute_tool(tool, ctx, {"body": "changed"}, **kwargs)["data"]["route"] == "tool_approval_required"
    other = ToolExecutionContext(user_id="other", role="admin", deps={})
    assert execute_tool(tool, other, {"body": "hello"}, **kwargs)["data"]["route"] == "tool_approval_required"
    assert calls == []
    assert execute_tool(tool, ctx, {"body": "hello"}, **kwargs)["data"]["route"] == "sent"
    assert calls == [{"body": "hello"}]
    assert store.get_approval(req_id)["status"] == "consumed"
    assert execute_tool(tool, ctx, {"body": "hello"}, confirm=True, **kwargs)["data"]["route"] == "tool_approval_required"
    assert len(calls) == 1


def test_chat_approval_claim_is_atomic(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store = AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: 1000)
    kwargs = dict(capability="email.send", tool="send", user_id="u", params={"message": "hello"})
    req = store.claim_tool_approval(**kwargs)
    store.decide_approval(req["id"], actor="owner", approve=True, channel="admin")
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: store.claim_tool_approval(**kwargs), range(8)))
    assert sum(c["status"] == "consumed" for c in claims) == 1
    assert len({c["id"] for c in claims if c["status"] == "pending"}) == 1
