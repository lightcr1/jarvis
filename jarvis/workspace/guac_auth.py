from __future__ import annotations

import base64
import hashlib
import hmac
import json

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_ZERO_IV = b"\x00" * 16
_SIGNATURE_LEN = 32  # HMAC-SHA256 digest size


class GuacamoleTokenError(ValueError):
    pass


def _load_key(secret_hex: str) -> bytes:
    cleaned = (secret_hex or "").strip()
    try:
        key = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise GuacamoleTokenError(
            "JARVIS_WORKSPACE_JSON_SECRET must be a 32-character hex string (16 bytes / 128-bit key)"
        ) from exc
    if len(key) != 16:
        raise GuacamoleTokenError(
            "JARVIS_WORKSPACE_JSON_SECRET must decode to exactly 16 bytes (128-bit AES key)"
        )
    return key


def encode_json_auth_token(secret_hex: str, payload: dict) -> str:
    """Encodes `payload` for Apache Guacamole's `guacamole-auth-json` extension.

    SOURCE / ASSUMPTIONS (flagged for live verification — see final report):
    Implements the algorithm documented at
    https://guacamole.apache.org/doc/gug/json-auth.html and demonstrated by the
    reference `encrypt-json.sh` script shipped with guacamole-auth-json
    (https://github.com/glyptodon/guacamole-auth-json/blob/master/doc/encrypt-json.sh),
    both confirmed via live fetch during implementation:

      1. Serialize `payload` to JSON (UTF-8 bytes). No specific key ordering or
         whitespace requirement is documented; compact separators are used here.
      2. Sign those bytes with HMAC-SHA256 using the 128-bit secret key
         (`json-secret-key` in guacamole.properties — same key as step 4).
      3. Prepend the 32-byte binary signature to the plaintext JSON bytes.
      4. Encrypt the result with AES-128-CBC: key = the same 128-bit secret,
         IV = 16 zero bytes, PKCS7-padded.
      5. Base64-encode the ciphertext. Callers must URL-encode this value
         before using it as the `data` query parameter on a Guacamole page URL,
         or as the `data` field in a POST to `/api/tokens`.

    ASSUMPTION NOT EXPLICITLY CONFIRMED IN PROSE DOCS: PKCS7 padding. The
    reference script invokes `openssl enc -aes-128-cbc -K ... -iv ... -nosalt -a`
    without `-nopad`, which defaults to PKCS7/PKCS5 padding — that is the basis
    for this implementation, but it was not verified against a live Guacamole
    instance during this change. See `decode_json_auth_token` below for a
    same-process round-trip test of this encode/decode pair; that test proves
    internal consistency, NOT that a real Guacamole server will accept the
    token. Verify against a running `guacamole-auth-json` deployment before
    relying on this in production.
    """
    key = _load_key(secret_hex)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(key, plaintext, hashlib.sha256).digest()
    signed = signature + plaintext
    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded = padder.update(signed) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(_ZERO_IV)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def decode_json_auth_token(secret_hex: str, token: str) -> dict:
    """Inverse of `encode_json_auth_token`, for round-trip testing of our own
    encode logic only. Guacamole performs the equivalent decode/verify
    server-side; this function is not called anywhere in the request path.
    """
    key = _load_key(secret_hex)
    try:
        ciphertext = base64.b64decode(token, validate=True)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise GuacamoleTokenError("token is not valid base64") from exc
    decryptor = Cipher(algorithms.AES(key), modes.CBC(_ZERO_IV)).decryptor()
    try:
        padded = decryptor.update(ciphertext) + decryptor.finalize()
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        signed = unpadder.update(padded) + unpadder.finalize()
    except ValueError as exc:
        raise GuacamoleTokenError("decryption failed — wrong key or corrupt token") from exc
    signature, plaintext = signed[:_SIGNATURE_LEN], signed[_SIGNATURE_LEN:]
    expected = hmac.new(key, plaintext, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise GuacamoleTokenError("HMAC signature verification failed")
    return json.loads(plaintext.decode("utf-8"))
