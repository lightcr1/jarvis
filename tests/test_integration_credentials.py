"""Tests for IntegrationCredentialStore (V2 Phase 5). Real in-memory store, temp paths."""
import json


def _store_with_key(tmp_path, monkeypatch):
    from jarvis.secret_crypto import generate_master_key
    key = generate_master_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    monkeypatch.setenv("JARVIS_INTEGRATION_CREDENTIALS_PATH", str(tmp_path / "integration_credentials.json"))
    from jarvis.integration_credentials import IntegrationCredentialStore
    return IntegrationCredentialStore()


def _store_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_SECRET_KEY", raising=False)
    monkeypatch.setenv("JARVIS_INTEGRATION_CREDENTIALS_PATH", str(tmp_path / "integration_credentials.json"))
    from jarvis.integration_credentials import IntegrationCredentialStore
    return IntegrationCredentialStore()


def test_set_and_get_credentials_round_trip(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    fields = {"url": "https://caldav.example.com/cal", "username": "alice", "password": "hunter2"}
    record = store.set_credentials("usr-1", "calendar", fields)
    assert record["integration"] == "calendar"
    assert sorted(record["field_names"]) == ["password", "url", "username"]
    recovered = store.get_credentials("usr-1", "calendar")
    assert recovered == fields


def test_multi_field_email_credentials(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    fields = {
        "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "bob", "imap_password": "pw1",
        "smtp_host": "smtp.example.com", "smtp_port": "587", "smtp_username": "bob", "smtp_password": "pw1",
    }
    store.set_credentials("usr-1", "email", fields)
    recovered = store.get_credentials("usr-1", "email")
    assert recovered == fields


def test_credentials_never_leak_raw_values_in_status(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "calendar", {"url": "https://x", "username": "u", "password": "super-secret-pw"})
    status = store.status("usr-1", "calendar")
    raw_json = json.dumps(status)
    assert "super-secret-pw" not in raw_json
    assert status["configured"] is True
    assert "password" in status["field_names"]


def test_has_credentials_and_status_when_unset(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    assert store.has_credentials("usr-1", "calendar") is False
    status = store.status("usr-1", "calendar")
    assert status == {"configured": False, "field_names": [], "updated_at": None}


def test_delete_credentials(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "calendar", {"url": "https://x", "username": "u", "password": "p"})
    assert store.delete_credentials("usr-1", "calendar") is True
    assert store.has_credentials("usr-1", "calendar") is False
    assert store.delete_credentials("usr-1", "calendar") is False


def test_users_and_integrations_isolated(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "calendar", {"url": "https://a", "username": "u1", "password": "p1"})
    store.set_credentials("usr-2", "calendar", {"url": "https://b", "username": "u2", "password": "p2"})
    store.set_credentials("usr-1", "email", {"imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p", "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p"})
    assert store.get_credentials("usr-1", "calendar")["username"] == "u1"
    assert store.get_credentials("usr-2", "calendar")["username"] == "u2"
    assert store.has_credentials("usr-1", "email") is True
    assert store.has_credentials("usr-2", "email") is False


def test_set_credentials_no_master_key_raises(tmp_path, monkeypatch):
    store = _store_no_key(tmp_path, monkeypatch)
    from jarvis.secret_crypto import SecretEncryptionUnavailable
    import pytest
    with pytest.raises(SecretEncryptionUnavailable):
        store.set_credentials("usr-1", "calendar", {"url": "https://x", "username": "u", "password": "p"})


def test_get_credentials_missing_returns_none(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    assert store.get_credentials("usr-1", "calendar") is None


def test_credentials_persist_across_instances(tmp_path, monkeypatch):
    from jarvis.secret_crypto import generate_master_key
    key = generate_master_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    path = str(tmp_path / "creds.json")
    monkeypatch.setenv("JARVIS_INTEGRATION_CREDENTIALS_PATH", path)

    from jarvis.integration_credentials import IntegrationCredentialStore
    s1 = IntegrationCredentialStore()
    s1.set_credentials("usr-1", "calendar", {"url": "https://x", "username": "u", "password": "p"})

    s2 = IntegrationCredentialStore()
    assert s2.get_credentials("usr-1", "calendar") == {"url": "https://x", "username": "u", "password": "p"}


def test_update_credentials_preserves_created_at(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    first = store.set_credentials("usr-1", "calendar", {"url": "https://x", "username": "u", "password": "p1"})
    second = store.set_credentials("usr-1", "calendar", {"url": "https://x", "username": "u", "password": "p2"})
    assert first["updated_at"] <= second["updated_at"]
    assert store.get_credentials("usr-1", "calendar")["password"] == "p2"
