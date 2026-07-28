from __future__ import annotations

import os
import tempfile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.policy_store import PolicyStore
from jarvis.policy_engine import PolicyEngine
from jarvis.playbook_store import PlaybookStore
from jarvis.playbook_executor import PlaybookExecutor
from jarvis.api_policies import build_policies_router
from jarvis.router_dependencies import LiveRef


_ADMIN_HDR = {"Authorization": "Bearer valid-admin-token"}


class _FakeAudit:
    def __init__(self):
        self.events: list[tuple] = []

    def __call__(self, event, actor_user_id, actor_role, payload=None):
        self.events.append((event, actor_user_id, actor_role, payload))


def _require_admin_access(uid, role, auth, *, allow_bootstrap=False):
    if auth == "Bearer valid-admin-token":
        return ("usr-admin", "admin")
    raise HTTPException(401, "unauthorized")


@pytest.fixture
def stores(tmp_path):
    policy_path = tmp_path / "policies.json"
    playbook_path = tmp_path / "playbooks.json"
    os.environ["JARVIS_POLICY_STORE_PATH"] = str(policy_path)
    os.environ["JARVIS_PLAYBOOK_STORE_PATH"] = str(playbook_path)
    policy_store = PolicyStore()
    playbook_store = PlaybookStore()
    yield policy_store, playbook_store
    os.environ.pop("JARVIS_POLICY_STORE_PATH", None)
    os.environ.pop("JARVIS_PLAYBOOK_STORE_PATH", None)


@pytest.fixture
def app_client(stores):
    policy_store, playbook_store = stores
    audit = _FakeAudit()

    def fake_run_cmd(cmd, timeout=8):
        if "is-active" in cmd:
            return "active"
        return ""

    policy_engine = PolicyEngine(
        policy_store=policy_store,
        run_cmd=fake_run_cmd,
        ensure_service_allowed=lambda s: None,
        emergency_stop_enabled=lambda: False,
        write_permission_check=lambda: True,
        audit_admin_event=audit,
    )
    playbook_executor = PlaybookExecutor(
        store=playbook_store,
        action_dispatch={"noop": lambda p: {"ok": True}, "restart_service": lambda p: {"ok": True, "healthy": True}},
        audit_admin_event=audit,
        emergency_stop_enabled=lambda: False,
    )

    deps = {
        "require_admin_access": _require_admin_access,
        "policy_store": LiveRef(lambda: policy_store),
        "policy_engine": LiveRef(lambda: policy_engine),
        "playbook_store": LiveRef(lambda: playbook_store),
        "playbook_executor": LiveRef(lambda: playbook_executor),
        "audit_admin_event": audit,
    }
    app = FastAPI()
    app.include_router(build_policies_router(deps))
    client = TestClient(app, raise_server_exceptions=False)
    return client, policy_store, playbook_store, audit


_POLICY_PAYLOAD = {
    "name": "nginx self-heal",
    "domain": "system",
    "condition": {"metric": "service_status", "comparator": "equals", "threshold": "failed", "duration_sec": 30},
    "action": {"type": "restart_service", "params": {"service": "nginx"}},
    "enabled": True,
    "dry_run": True,
    "cooldown_sec": 120,
}

_PLAYBOOK_PAYLOAD = {
    "name": "Nginx maintenance",
    "description": "test",
    "dry_run": True,
    "steps": [{"step_id": "s1", "description": "noop", "action": {"type": "noop", "params": {}}, "requires_confirmation": False}],
}


# ---------------------------------------------------------------------------
# Policies CRUD
# ---------------------------------------------------------------------------

def test_list_policies_requires_admin(app_client):
    client, *_ = app_client
    resp = client.get("/admin/policies")
    assert resp.status_code in (401, 403, 500)


def test_create_and_list_policy(app_client):
    client, *_ = app_client
    resp = client.post("/admin/policies", json=_POLICY_PAYLOAD, headers=_ADMIN_HDR)
    assert resp.status_code == 201
    policy_id = resp.json()["policy"]["id"]

    listed = client.get("/admin/policies", headers=_ADMIN_HDR)
    assert listed.status_code == 200
    assert any(p["id"] == policy_id for p in listed.json()["policies"])


def test_create_policy_audited(app_client):
    client, _, _, audit = app_client
    client.post("/admin/policies", json=_POLICY_PAYLOAD, headers=_ADMIN_HDR)
    assert any(e[0] == "policy.created" for e in audit.events)


def test_create_policy_invalid_condition_rejected(app_client):
    client, *_ = app_client
    bad = {**_POLICY_PAYLOAD, "condition": {"metric": "", "comparator": "above", "threshold": 1, "duration_sec": -1}}
    resp = client.post("/admin/policies", json=bad, headers=_ADMIN_HDR)
    assert resp.status_code == 422


def test_update_policy(app_client):
    client, *_ = app_client
    created = client.post("/admin/policies", json=_POLICY_PAYLOAD, headers=_ADMIN_HDR).json()["policy"]
    resp = client.patch(f"/admin/policies/{created['id']}", json={"enabled": False}, headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json()["policy"]["enabled"] is False


def test_update_missing_policy_404(app_client):
    client, *_ = app_client
    resp = client.patch("/admin/policies/nonexistent", json={"enabled": False}, headers=_ADMIN_HDR)
    assert resp.status_code == 404


def test_delete_policy(app_client):
    client, *_ = app_client
    created = client.post("/admin/policies", json=_POLICY_PAYLOAD, headers=_ADMIN_HDR).json()["policy"]
    resp = client.delete(f"/admin/policies/{created['id']}", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert client.get("/admin/policies", headers=_ADMIN_HDR).json()["policies"] == []


def test_delete_missing_policy_404(app_client):
    client, *_ = app_client
    resp = client.delete("/admin/policies/nope", headers=_ADMIN_HDR)
    assert resp.status_code == 404


def test_test_policy_endpoint(app_client):
    client, *_ = app_client
    created = client.post("/admin/policies", json=_POLICY_PAYLOAD, headers=_ADMIN_HDR).json()["policy"]
    resp = client.post(f"/admin/policies/{created['id']}/test", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "[TEST]" in body["event"]["message"]


def test_test_missing_policy_404(app_client):
    client, *_ = app_client
    resp = client.post("/admin/policies/nope/test", headers=_ADMIN_HDR)
    assert resp.status_code == 404


def test_policy_history_endpoint(app_client):
    client, *_ = app_client
    created = client.post("/admin/policies", json=_POLICY_PAYLOAD, headers=_ADMIN_HDR).json()["policy"]
    client.post(f"/admin/policies/{created['id']}/test", headers=_ADMIN_HDR)
    resp = client.get("/admin/policies/history", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert len(resp.json()["events"]) >= 1


# ---------------------------------------------------------------------------
# Playbooks CRUD + execution
# ---------------------------------------------------------------------------

def test_list_playbooks_requires_admin(app_client):
    client, *_ = app_client
    resp = client.get("/admin/playbooks")
    assert resp.status_code in (401, 403, 500)


def test_create_playbook(app_client):
    client, *_ = app_client
    resp = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR)
    assert resp.status_code == 201
    assert resp.json()["playbook"]["name"] == "Nginx maintenance"


def test_create_playbook_audited(app_client):
    client, _, _, audit = app_client
    client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR)
    assert any(e[0] == "playbook.created" for e in audit.events)


def test_update_playbook(app_client):
    client, *_ = app_client
    created = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR).json()["playbook"]
    resp = client.patch(f"/admin/playbooks/{created['id']}", json={"dry_run": False}, headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json()["playbook"]["dry_run"] is False


def test_delete_playbook(app_client):
    client, *_ = app_client
    created = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR).json()["playbook"]
    resp = client.delete(f"/admin/playbooks/{created['id']}", headers=_ADMIN_HDR)
    assert resp.status_code == 200


def test_execute_playbook_dry_run_default(app_client):
    client, *_ = app_client
    created = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR).json()["playbook"]
    resp = client.post(f"/admin/playbooks/{created['id']}/execute", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["status"] == "completed"
    assert run["steps"][0]["status"] == "would_execute"


def test_execute_playbook_live_override(app_client):
    client, *_ = app_client
    created = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR).json()["playbook"]
    resp = client.post(f"/admin/playbooks/{created['id']}/execute?dry_run=false", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    run = resp.json()["run"]
    assert run["steps"][0]["status"] == "succeeded"


def test_execute_missing_playbook_404(app_client):
    client, *_ = app_client
    resp = client.post("/admin/playbooks/nope/execute", headers=_ADMIN_HDR)
    assert resp.status_code == 404


def test_get_and_list_playbook_runs(app_client):
    client, *_ = app_client
    created = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD, headers=_ADMIN_HDR).json()["playbook"]
    run = client.post(f"/admin/playbooks/{created['id']}/execute", headers=_ADMIN_HDR).json()["run"]

    listed = client.get(f"/admin/playbooks/{created['id']}/runs", headers=_ADMIN_HDR)
    assert listed.status_code == 200
    assert len(listed.json()["runs"]) == 1

    fetched = client.get(f"/admin/playbooks/runs/{run['id']}", headers=_ADMIN_HDR)
    assert fetched.status_code == 200
    assert fetched.json()["run"]["id"] == run["id"]


def test_get_missing_run_404(app_client):
    client, *_ = app_client
    resp = client.get("/admin/playbooks/runs/nope", headers=_ADMIN_HDR)
    assert resp.status_code == 404


def test_resume_playbook_run(app_client):
    client, *_ = app_client
    gated_payload = {
        "name": "gated",
        "dry_run": False,
        "steps": [{"step_id": "s1", "action": {"type": "noop", "params": {}}, "requires_confirmation": True}],
    }
    created = client.post("/admin/playbooks", json=gated_payload, headers=_ADMIN_HDR).json()["playbook"]
    run = client.post(f"/admin/playbooks/{created['id']}/execute", headers=_ADMIN_HDR).json()["run"]
    assert run["status"] == "awaiting_confirmation"

    resumed = client.post(f"/admin/playbooks/runs/{run['id']}/resume", headers=_ADMIN_HDR)
    assert resumed.status_code == 200
    assert resumed.json()["run"]["status"] == "completed"


def test_create_requires_auth(app_client):
    client, *_ = app_client
    resp = client.post("/admin/policies", json=_POLICY_PAYLOAD)
    assert resp.status_code in (401, 403, 500)
    resp2 = client.post("/admin/playbooks", json=_PLAYBOOK_PAYLOAD)
    assert resp2.status_code in (401, 403, 500)
