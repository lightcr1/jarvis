"""API-Tests fuer stehende Freigaben und die Capability-Registry."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router


def _client(tmp_path):
    store = AgentGrantStore(tmp_path / "grants.sqlite3", clock=lambda: 1000)
    app = FastAPI()
    app.include_router(build_agent_grants_router({
        "agent_grant_store": store,
        "get_identity_session": lambda token: {"user_id": "owner", "role": "admin"} if token == "owner" else None,
        "normalize_role": lambda role: role,
        "agent_request_token": "agent",
        "github_write_token": "",
        "web_search_token": "",
        "owner_user_id": "owner",
        "audit_admin_event": lambda *a: None,
    }))
    return store, TestClient(app)


OWNER = {"X-Jarvis-Session": "owner"}
AGENT = {"X-Jarvis-Agent-Request-Token": "agent"}


def test_standing_grant_create_list_revoke(tmp_path):
    _store, client = _client(tmp_path)
    assert client.get("/admin/standing-grants", headers=AGENT).status_code == 401
    created = client.post("/admin/standing-grants", headers=OWNER, json={
        "capability": "service.restart", "target_pattern": "jarvis*", "tier": "T2",
    })
    assert created.status_code == 201
    grant_id = created.json()["grant"]["id"]
    assert [g["id"] for g in client.get("/admin/standing-grants", headers=OWNER).json()["grants"]] == [grant_id]
    revoked = client.post(f"/admin/standing-grants/{grant_id}/revoke", headers=OWNER)
    assert revoked.status_code == 200
    assert revoked.json()["grant"]["status"] == "revoked"
    # nicht doppelt widerrufbar
    assert client.post(f"/admin/standing-grants/{grant_id}/revoke", headers=OWNER).status_code == 409


def test_standing_grant_rejects_t3(tmp_path):
    _store, client = _client(tmp_path)
    assert client.post("/admin/standing-grants", headers=OWNER, json={
        "capability": "email.send", "tier": "T3",
    }).status_code == 422


def test_capabilities_endpoint_lists_tiers(tmp_path):
    _store, client = _client(tmp_path)
    response = client.get("/admin/capabilities", headers=OWNER)
    assert response.status_code == 200
    by_name = {c["name"]: c for c in response.json()["capabilities"]}
    assert by_name["pod.start"]["tier"] == "T3"
    assert by_name["service.restart"]["tier"] == "T2"
    assert client.get("/admin/capabilities", headers=AGENT).status_code == 401
