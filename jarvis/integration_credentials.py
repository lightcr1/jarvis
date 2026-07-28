import json
import os
import time
from pathlib import Path

from .secret_crypto import (
    decrypt_secret,
    encrypt_secret,
    encryption_available,
    SecretDecryptionError,
    SecretEncryptionUnavailable,
)


class IntegrationCredentialStore:
    """Per-user encrypted multi-field credential storage, shared across integrations
    that need more than one secret field (CalDAV URL/user/pass, IMAP+SMTP host/port/
    user/pass) — unlike ByokKeyStore's single-string-per-provider shape.

    Schema: {"credentials": {f"{user_id}:{integration}": {ciphertext, field_names,
    created_at, updated_at}}}

    `ciphertext` is a Fernet-encrypted JSON blob of the raw field dict. Only
    `field_names` (never values) are ever returned to a caller that isn't decrypting
    server-side. This store is excluded from /admin/backup — users must re-enter
    credentials after a restore, same as jarvis/byok_store.py.
    """

    def __init__(self) -> None:
        path_str = os.getenv("JARVIS_INTEGRATION_CREDENTIALS_PATH") or ""
        if path_str:
            self.path = Path(path_str)
        else:
            base = Path(os.getenv("JARVIS_USER_STORE_PATH") or "/var/lib/jarvis")
            self.path = base.parent / "integration_credentials.json" if base.suffix else base / "integration_credentials.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"credentials": {}}

    def _load(self) -> dict:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _key(user_id: str, integration: str) -> str:
        return f"{user_id}:{integration}"

    def set_credentials(self, user_id: str, integration: str, fields: dict[str, str]) -> dict:
        if not encryption_available():
            raise SecretEncryptionUnavailable(
                "JARVIS_SECRET_KEY is not configured — integration credential storage is unavailable."
            )
        now = int(time.time())
        ciphertext = encrypt_secret(json.dumps(fields, ensure_ascii=False))
        key = self._key(user_id, integration)
        existing = self.data["credentials"].get(key, {})
        entry = {
            "ciphertext": ciphertext,
            "field_names": sorted(fields.keys()),
            "created_at": existing.get("created_at", now),
            "updated_at": now,
        }
        self.data["credentials"][key] = entry
        self._save()
        return {"integration": integration, "field_names": entry["field_names"], "updated_at": now}

    def get_credentials(self, user_id: str, integration: str) -> dict[str, str] | None:
        """Server-internal only. Never expose raw fields via an HTTP endpoint."""
        entry = self.data["credentials"].get(self._key(user_id, integration))
        if not entry:
            return None
        try:
            return json.loads(decrypt_secret(entry["ciphertext"]))
        except (SecretDecryptionError, SecretEncryptionUnavailable, json.JSONDecodeError):
            return None

    def has_credentials(self, user_id: str, integration: str) -> bool:
        return self._key(user_id, integration) in self.data["credentials"]

    def status(self, user_id: str, integration: str) -> dict:
        entry = self.data["credentials"].get(self._key(user_id, integration))
        if not entry:
            return {"configured": False, "field_names": [], "updated_at": None}
        return {"configured": True, "field_names": entry.get("field_names", []), "updated_at": entry.get("updated_at")}

    def delete_credentials(self, user_id: str, integration: str) -> bool:
        key = self._key(user_id, integration)
        if key not in self.data["credentials"]:
            return False
        del self.data["credentials"][key]
        self._save()
        return True

    def list_users_with_credential(self, integration: str) -> list[dict]:
        suffix = f":{integration}"
        return [
            {
                "user_id": key[: -len(suffix)],
                "field_names": entry.get("field_names", []),
                "updated_at": entry.get("updated_at"),
            }
            for key, entry in self.data["credentials"].items()
            if key.endswith(suffix)
        ]
