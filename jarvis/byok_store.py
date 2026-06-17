import json
import os
import time
import uuid
from pathlib import Path

from .secret_crypto import (
    encrypt_secret,
    decrypt_secret,
    mask_secret,
    encryption_available,
    SecretEncryptionUnavailable,
    SecretDecryptionError,
)

ALLOWED_PROVIDERS = {"openrouter", "openai", "anthropic", "gemini", "mistral", "deepseek"}


class ByokKeyStore:
    """Per-user encrypted API key storage.

    Schema: {"keys": {user_id: {provider: {ciphertext, masked, label, created_at, updated_at}}}}

    Keys are encrypted with Fernet (JARVIS_SECRET_KEY required).
    Masked display values are stored alongside ciphertext for fast UI reads.
    Raw keys are NEVER returned by any public method.
    This store is excluded from backups (users must re-enter after restore).
    """

    def __init__(self) -> None:
        path_str = os.getenv("JARVIS_BYOK_STORE_PATH") or ""
        if path_str:
            self.path = Path(path_str)
        else:
            base = Path(os.getenv("JARVIS_USER_STORE_PATH") or "/var/lib/jarvis")
            self.path = base.parent / "byok_keys.json" if base.suffix else base / "byok_keys.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"keys": {}}

    def _load(self) -> dict:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_key(self, user_id: str, provider: str, raw_key: str) -> dict:
        if provider not in ALLOWED_PROVIDERS:
            raise ValueError(f"Unknown provider {provider!r}. Allowed: {sorted(ALLOWED_PROVIDERS)}")
        if not encryption_available():
            raise SecretEncryptionUnavailable(
                "JARVIS_SECRET_KEY is not configured — BYOK key storage is unavailable."
            )
        now = int(time.time())
        ciphertext = encrypt_secret(raw_key)
        masked = mask_secret(raw_key)
        user_keys = self.data["keys"].setdefault(user_id, {})
        created_at = user_keys.get(provider, {}).get("created_at", now)
        user_keys[provider] = {
            "ciphertext": ciphertext,
            "masked": masked,
            "label": provider,
            "created_at": created_at,
            "updated_at": now,
        }
        self._save()
        return {"provider": provider, "masked": masked, "label": provider, "created_at": created_at}

    def get_decrypted_key(self, user_id: str, provider: str) -> str | None:
        """Server-internal only. Never expose via an HTTP endpoint."""
        entry = (self.data["keys"].get(user_id) or {}).get(provider)
        if not entry:
            return None
        try:
            return decrypt_secret(entry["ciphertext"])
        except (SecretDecryptionError, SecretEncryptionUnavailable):
            return None

    def list_masked(self, user_id: str) -> list[dict]:
        user_keys = self.data["keys"].get(user_id) or {}
        return [
            {
                "provider": provider,
                "masked": entry.get("masked", "****"),
                "label": entry.get("label", provider),
                "created_at": entry.get("created_at", 0),
            }
            for provider, entry in user_keys.items()
        ]

    def delete_key(self, user_id: str, provider: str) -> bool:
        user_keys = self.data["keys"].get(user_id) or {}
        if provider not in user_keys:
            return False
        del user_keys[provider]
        if not user_keys:
            self.data["keys"].pop(user_id, None)
        else:
            self.data["keys"][user_id] = user_keys
        self._save()
        return True

    def has_key(self, user_id: str, provider: str) -> bool:
        return provider in (self.data["keys"].get(user_id) or {})

    def list_providers_for_user(self, user_id: str) -> list[str]:
        return list(self.data["keys"].get(user_id) or {})
