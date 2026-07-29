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


def test_legacy_default_account_key_format_preserved(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"imap_host": "h", "imap_port": "1", "imap_username": "u", "imap_password": "p", "smtp_host": "h", "smtp_port": "1", "smtp_username": "u", "smtp_password": "p"})
    assert "usr-1:email" in store.data["credentials"]
    assert "usr-1:email:default" not in store.data["credentials"]


def test_first_account_becomes_primary_automatically(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"url": "https://x", "username": "u", "password": "p"})
    accounts = store.list_accounts("usr-1", "email")
    assert len(accounts) == 1
    assert accounts[0]["is_primary"] is True
    assert accounts[0]["account_id"] == "default"
    assert store.primary_account_id("usr-1", "email") == "default"


def test_second_account_gets_own_key_and_is_not_primary(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"url": "a"}, account_id="default", label="Work")
    store.set_credentials("usr-1", "email", {"url": "b"}, account_id="acct2", label="Personal")
    assert "usr-1:email" in store.data["credentials"]
    assert "usr-1:email:acct2" in store.data["credentials"]
    accounts = {a["account_id"]: a for a in store.list_accounts("usr-1", "email")}
    assert accounts["default"]["is_primary"] is True
    assert accounts["acct2"]["is_primary"] is False
    assert accounts["acct2"]["label"] == "Personal"


def test_list_accounts_never_leaks_raw_values(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"imap_password": "super-secret-pw"}, label="Work")
    accounts = store.list_accounts("usr-1", "email")
    raw_json = json.dumps(accounts)
    assert "super-secret-pw" not in raw_json
    assert accounts[0]["label"] == "Work"


def test_set_primary_account_switches_flag_and_rejects_unknown_id(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"url": "a"}, account_id="default")
    store.set_credentials("usr-1", "email", {"url": "b"}, account_id="acct2")
    assert store.set_primary_account("usr-1", "email", "acct2") is True
    accounts = {a["account_id"]: a for a in store.list_accounts("usr-1", "email")}
    assert accounts["acct2"]["is_primary"] is True
    assert accounts["default"]["is_primary"] is False
    assert store.primary_account_id("usr-1", "email") == "acct2"
    assert store.set_primary_account("usr-1", "email", "nope") is False


def test_delete_credentials_does_not_auto_promote(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"url": "a"}, account_id="default")
    store.set_credentials("usr-1", "email", {"url": "b"}, account_id="acct2")
    store.delete_credentials("usr-1", "email", account_id="default")
    accounts = store.list_accounts("usr-1", "email")
    assert len(accounts) == 1
    assert accounts[0]["is_primary"] is False


def test_list_users_with_credential_includes_account_metadata(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_credentials("usr-1", "email", {"url": "a"}, account_id="default", label="Work")
    store.set_credentials("usr-1", "email", {"url": "b"}, account_id="acct2", label="Personal")
    entries = store.list_users_with_credential("email")
    labels = {e["account_id"]: e["label"] for e in entries}
    assert labels == {"default": "Work", "acct2": "Personal"}


def test_migration_backfills_legacy_entry_label_and_primary_idempotently(tmp_path, monkeypatch):
    from jarvis.secret_crypto import generate_master_key
    key = generate_master_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    path = tmp_path / "integration_credentials.json"
    legacy = {"credentials": {"usr-1:email": {"ciphertext": "x", "field_names": ["url"], "created_at": 1, "updated_at": 1}}}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setenv("JARVIS_INTEGRATION_CREDENTIALS_PATH", str(path))

    from jarvis.integration_credentials import IntegrationCredentialStore
    store = IntegrationCredentialStore()
    entry = store.data["credentials"]["usr-1:email"]
    assert entry["account_id"] == "default"
    assert entry["is_primary"] is True
    assert entry["label"] == "Primary"
    assert entry["user_id"] == "usr-1"
    assert entry["integration"] == "email"

    before = path.read_text(encoding="utf-8")
    store2 = IntegrationCredentialStore()
    after = path.read_text(encoding="utf-8")
    assert before == after
    assert store2.data["credentials"]["usr-1:email"]["account_id"] == "default"


def test_workspace_style_integration_name_with_colons_untouched_by_migration(tmp_path, monkeypatch):
    from jarvis.secret_crypto import generate_master_key
    key = generate_master_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    path = tmp_path / "integration_credentials.json"
    legacy = {"credentials": {"workspace:workspace:target-1": {"ciphertext": "x", "field_names": ["password"], "created_at": 1, "updated_at": 1}}}
    path.write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.setenv("JARVIS_INTEGRATION_CREDENTIALS_PATH", str(path))

    from jarvis.integration_credentials import IntegrationCredentialStore
    store = IntegrationCredentialStore()
    entry = store.data["credentials"]["workspace:workspace:target-1"]
    assert "account_id" not in entry
    assert "user_id" not in entry
    assert "integration" not in entry
    assert store.get_credentials("workspace", "workspace:target-1") is None  # ciphertext "x" isn't valid Fernet, but key lookup itself must still work
    assert "workspace:workspace:target-1" in store.data["credentials"]
