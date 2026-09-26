"""TOTP (RFC 6238) mit der Standardbibliothek -- 2. Faktor fuer kritische Freigaben.

Kein externes Paket noetig. Standard: SHA1, 6 Stellen, 30 s, +/-1 Fenster.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def generate_secret(length: int = 20) -> str:
    return base64.b32encode(os.urandom(length)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    padded = secret + "=" * (-len(secret) % 8)
    return base64.b32decode(padded, casefold=True)


def hotp(secret: str, counter: int, digits: int = 6, algo=hashlib.sha1) -> str:
    digest = hmac.new(_key(secret), struct.pack(">Q", counter), algo).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** digits)).zfill(digits)


def totp(secret: str, at: float | None = None, digits: int = 6, period: int = 30,
         algo=hashlib.sha1) -> str:
    moment = time.time() if at is None else at
    return hotp(secret, int(moment // period), digits, algo)


def verify(secret: str, code: str, at: float | None = None, window: int = 1,
           digits: int = 6, period: int = 30, algo=hashlib.sha1) -> bool:
    return matching_counter(secret, code, at, window, digits, period, algo) is not None


def matching_counter(secret: str, code: str, at: float | None = None, window: int = 1,
                     digits: int = 6, period: int = 30, algo=hashlib.sha1) -> int | None:
    """Return the matched time step so a store can atomically reject replay."""
    candidate = str(code or "").strip().replace(" ", "")
    if not candidate.isdigit() or len(candidate) != digits or not secret:
        return None
    moment = time.time() if at is None else at
    counter = int(moment // period)
    for step in range(window, -window - 1, -1):
        if counter + step >= 0 and hmac.compare_digest(hotp(secret, counter + step, digits, algo), candidate):
            return counter + step
    return None


def provisioning_uri(secret: str, account: str, issuer: str = "Jarvis",
                     digits: int = 6, period: int = 30) -> str:
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&digits={digits}&period={period}&algorithm=SHA1")
