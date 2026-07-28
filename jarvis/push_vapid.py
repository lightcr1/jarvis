from __future__ import annotations

import base64
import json
import os
from pathlib import Path

_cached_keys: dict[str, str] | None = None


def _raw_keys_from_vapid(vapid: object) -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization

    private_value = vapid.private_key.private_numbers().private_value
    priv_raw = private_value.to_bytes(32, "big")
    pub_raw = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    private_b64 = base64.urlsafe_b64encode(priv_raw).decode().rstrip("=")
    public_b64 = base64.urlsafe_b64encode(pub_raw).decode().rstrip("=")
    return private_b64, public_b64


def _generate_vapid_keys() -> tuple[str, str]:
    from py_vapid import Vapid

    vapid = Vapid()
    vapid.generate_keys()
    return _raw_keys_from_vapid(vapid)


def _keys_path() -> Path:
    configured = os.getenv("JARVIS_VAPID_KEYS_PATH")
    return Path(configured) if configured else Path("/var/lib/jarvis/vapid_keys.json")


def _load_persisted_keys(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _persist_keys(path: Path, data: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _keys_from_env(subject: str) -> dict[str, str] | None:
    public_key = (os.getenv("JARVIS_VAPID_PUBLIC_KEY") or "").strip()
    private_key = (os.getenv("JARVIS_VAPID_PRIVATE_KEY") or "").strip()
    if public_key and private_key:
        return {"public_key": public_key, "private_key": private_key, "subject": subject}
    return None


def get_vapid_keys() -> dict[str, str]:
    """Returns {public_key, private_key, subject}, all as urlsafe-base64 strings.

    Keys are read from JARVIS_VAPID_PUBLIC_KEY / JARVIS_VAPID_PRIVATE_KEY if both are
    set; otherwise a keypair is generated once and persisted to disk so it survives
    restarts (JARVIS_VAPID_KEYS_PATH, default /var/lib/jarvis/vapid_keys.json).
    """
    global _cached_keys
    if _cached_keys is not None:
        return _cached_keys

    subject = (os.getenv("JARVIS_VAPID_SUBJECT") or "mailto:admin@localhost").strip()

    from_env = _keys_from_env(subject)
    if from_env:
        _cached_keys = from_env
        return _cached_keys

    path = _keys_path()
    persisted = _load_persisted_keys(path)
    if persisted and persisted.get("public_key") and persisted.get("private_key"):
        persisted.setdefault("subject", subject)
        _cached_keys = persisted
        return _cached_keys

    private_key, public_key = _generate_vapid_keys()
    generated = {"public_key": public_key, "private_key": private_key, "subject": subject}
    _persist_keys(path, generated)
    _cached_keys = generated
    return generated


def reset_cache_for_tests() -> None:
    global _cached_keys
    _cached_keys = None
