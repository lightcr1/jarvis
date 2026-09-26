"""Tests fuer TOTP-Kern und -Store (Review-Punkt 4)."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from jarvis import totp
from jarvis.secret_crypto import generate_master_key, SecretEncryptionUnavailable
from jarvis.totp_store import TotpStore


def test_totp_generate_verify_window_and_uri():
    secret = totp.generate_secret()
    assert len(secret) >= 16
    code = totp.totp(secret, at=1_000_000)
    assert totp.verify(secret, code, at=1_000_000)
    assert totp.verify(secret, code, at=1_000_000 + 25)      # +/-1 Fenster
    assert not totp.verify(secret, code, at=1_000_000 + 90)  # ausserhalb
    assert not totp.verify(secret, "000000", at=1_000_000) or code == "000000"
    assert not totp.verify(secret, "abc", at=1_000_000)
    uri = totp.provisioning_uri(secret, "owner", issuer="Jarvis")
    assert uri.startswith("otpauth://totp/") and secret in uri


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setenv("JARVIS_SECRET_KEY", generate_master_key())
    now = [1_000_020.0]
    monkeypatch.setattr(totp.time, "time", lambda: now[0])
    return now


def test_totp_store_enroll_activate_disable(tmp_path, clock):
    store = TotpStore(tmp_path / "2fa.json")
    assert store.enabled("u1") is False
    secret = store.start_enrollment("u1")
    assert store.enabled("u1") is False and store.get("u1")["enabled"] is False
    assert store.verify("u1", totp.totp(secret)) is False  # not enrolled yet
    assert store.activate("u1", "invalid") is False
    assert store.activate("u1", totp.totp(secret)) is True
    assert store.enabled("u1") is True
    assert store.verify("u1", totp.totp(secret)) is False  # activation consumed it
    clock[0] += 30
    assert store.verify("u1", totp.totp(secret)) is True
    assert store.disable("u1", totp.totp(secret)) is False  # replay
    clock[0] += 30
    assert store.disable("u1", totp.totp(secret)) is True
    assert store.enabled("u1") is False


def test_encrypted_at_rest_and_replay_survives_restart(tmp_path, clock):
    path = tmp_path / "2fa.json"
    store = TotpStore(path)
    secret = store.start_enrollment("u")
    assert secret not in path.read_text()
    assert json.loads(path.read_text())["users"]["u"]["secret"].startswith("fernet:v1:")
    assert path.stat().st_mode & 0o777 == 0o600
    assert "secret" not in store.get("u")
    assert store.activate("u", totp.totp(secret))
    clock[0] += 30
    code = totp.totp(secret)
    assert store.verify("u", code)
    assert not TotpStore(path).verify("u", code)


def test_only_one_concurrent_verifier_consumes_step(tmp_path, clock):
    path = tmp_path / "2fa.json"
    store = TotpStore(path)
    secret = store.start_enrollment("u")
    assert store.activate("u", totp.totp(secret))
    clock[0] += 30
    stores = [TotpStore(path) for _ in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda s: s.verify("u", totp.totp(secret)), stores))
    assert sum(results) == 1


def test_migrate_plaintext_and_preserve_enrollment(tmp_path, clock):
    path = tmp_path / "2fa.json"
    secret = totp.generate_secret()
    path.write_text(json.dumps({"users": {"u": {"secret": secret, "enabled": True}}}))
    store = TotpStore(path)
    assert secret not in path.read_text()
    assert store.enabled("u") and store.verify("u", totp.totp(secret))


def test_missing_key_cannot_disable_or_replace_active_factor(tmp_path, clock, monkeypatch):
    path = tmp_path / "2fa.json"
    store = TotpStore(path)
    secret = store.start_enrollment("u")
    assert store.activate("u", totp.totp(secret))
    with pytest.raises(ValueError, match="disable existing"):
        store.start_enrollment("u")
    monkeypatch.delenv("JARVIS_SECRET_KEY")
    assert TotpStore(path).enabled("u")
    assert not store.verify("u", totp.totp(secret))
    assert not store.disable("u", totp.totp(secret))
    with pytest.raises(SecretEncryptionUnavailable):
        store.start_enrollment("new")


def test_corrupt_store_does_not_silently_disable_2fa(tmp_path):
    path = tmp_path / "2fa.json"
    path.write_text("not json")
    with pytest.raises(ValueError):
        TotpStore(path)


def test_future_step_prevents_older_code_replay(tmp_path, clock):
    store = TotpStore(tmp_path / "2fa.json")
    secret = store.start_enrollment("u")
    assert store.activate("u", totp.totp(secret))
    clock[0] += 30
    assert store.verify("u", totp.totp(secret, at=clock[0] + 30))
    assert not store.verify("u", totp.totp(secret))
