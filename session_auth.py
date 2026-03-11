from __future__ import annotations

import time


def bearer_token_from_header(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    raw = auth_header.strip()
    if not raw.lower().startswith("bearer "):
        return None
    token = raw.split(" ", 1)[1].strip()
    return token or None


def is_token_active(tokens: dict[str, float], token: str | None, now: float | None = None) -> bool:
    if not token:
        return False
    exp = tokens.get(token)
    if not exp:
        return False
    now_ts = time.time() if now is None else now
    return now_ts <= exp
