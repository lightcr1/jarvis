"""
Encryption helpers for JARVIS secrets (API keys, BYOK).

Uses Fernet symmetric encryption from the `cryptography` library.
A master key MUST be set via the `JARVIS_SECRET_KEY` environment variable.
All other data (chat history, settings, etc.) is NEVER encrypted with this module.

Scheme tag: stored ciphertext is prefixed with "fernet:v1:" so future key-rotation
or algorithm changes can be detected and handled gracefully.

Key generation (run once per deployment):
    python -c "from jarvis.secret_crypto import generate_master_key; print(generate_master_key())"
"""

import base64
import os


class SecretEncryptionUnavailable(Exception):
    pass


class SecretDecryptionError(Exception):
    pass


_SCHEME = "fernet:v1:"


def get_master_key() -> bytes | None:
    raw = (os.getenv("JARVIS_SECRET_KEY") or "").strip()
    if not raw:
        return None
    try:
        key_bytes = base64.urlsafe_b64decode(raw)
        if len(key_bytes) != 32:
            return None
        return base64.urlsafe_b64encode(key_bytes)
    except Exception:
        return None


def encryption_available() -> bool:
    return get_master_key() is not None


def generate_master_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def encrypt_secret(plaintext: str) -> str:
    key = get_master_key()
    if key is None:
        raise SecretEncryptionUnavailable(
            "JARVIS_SECRET_KEY is not set or invalid — cannot encrypt secrets."
        )
    from cryptography.fernet import Fernet
    token = Fernet(key).encrypt(plaintext.encode()).decode()
    return _SCHEME + token


def decrypt_secret(stored: str) -> str:
    if not stored.startswith(_SCHEME):
        raise SecretDecryptionError(f"Unrecognised scheme tag in stored secret (expected '{_SCHEME}...')")
    key = get_master_key()
    if key is None:
        raise SecretEncryptionUnavailable(
            "JARVIS_SECRET_KEY is not set or invalid — cannot decrypt secrets. Re-enter your API keys."
        )
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(key).decrypt(stored[len(_SCHEME):].encode()).decode()
    except InvalidToken as exc:
        raise SecretDecryptionError("Decryption failed — token is invalid or key has changed.") from exc


def mask_secret(plaintext: str) -> str:
    """Return a masked representation for display (sk-...abcd style). Never call this with ciphertext."""
    if not plaintext or len(plaintext) < 8:
        return "****"
    prefix = plaintext[:3]
    suffix = plaintext[-4:]
    return f"{prefix}...{suffix}"
