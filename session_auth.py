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
    if token is None:
        return False
    exp = tokens.get(token)
    if exp is None:
        return False
    now_ts = time.time() if now is None else now
    return now_ts <= exp


def prune_expired_tokens(tokens: dict[str, float], now: float | None = None) -> int:
    now_ts = time.time() if now is None else now
    expired = [token for token, exp in tokens.items() if exp < now_ts]
    for token in expired:
        tokens.pop(token, None)
    return len(expired)



def enforce_token_capacity(tokens: dict[str, float], max_active: int) -> int:
    if max_active < 1:
        removed = len(tokens)
        tokens.clear()
        return removed

    overflow = len(tokens) - max_active
    if overflow <= 0:
        return 0

    # Deterministic eviction: remove earliest-expiring tokens first, then token id.
    ordered = sorted(tokens.items(), key=lambda item: (item[1], item[0]))
    for token, _ in ordered[:overflow]:
        tokens.pop(token, None)
    return overflow
