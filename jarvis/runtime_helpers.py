import os
import re
import secrets
import time

from fastapi import HTTPException


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw = os.getenv(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    if minimum is not None and value < minimum:
        return minimum
    return value


def ensure_default_admin_seeded(
    *,
    user_store,
    admin_password_store,
    audit_log,
    logger,
    username: str,
    password: str,
) -> dict | None:
    existing = user_store.list_users()
    if not existing:
        try:
            created = user_store.create_user(username, role="admin", enabled=True)
            admin_password_store.set_password(created["id"], password)
        except OSError:
            logger.warning("default admin seeding skipped because storage is not writable")
            return None
        audit_log.write(
            "admin_default_seeded",
            {"user_id": created["id"], "username": created["username"], "role": created["role"]},
        )
        return created

    default_admin = user_store.find_by_username(username)
    if (
        default_admin
        and default_admin.get("role") == "admin"
        and bool(default_admin.get("enabled", False))
        and not admin_password_store.has_password(default_admin["id"])
    ):
        try:
            admin_password_store.set_password(default_admin["id"], password)
        except OSError:
            logger.warning("default admin password seeding skipped because storage is not writable")
            return None
        audit_log.write(
            "admin_default_password_seeded",
            {"user_id": default_admin["id"], "username": default_admin["username"]},
        )
        return default_admin
    return None


def settings_env_summary(*, admin_settings_store, wakeword_enabled, wakeword_phrase, get_stt_provider) -> dict[str, object]:
    settings = admin_settings_store.get()
    ttl_value = env_int(
        "JARVIS_TOKEN_TTL_MIN",
        default=settings["usage_limits"]["token_ttl_min"],
        minimum=1,
    )
    max_active_value = env_int(
        "JARVIS_MAX_ACTIVE_TOKENS",
        default=settings["usage_limits"]["max_active_tokens"],
        minimum=1,
    )
    return {
        "usage_limits": {
            "token_ttl_min": {
                "value": ttl_value,
                "source": "env" if os.getenv("JARVIS_TOKEN_TTL_MIN") is not None else "settings",
            },
            "max_active_tokens": {
                "value": max_active_value,
                "source": "env" if os.getenv("JARVIS_MAX_ACTIVE_TOKENS") is not None else "settings",
            },
        },
        "voice": {
            "wakeword_enabled": {
                "value": wakeword_enabled(),
                "source": "env" if os.getenv("JARVIS_WAKEWORD_ENABLED") is not None else "settings",
            },
            "wakeword_phrase": {
                "value": wakeword_phrase(),
                "source": "env" if os.getenv("JARVIS_WAKEWORD_PHRASE") is not None else "settings",
            },
            "stt_provider": {
                "value": get_stt_provider(),
                "source": "env" if os.getenv("STT_PROVIDER") is not None else "settings",
            },
        },
    }


def issue_token(*, tokens, admin_settings_store, unlock_out_type, prune_expired_tokens, enforce_token_capacity) -> object:
    prune_expired_tokens(tokens)
    settings = admin_settings_store.get()
    ttl_min = env_int(
        "JARVIS_TOKEN_TTL_MIN",
        default=settings["usage_limits"]["token_ttl_min"],
        minimum=1,
    )
    token = secrets.token_urlsafe(32)
    tokens[token] = time.time() + ttl_min * 60

    max_active = env_int(
        "JARVIS_MAX_ACTIVE_TOKENS",
        default=settings["usage_limits"]["max_active_tokens"],
        minimum=1,
    )
    enforce_token_capacity(tokens, max_active)
    return unlock_out_type(token=token, expires_in_sec=ttl_min * 60)


def prune_identity_tokens(identity_tokens: dict[str, dict]) -> int:
    now = time.time()
    expired = [token for token, data in identity_tokens.items() if float(data.get("exp", 0)) < now]
    for token in expired:
        identity_tokens.pop(token, None)
    return len(expired)


def issue_identity_token(*, identity_tokens: dict[str, dict], user_id: str, role: str, normalize_role) -> dict:
    prune_identity_tokens(identity_tokens)
    ttl_min = env_int("JARVIS_IDENTITY_TOKEN_TTL_MIN", default=60 * 24 * 7, minimum=5)
    token = secrets.token_urlsafe(32)
    exp = time.time() + ttl_min * 60
    identity_tokens[token] = {"user_id": user_id, "role": normalize_role(role), "exp": exp}
    return {"session_token": token, "expires_in_sec": ttl_min * 60}


def get_identity_session(*, identity_tokens: dict[str, dict], x_jarvis_session: str | None, user_store, normalize_role) -> dict | None:
    prune_identity_tokens(identity_tokens)
    token = (x_jarvis_session or "").strip()
    if not token:
        return None
    session = identity_tokens.get(token)
    if not session:
        return None
    if time.time() > float(session.get("exp", 0)):
        identity_tokens.pop(token, None)
        return None
    user = user_store.get_user(session.get("user_id", ""))
    if not user or not bool(user.get("enabled", False)):
        identity_tokens.pop(token, None)
        return None
    return {"token": token, "user": user, "role": normalize_role(session.get("role"))}


def chat_owner_key(*, get_identity_session, x_jarvis_session: str | None, x_jarvis_guest_key: str | None) -> tuple[str, str | None]:
    session = get_identity_session(x_jarvis_session)
    if session:
        return f"user:{session['user']['id']}", session["user"]["id"]
    guest = (x_jarvis_guest_key or "").strip()
    if guest:
        return f"guest:{guest}", None
    return "guest:anonymous", None


def token_fingerprint(token: str) -> str:
    import hashlib

    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return digest[:16]


def audit_admin_event(*, audit_log, event: str, actor_user_id: str, actor_role: str, payload: dict | None = None) -> None:
    body = {"actor_user_id": actor_user_id, "actor_role": actor_role, **(payload or {})}
    audit_log.write(event, body)


def normalize_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def validate_token_fingerprint_filter(token_fingerprint: str | None) -> None:
    if token_fingerprint is None:
        return
    if not re.fullmatch(r"[0-9a-f]{16}", token_fingerprint):
        raise HTTPException(400, "token_fingerprint must be 16 lowercase hex characters")


def validate_actor_user_id_filter(actor_user_id: str | None) -> None:
    if actor_user_id is None:
        return
    if actor_user_id == "bootstrap":
        return
    if not re.fullmatch(r"usr-[0-9a-f]{12}", actor_user_id):
        raise HTTPException(400, "actor_user_id must be 'bootstrap' or match usr-[0-9a-f]{12}")


def validate_role_filter(role: str | None, *, valid_roles) -> None:
    if role is None:
        return
    if role not in valid_roles:
        raise HTTPException(400, f"role must be one of: {', '.join(sorted(valid_roles))}")


def validate_event_filter(event: str | None) -> None:
    if event is None:
        return
    if not re.fullmatch(r"[a-z0-9_]{1,64}", event):
        raise HTTPException(400, "event must match [a-z0-9_]{1,64}")


def prepare_audit_filters(
    *,
    event: str | None,
    role: str | None,
    actor_user_id: str | None,
    token_fingerprint: str | None,
    valid_roles,
) -> dict[str, str | None]:
    prepared = {
        "event": (normalize_filter(event) or "").lower() or None,
        "role": (normalize_filter(role) or "").lower() or None,
        "actor_user_id": normalize_filter(actor_user_id),
        "token_fingerprint": (normalize_filter(token_fingerprint) or "").lower() or None,
    }
    validate_event_filter(prepared["event"])
    validate_role_filter(prepared["role"], valid_roles=valid_roles)
    validate_actor_user_id_filter(prepared["actor_user_id"])
    validate_token_fingerprint_filter(prepared["token_fingerprint"])
    return prepared


def validate_audit_query(limit: int, since_ts: int | None, until_ts: int | None) -> None:
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    if since_ts is not None and since_ts < 0:
        raise HTTPException(400, "since_ts must be >= 0")
    if until_ts is not None and until_ts < 0:
        raise HTTPException(400, "until_ts must be >= 0")
    if since_ts is not None and until_ts is not None and since_ts > until_ts:
        raise HTTPException(400, "since_ts must be <= until_ts")
