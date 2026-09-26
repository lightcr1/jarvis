"""Tests fuer TOTP-Kern und -Store (Review-Punkt 4)."""
from __future__ import annotations

from jarvis import totp
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


def test_totp_store_enroll_activate_disable(tmp_path):
    store = TotpStore(tmp_path / "2fa.json")
    assert store.enabled("u1") is False
    secret = store.start_enrollment("u1")
    assert store.enabled("u1") is False and store.get("u1")["enabled"] is False
    assert store.activate("u1", "000000") is False           # falscher Code
    assert store.activate("u1", totp.totp(secret)) is True
    assert store.enabled("u1") is True
    assert store.verify("u1", totp.totp(secret)) is True
    assert store.disable("u1", "000000") is False
    assert store.disable("u1", totp.totp(secret)) is True
    assert store.enabled("u1") is False
