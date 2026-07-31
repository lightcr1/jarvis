from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_admin_integrations import build_admin_integrations_router
from jarvis.home_assistant.client import HA_CREDENTIAL_INTEGRATION, HA_CREDENTIAL_OWNER, HomeAssistantClient
from jarvis.integration_credentials import IntegrationCredentialStore
from jarvis.router_dependencies import LiveRef
from jarvis.secret_crypto import generate_master_key
from jarvis.user_store import UserStore


_ADMIN_HDR = {"Authorization": "Bearer valid-admin-token"}


def _require_admin_access(uid, role, auth, *, allow_bootstrap=False):
    if auth == "Bearer valid-admin-token":
        return ("usr-admin", "admin")
    raise HTTPException(401, "unauthorized")


@pytest.fixture
def stores(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_SECRET_KEY", generate_master_key())
    monkeypatch.setenv("JARVIS_INTEGRATION_CREDENTIALS_PATH", str(tmp_path / "integration_credentials.json"))
    monkeypatch.setenv("JARVIS_USER_STORE_PATH", str(tmp_path / "users.json"))
    credential_store = IntegrationCredentialStore()
    user_store = UserStore()
    yield credential_store, user_store


@pytest.fixture
def app_client(stores):
    credential_store, user_store = stores
    ha_client = HomeAssistantClient()
    ha_client.apply_credentials("", "")
    env_credentials = {"base_url": "", "api_token": ""}
    audit_events: list[tuple] = []

    def _sync_home_assistant_credentials() -> None:
        stored = credential_store.get_credentials(HA_CREDENTIAL_OWNER, HA_CREDENTIAL_INTEGRATION)
        creds = stored or env_credentials
        ha_client.apply_credentials(creds.get("base_url", ""), creds.get("api_token", ""))

    deps = {
        "require_admin_access": _require_admin_access,
        "integration_credential_store": LiveRef(lambda: credential_store),
        "user_store": LiveRef(lambda: user_store),
        "home_assistant_client": LiveRef(lambda: ha_client),
        "sync_home_assistant_credentials": _sync_home_assistant_credentials,
        "audit_admin_event": lambda *args: audit_events.append(args),
    }
    app = FastAPI()
    app.include_router(build_admin_integrations_router(deps))
    client = TestClient(app, raise_server_exceptions=False)
    return client, credential_store, user_store, ha_client, audit_events


def test_empty_state(app_client):
    client, *_ = app_client
    resp = client.get("/admin/integrations/status", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json() == {"calendar": [], "email": []}


def test_calendar_only_credential_appears_only_in_calendar_list(app_client):
    client, credential_store, user_store, *_ = app_client
    user = user_store.create_user("alice", role="standard_user")
    credential_store.set_credentials(
        user["id"], "calendar", {"url": "https://caldav.example.com", "username": "alice", "password": "hunter2"}
    )

    resp = client.get("/admin/integrations/status", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    body = resp.json()

    assert len(body["calendar"]) == 1
    entry = body["calendar"][0]
    assert entry["user_id"] == user["id"]
    assert entry["username"] == "alice"
    assert sorted(entry["field_names"]) == ["password", "url", "username"]
    assert isinstance(entry["updated_at"], int)

    assert body["email"] == []


def test_user_with_both_calendar_and_email_appears_independently(app_client):
    client, credential_store, user_store, *_ = app_client
    user = user_store.create_user("bob", role="standard_user")
    credential_store.set_credentials(
        user["id"], "calendar", {"url": "https://caldav.example.com", "username": "bob", "password": "pw-cal"}
    )
    credential_store.set_credentials(
        user["id"],
        "email",
        {
            "imap_host": "imap.example.com",
            "imap_port": "993",
            "imap_username": "bob",
            "imap_password": "pw-email",
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "bob",
            "smtp_password": "pw-email",
        },
    )

    resp = client.get("/admin/integrations/status", headers=_ADMIN_HDR)
    body = resp.json()

    assert len(body["calendar"]) == 1
    assert body["calendar"][0]["user_id"] == user["id"]
    assert body["calendar"][0]["username"] == "bob"

    assert len(body["email"]) == 1
    assert body["email"][0]["user_id"] == user["id"]
    assert body["email"][0]["username"] == "bob"


def test_response_never_leaks_raw_or_encrypted_credential_value(app_client):
    client, credential_store, user_store, *_ = app_client
    user = user_store.create_user("carol", role="standard_user")
    secret_password = "super-secret-value-should-never-leak-123"
    credential_store.set_credentials(
        user["id"], "email",
        {
            "imap_host": "imap.example.com",
            "imap_port": "993",
            "imap_username": "carol",
            "imap_password": secret_password,
            "smtp_host": "smtp.example.com",
            "smtp_port": "587",
            "smtp_username": "carol",
            "smtp_password": secret_password,
        },
    )
    stored_ciphertext = credential_store.data["credentials"][f"{user['id']}:email"]["ciphertext"]

    resp = client.get("/admin/integrations/status", headers=_ADMIN_HDR)
    raw_body = resp.text

    assert secret_password not in raw_body
    assert stored_ciphertext not in raw_body
    body = json.loads(raw_body)
    assert body["email"][0]["field_names"] == sorted(
        ["imap_host", "imap_port", "imap_username", "imap_password", "smtp_host", "smtp_port", "smtp_username", "smtp_password"]
    )


def test_user_with_two_email_accounts_appears_as_two_entries_with_labels(app_client):
    client, credential_store, user_store, *_ = app_client
    user = user_store.create_user("dana", role="standard_user")
    credential_store.set_credentials(
        user["id"],
        "email",
        {
            "imap_host": "imap.work.example.com", "imap_port": "993", "imap_username": "dana.work",
            "imap_password": "pw-work", "smtp_host": "smtp.work.example.com", "smtp_port": "587",
            "smtp_username": "dana.work", "smtp_password": "pw-work",
        },
        account_id="default",
        label="Work",
    )
    credential_store.set_credentials(
        user["id"],
        "email",
        {
            "imap_host": "imap.personal.example.com", "imap_port": "993", "imap_username": "dana.home",
            "imap_password": "pw-home", "smtp_host": "smtp.personal.example.com", "smtp_port": "587",
            "smtp_username": "dana.home", "smtp_password": "pw-home",
        },
        account_id="acct2",
        label="Personal",
    )

    resp = client.get("/admin/integrations/status", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    body = resp.json()

    assert body["calendar"] == []
    assert len(body["email"]) == 2
    by_label = {e["label"]: e for e in body["email"]}
    assert set(by_label) == {"Work", "Personal"}
    assert by_label["Work"]["user_id"] == user["id"]
    assert by_label["Work"]["account_id"] == "default"
    assert by_label["Work"]["is_primary"] is True
    assert by_label["Personal"]["account_id"] == "acct2"
    assert by_label["Personal"]["is_primary"] is False


def test_non_admin_caller_rejected(app_client):
    client, *_ = app_client
    resp = client.get("/admin/integrations/status")
    assert resp.status_code in (401, 403, 500)


def test_ha_credentials_unconfigured_by_default(app_client):
    client, *_ = app_client
    resp = client.get("/admin/integrations/home-assistant", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"configured": False, "custom": False, "base_url": "", "token_hint": "", "updated_at": None}


def test_set_ha_credentials_applies_to_live_client_and_audits(app_client):
    client, credential_store, _, ha_client, audit_events = app_client
    resp = client.put(
        "/admin/integrations/home-assistant",
        headers=_ADMIN_HDR,
        json={"base_url": "http://homeassistant.local:8123", "api_token": "super-secret-long-lived-token"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"configured": True, "base_url": "http://homeassistant.local:8123"}

    # the live client used elsewhere in the app is updated immediately, no restart needed
    assert ha_client.base_url == "http://homeassistant.local:8123"
    assert ha_client.api_token == "super-secret-long-lived-token"

    assert audit_events and audit_events[0][0] == "admin_home_assistant_credentials_set"

    status = client.get("/admin/integrations/home-assistant", headers=_ADMIN_HDR).json()
    assert status["configured"] is True
    assert status["custom"] is True
    assert status["token_hint"] not in ("", "super-secret-long-lived-token")
    assert "super-secret-long-lived-token" not in client.get("/admin/integrations/home-assistant", headers=_ADMIN_HDR).text

    # persisted via the shared credential store, not just in-memory on the client
    stored = credential_store.get_credentials(HA_CREDENTIAL_OWNER, HA_CREDENTIAL_INTEGRATION)
    assert stored == {"base_url": "http://homeassistant.local:8123", "api_token": "super-secret-long-lived-token"}


def test_clear_ha_credentials_reverts_live_client_to_env_fallback(app_client):
    client, _, _, ha_client, audit_events = app_client
    client.put(
        "/admin/integrations/home-assistant",
        headers=_ADMIN_HDR,
        json={"base_url": "http://homeassistant.local:8123", "api_token": "super-secret-long-lived-token"},
    )
    resp = client.delete("/admin/integrations/home-assistant", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json() == {"configured": False}
    assert ha_client.base_url == ""
    assert ha_client.api_token == ""
    assert audit_events[-1][0] == "admin_home_assistant_credentials_cleared"


def test_test_connection_reports_unconfigured_without_hitting_network(app_client):
    client, *_ = app_client
    resp = client.post("/admin/integrations/home-assistant/test", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json() == {"ok": False}


def test_set_ha_credentials_requires_admin(app_client):
    client, *_ = app_client
    resp = client.put(
        "/admin/integrations/home-assistant",
        json={"base_url": "http://homeassistant.local:8123", "api_token": "super-secret-long-lived-token"},
    )
    assert resp.status_code in (401, 403, 500)


def test_set_ha_credentials_rejects_short_token(app_client):
    client, *_ = app_client
    resp = client.put(
        "/admin/integrations/home-assistant",
        headers=_ADMIN_HDR,
        json={"base_url": "http://homeassistant.local:8123", "api_token": "short"},
    )
    assert resp.status_code == 422
