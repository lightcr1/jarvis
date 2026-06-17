"""Tests for ByokKeyStore (Phase 2). Uses real in-memory stores with temp paths."""
import json
import pytest
import tempfile
import os
from pathlib import Path


def _store_with_key(tmp_path, monkeypatch):
    from jarvis.secret_crypto import generate_master_key
    key = generate_master_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    monkeypatch.setenv("JARVIS_BYOK_STORE_PATH", str(tmp_path / "byok_keys.json"))
    from jarvis.byok_store import ByokKeyStore
    return ByokKeyStore()


def _store_no_key(tmp_path, monkeypatch):
    monkeypatch.delenv("JARVIS_SECRET_KEY", raising=False)
    monkeypatch.setenv("JARVIS_BYOK_STORE_PATH", str(tmp_path / "byok_keys.json"))
    from jarvis.byok_store import ByokKeyStore
    return ByokKeyStore()


def test_set_key_returns_masked_only(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    result = store.set_key("usr-1", "openai", "sk-proj-abc123xyz987abcd")
    assert result["provider"] == "openai"
    assert "masked" in result
    assert "sk-proj-abc123xyz987abcd" not in str(result)
    assert "sk-" in result["masked"]  # starts with prefix
    assert "..." in result["masked"]  # has ellipsis


def test_set_and_list_masked(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_key("usr-1", "openai", "sk-openai-abc123xyz987")
    store.set_key("usr-1", "anthropic", "sk-ant-abc123xyz987abc")
    keys = store.list_masked("usr-1")
    providers = {k["provider"] for k in keys}
    assert providers == {"openai", "anthropic"}
    # Verify no raw keys leaked
    for k in keys:
        assert "sk-openai-abc123xyz987" not in str(k)
        assert "sk-ant-abc123xyz987abc" not in str(k)


def test_list_masked_never_returns_ciphertext(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_key("usr-1", "gemini", "AIza-super-secret-key-12345")
    keys = store.list_masked("usr-1")
    raw_json = json.dumps(keys)
    assert "fernet" not in raw_json
    assert "AIza-super-secret-key-12345" not in raw_json
    assert "ciphertext" not in raw_json


def test_get_decrypted_key(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    raw = "sk-openai-abc123xyz987longkey"
    store.set_key("usr-1", "openai", raw)
    recovered = store.get_decrypted_key("usr-1", "openai")
    assert recovered == raw


def test_get_decrypted_key_missing_returns_none(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    assert store.get_decrypted_key("usr-1", "openai") is None


def test_has_key(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    assert not store.has_key("usr-1", "openai")
    store.set_key("usr-1", "openai", "sk-openai-abc123xyz987")
    assert store.has_key("usr-1", "openai")


def test_delete_key(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_key("usr-1", "openai", "sk-openai-abc123xyz987")
    assert store.has_key("usr-1", "openai")
    assert store.delete_key("usr-1", "openai") is True
    assert not store.has_key("usr-1", "openai")


def test_delete_key_idempotent(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    assert store.delete_key("usr-1", "missing_provider") is False


def test_set_key_persists(tmp_path, monkeypatch):
    from jarvis.secret_crypto import generate_master_key
    key = generate_master_key()
    monkeypatch.setenv("JARVIS_SECRET_KEY", key)
    path = str(tmp_path / "byok.json")
    monkeypatch.setenv("JARVIS_BYOK_STORE_PATH", path)

    from jarvis.byok_store import ByokKeyStore
    s1 = ByokKeyStore()
    s1.set_key("usr-1", "anthropic", "sk-ant-abc123xyz987abc")

    s2 = ByokKeyStore()
    assert s2.has_key("usr-1", "anthropic")
    assert s2.get_decrypted_key("usr-1", "anthropic") == "sk-ant-abc123xyz987abc"


def test_set_key_no_master_key_raises(tmp_path, monkeypatch):
    store = _store_no_key(tmp_path, monkeypatch)
    from jarvis.secret_crypto import SecretEncryptionUnavailable
    with pytest.raises(SecretEncryptionUnavailable):
        store.set_key("usr-1", "openai", "sk-openai-abc123xyz987")


def test_unknown_provider_raises(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Unknown provider"):
        store.set_key("usr-1", "unknown_provider_xyz", "key123456789")


def test_list_masked_empty_user(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    assert store.list_masked("nonexistent_user") == []


def test_multiple_users_isolated(tmp_path, monkeypatch):
    store = _store_with_key(tmp_path, monkeypatch)
    store.set_key("usr-1", "openai", "sk-openai-abc123xyz987user1")
    store.set_key("usr-2", "openai", "sk-openai-abc123xyz987user2")
    assert store.get_decrypted_key("usr-1", "openai") != store.get_decrypted_key("usr-2", "openai")
    assert store.get_decrypted_key("usr-1", "openai") == "sk-openai-abc123xyz987user1"
    assert store.get_decrypted_key("usr-2", "openai") == "sk-openai-abc123xyz987user2"
