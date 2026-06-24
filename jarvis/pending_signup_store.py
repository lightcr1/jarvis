from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.getenv(name)
    try:
        v = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        v = default
    return max(v, minimum)


class SignupCodeError(Exception):
    pass


class SignupCodeExpired(SignupCodeError):
    pass


class SignupCodeInvalid(SignupCodeError):
    pass


class SignupCodeLocked(SignupCodeError):
    pass


class PendingSignupStore:
    MAX_ATTEMPTS: int = 5

    def __init__(self) -> None:
        user_store_path = os.getenv("JARVIS_USER_STORE_PATH")
        if user_store_path:
            self.path = Path(user_store_path).resolve().parent / "pending_signups.json"
        else:
            self.path = Path("/var/lib/jarvis/pending_signups.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _hash_code(code: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{code}".encode()).hexdigest()

    def put(self, email: str, username: str, cred: dict, code: str) -> None:
        self.prune_expired()
        key = email.strip().lower()
        ttl = _env_int("JARVIS_SIGNUP_CODE_TTL_SEC", 900, minimum=60)
        code_salt = secrets.token_hex(16)
        self.data[key] = {
            "email": key,
            "username": username,
            "cred": cred,
            "code_hash": self._hash_code(code, code_salt),
            "code_salt": code_salt,
            "attempts": 0,
            "expires_at": int(time.time()) + ttl,
            "created_at": int(time.time()),
        }
        self._save()

    def get(self, email: str) -> dict | None:
        return self.data.get(email.strip().lower())

    def verify_code(self, email: str, code: str) -> dict:
        key = email.strip().lower()
        record = self.data.get(key)
        if not record:
            raise SignupCodeInvalid("No pending signup for this email")

        if time.time() > record["expires_at"]:
            self.data.pop(key, None)
            self._save()
            raise SignupCodeExpired("Verification code has expired")

        if record["attempts"] >= self.MAX_ATTEMPTS:
            raise SignupCodeLocked("Too many attempts — please sign up again")

        expected = record["code_hash"]
        code_salt = record.get("code_salt") or "jarvis_signup_v1"
        actual = self._hash_code(code.strip(), code_salt)
        if not hmac.compare_digest(expected, actual):
            record["attempts"] += 1
            self._save()
            raise SignupCodeInvalid(f"Invalid code ({self.MAX_ATTEMPTS - record['attempts']} attempts left)")

        return record

    def delete(self, email: str) -> None:
        key = email.strip().lower()
        if key in self.data:
            self.data.pop(key)
            self._save()

    def username_pending(self, username: str) -> bool:
        normalized = (username or "").strip().lower()
        return any((r.get("username") or "").lower() == normalized for r in self.data.values())

    def email_pending(self, email: str) -> bool:
        return (email or "").strip().lower() in self.data

    def prune_expired(self) -> int:
        now = time.time()
        expired = [k for k, v in self.data.items() if v.get("expires_at", 0) < now]
        for k in expired:
            self.data.pop(k, None)
        if expired:
            self._save()
        return len(expired)

    @staticmethod
    def generate_code() -> str:
        return str(secrets.randbelow(900_000) + 100_000)
