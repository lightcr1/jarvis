from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_admin_integrations import build_admin_integrations_router
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
    deps = {
        "require_admin_access": _require_admin_access,
        "integration_credential_store": LiveRef(lambda: credential_store),
        "user_store": LiveRef(lambda: user_store),
    }
    app = FastAPI()
    app.include_router(build_admin_integrations_router(deps))
    client = TestClient(app, raise_server_exceptions=False)
    return client, credential_store, user_store


def test_empty_state(app_client):
    client, *_ = app_client
    resp = client.get("/admin/integrations/status", headers=_ADMIN_HDR)
    assert resp.status_code == 200
    assert resp.json() == {"calendar": [], "email": []}


def test_calendar_only_credential_appears_only_in_calendar_list(app_client):
    client, credential_store, user_store = app_client
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
    client, credential_store, user_store = app_client
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
    client, credential_store, user_store = app_client
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


def test_non_admin_caller_rejected(app_client):
    client, *_ = app_client
    resp = client.get("/admin/integrations/status")
    assert resp.status_code in (401, 403, 500)
