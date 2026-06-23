import asyncio
import sys
import logging
import os
import re
import subprocess
import time as _startup_time
import uuid

JARVIS_VERSION = "1.0.0"
_START_TIME = _startup_time.monotonic()

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from jarvis.proxmox_module import (
    build_router,
    proxmox_lxc_action,
    proxmox_lxc_status,
    proxmox_vm_action,
    proxmox_vm_status,
)
from jarvis.skill_utils import (
    disk_usage,
    ensure_service_allowed,
    format_bytes,
    parse_meminfo,
    parse_ping,
    run_cmd,
    tail_lines,
)
from jarvis.audio_services import (
    strip_wakeword as audio_strip_wakeword,
    synthesize_tts as audio_synthesize_tts,
    tts_preprocess_text as audio_tts_preprocess_text,
    transcribe_gemini as audio_transcribe_gemini,
    transcribe_local as audio_transcribe_local,
    wakeword_enabled as audio_wakeword_enabled,
    wakeword_phrase as audio_wakeword_phrase,
)
from jarvis.ai_clients import (
    SYSTEM_PROMPT,
    build_context_reply,
    get_anthropic,
    get_gemini,
    get_openai,
    get_provider,
    get_whisper,
    local_ai_chat_reply,
    local_ai_stub_reply,
)
from jarvis.assistant_domain import (
    block_write_if_unauthorized as domain_block_write_if_unauthorized,
    cloud_llm_available as domain_cloud_llm_available,
    format_rag_reply as domain_format_rag_reply,
    rag_llm_answer as domain_rag_llm_answer,
    rag_needs_smart_llm as domain_rag_needs_smart_llm,
    rag_query_from_prompt as domain_rag_query_from_prompt,
    select_rag_hits as domain_select_rag_hits,
    try_skill as domain_try_skill,
)
from jarvis.runtime_helpers import (
    audit_admin_event as runtime_audit_admin_event,
    chat_owner_key as runtime_chat_owner_key,
    ensure_default_admin_seeded as runtime_ensure_default_admin_seeded,
    env_int as runtime_env_int,
    get_identity_session as runtime_get_identity_session,
    issue_identity_token as runtime_issue_identity_token,
    issue_token as runtime_issue_token,
    normalize_filter as runtime_normalize_filter,
    prepare_audit_filters as runtime_prepare_audit_filters,
    prune_identity_tokens as runtime_prune_identity_tokens,
    settings_env_summary as runtime_settings_env_summary,
    token_fingerprint as runtime_token_fingerprint,
    validate_audit_query as runtime_validate_audit_query,
)
from jarvis.authz import build_permission_context, permission_decision, resolve_effective_permissions
from jarvis.admin_access import require_admin_access as require_admin_access_guard
from jarvis.audit_log_store import AuditLogStore
from jarvis.identity import get_active_user_or_raise
from jarvis.user_store import UserStore
from jarvis.group_store import GroupStore
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import PermissionStore, KNOWN_PERMISSIONS
from jarvis.admin_password_store import AdminPasswordStore
from jarvis.admin_settings_store import AdminSettingsStore
from jarvis.user_preferences_store import UserPreferencesStore
from jarvis.byok_store import ByokKeyStore
from jarvis.usage_log_store import UsageLogStore
from jarvis.credit_store import CreditStore
from jarvis.user_limits_store import UserLimitsStore
from jarvis.pending_signup_store import PendingSignupStore
from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.api_alerts import build_alerts_router, get_alert_broadcaster
from jarvis.api_home_assistant import build_home_assistant_router
from jarvis.alert_store import AlertRulesStore
from jarvis.alert_engine import AlertEngine
from jarvis.api_memory import build_memory_router
from jarvis.api_status import build_status_router
from jarvis.api_voice import build_voice_router
from jarvis.memory_store import MemoryStore
from jarvis.api_models import UnlockOut
from jarvis.frontend_routes import frontend_router, mount_frontend_assets
from jarvis.home_assistant.client import HomeAssistantClient
from jarvis.home_assistant.service import HomeAssistantService
from jarvis.home_assistant.store import HomeAssistantStore
from jarvis.router_dependencies import build_admin_deps, build_alerts_deps, build_auth_chat_deps, build_home_assistant_deps, build_memory_deps, build_status_deps, build_voice_deps
from jarvis.jarvis_engine import (
    JarvisEngine,
    build_registry,
    SecurityPolicy,
    normalize_role,
    role_has_permission,
    emergency_stop_enabled,
    VALID_ROLES,
)
from jarvis.runtime_state import ChatHistoryStore, RagStore
from jarvis.runtime_state import JarvisStatusHub
from jarvis.session_auth import bearer_token_from_header, enforce_token_capacity, is_token_active, prune_expired_tokens
from jarvis.wakeword_engine import (
    NullWakewordEngine,
    SoftwareWakewordEngine,
    create_wakeword_engine,
)

@asynccontextmanager
async def _lifespan(application: FastAPI):  # noqa: ARG001
    global _auto_backup_task, wakeword_engine
    _WARN_IF_MISSING = ["OPENAI_API_KEY", "JARVIS_PASSPHRASE"]
    for _var in _WARN_IF_MISSING:
        if not os.getenv(_var):
            logging.warning("JARVIS startup: env var %s is not set — dependent features will fail", _var)
    if os.getenv("JARVIS_AUTO_BACKUP_DISABLED", "").strip().lower() not in {"1", "true", "yes"}:
        _auto_backup_task = asyncio.create_task(_auto_backup_loop())
    prune_expired_tokens(_tokens)
    alert_engine.start()
    wakeword_engine = create_wakeword_engine(admin_settings_store.get())
    wakeword_engine.start(asyncio.get_event_loop(), _on_wakeword_detected)
    yield
    wakeword_engine.stop()
    alert_engine.stop()
    if _auto_backup_task:
        _auto_backup_task.cancel()

app = FastAPI(title="Jarvis Backend", lifespan=_lifespan)
logger = logging.getLogger("jarvis.audio")

mount_frontend_assets(app)
app.include_router(frontend_router)


_tokens: dict[str, float] = {}  # token -> expires_epoch
_identity_tokens: dict[str, dict] = {}  # token -> {user_id, role, exp}


chat_history = ChatHistoryStore()
rag_store = RagStore()
audit_log = AuditLogStore()
user_store = UserStore()
group_store = GroupStore()
membership_store = MembershipStore()
permission_store = PermissionStore()
admin_password_store = AdminPasswordStore()
admin_settings_store = AdminSettingsStore()
user_preferences_store = UserPreferencesStore()
byok_store = ByokKeyStore()
usage_log_store = UsageLogStore()
credit_store = CreditStore()
user_limits_store = UserLimitsStore()
memory_store = MemoryStore()
pending_signup_store = PendingSignupStore()
status_hub = JarvisStatusHub()
home_assistant_store = HomeAssistantStore()
home_assistant_client = HomeAssistantClient()
alert_rules_store = AlertRulesStore()

wakeword_engine: NullWakewordEngine | SoftwareWakewordEngine = NullWakewordEngine()

DEFAULT_ADMIN_USERNAME = (os.getenv("JARVIS_DEFAULT_ADMIN_USERNAME") or "admin").strip() or "admin"
DEFAULT_ADMIN_PASSWORD = (os.getenv("JARVIS_DEFAULT_ADMIN_PASSWORD") or "admin123").strip() or "admin123"


def ensure_default_admin_seeded() -> dict | None:
    return runtime_ensure_default_admin_seeded(
        user_store=user_store,
        admin_password_store=admin_password_store,
        audit_log=audit_log,
        logger=logger,
        username=DEFAULT_ADMIN_USERNAME,
        password=DEFAULT_ADMIN_PASSWORD,
    )


ensure_default_admin_seeded()


async def _on_wakeword_detected() -> None:
    logger.debug("Wakeword detected — always-on engine callback fired")


def _apply_wakeword_settings(updated_settings: dict) -> None:
    voice = updated_settings.get("voice", {})
    new_sens = voice.get("wakeword_sensitivity")
    if new_sens is not None and hasattr(wakeword_engine, "sensitivity"):
        wakeword_engine.sensitivity = float(new_sens)  # type: ignore[union-attr]


@app.get("/version")
def version():
    return {"version": JARVIS_VERSION}


@app.get("/health")
def health():
    import time as _t
    uptime_sec = round(_t.monotonic() - _START_TIME)
    active_tokens = sum(1 for exp in _tokens.values() if exp > _t.time())
    return {
        "ok": True,
        "version": JARVIS_VERSION,
        "uptime_sec": uptime_sec,
        "active_tokens": active_tokens,
        "alert_engine": alert_engine._task is not None and not alert_engine._task.done(),
        "wakeword_engine": type(wakeword_engine).__name__,
    }


@app.get("/greeting")
def greeting(request: Request):
    """
    Unauthenticated greeting endpoint — only reachable from localhost/loopback.
    Returns a plain-text, TTS-ready salutation + briefing for startup scripts.
    """
    client_ip = (request.client.host if request.client else "") or ""
    loopback = {"127.0.0.1", "::1", "localhost"}
    if client_ip not in loopback:
        return JSONResponse(status_code=403, content={"error": "local_only"})
    from datetime import datetime as _dt
    now = _dt.now().astimezone()
    hour = now.hour
    if 5 <= hour < 12:
        salutation = "Good morning, sir."
    elif 12 <= hour < 17:
        salutation = "Good afternoon, sir."
    elif 17 <= hour < 22:
        salutation = "Good evening, sir."
    else:
        salutation = "Sir, working late again."
    time_str = now.strftime("%H:%M")
    date_str = now.strftime("%A, %d %B %Y")
    load1, _, _ = os.getloadavg()
    cores = os.cpu_count() or 1
    load_pct = load1 / cores * 100
    text = (
        f"{salutation} "
        f"It is {time_str} on {date_str}. "
        f"All systems nominal. Load {load_pct:.0f} percent of {cores} cores. "
        f"J.A.R.V.I.S. standing by."
    )
    return {"text": text, "salutation": salutation, "time": time_str, "date": date_str}


# ---------------------------
# Provider + Clients
# ---------------------------
def get_stt_provider() -> str:
    configured = (os.getenv("STT_PROVIDER") or "").lower().strip()
    if configured:
        return configured
    return admin_settings_store.get().get("voice", {}).get("stt_provider", "local")


def _env_int(name: str, default: int, minimum: int | None = None) -> int:
    return runtime_env_int(name, default, minimum)


def _get_wakeword_engine_name() -> str:
    return type(wakeword_engine).__name__


def _settings_env_summary() -> dict[str, object]:
    return runtime_settings_env_summary(
        admin_settings_store=admin_settings_store,
        wakeword_enabled=wakeword_enabled,
        wakeword_phrase=wakeword_phrase,
        get_stt_provider=get_stt_provider,
        get_wakeword_engine=_get_wakeword_engine_name,
    )


# ---------------------------
# Unlock / Token
# ---------------------------
def _issue_token() -> UnlockOut:
    return runtime_issue_token(
        tokens=_tokens,
        admin_settings_store=admin_settings_store,
        unlock_out_type=UnlockOut,
        prune_expired_tokens=prune_expired_tokens,
        enforce_token_capacity=enforce_token_capacity,
    )


def _issue_identity_token(user_id: str, role: str) -> dict:
    return runtime_issue_identity_token(
        identity_tokens=_identity_tokens,
        user_id=user_id,
        role=role,
        normalize_role=normalize_role,
    )


def _get_identity_session(x_jarvis_session: str | None) -> dict | None:
    return runtime_get_identity_session(
        identity_tokens=_identity_tokens,
        x_jarvis_session=x_jarvis_session,
        user_store=user_store,
        normalize_role=normalize_role,
    )


def require_identity_session(x_jarvis_session: str | None) -> dict:
    session = _get_identity_session(x_jarvis_session)
    if not session:
        raise HTTPException(401, "login required")
    return session


def _chat_owner_key(x_jarvis_session: str | None, x_jarvis_guest_key: str | None) -> tuple[str, str | None]:
    return runtime_chat_owner_key(
        get_identity_session=_get_identity_session,
        x_jarvis_session=x_jarvis_session,
        x_jarvis_guest_key=x_jarvis_guest_key,
    )


def _prune_identity_tokens() -> int:
    return runtime_prune_identity_tokens(_identity_tokens)


def require_token(auth: str | None):
    prune_expired_tokens(_tokens)
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    token = bearer_token_from_header(auth)
    if not is_token_active(_tokens, token):
        raise HTTPException(401, "Token expired or invalid")


app.include_router(build_router(require_token))


def require_admin_access(
    x_jarvis_user_id: str | None,
    x_jarvis_role: str | None,
    authorization: str | None,
    *,
    allow_bootstrap: bool = False,
) -> tuple[str, str]:
    return require_admin_access_guard(
        user_store,
        _tokens,
        x_jarvis_user_id,
        x_jarvis_role,
        authorization,
        allow_bootstrap=allow_bootstrap,
    )






def _token_fingerprint(token: str) -> str:
    return runtime_token_fingerprint(token)

def _audit_admin_event(event: str, actor_user_id: str, actor_role: str, payload: dict | None = None) -> None:
    runtime_audit_admin_event(
        audit_log=audit_log,
        event=event,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        payload=payload,
    )

def _normalize_filter(value: str | None) -> str | None:
    return runtime_normalize_filter(value)




def _prepare_audit_filters(
    event: str | None,
    role: str | None,
    actor_user_id: str | None,
    token_fingerprint: str | None,
) -> dict[str, str | None]:
    return runtime_prepare_audit_filters(
        event=event,
        role=role,
        actor_user_id=actor_user_id,
        token_fingerprint=token_fingerprint,
        valid_roles=VALID_ROLES,
    )

def _validate_audit_query(limit: int, since_ts: int | None, until_ts: int | None) -> None:
    runtime_validate_audit_query(limit, since_ts, until_ts)

engine = JarvisEngine(build_registry(), SecurityPolicy())
home_assistant_service = HomeAssistantService(
    store=home_assistant_store,
    client=home_assistant_client,
    user_store=user_store,
    membership_store=membership_store,
    permission_store=permission_store,
    resolve_effective_permissions=resolve_effective_permissions,
    normalize_role=normalize_role,
    audit_log=audit_log,
)

alert_engine = AlertEngine(
    rules_store=alert_rules_store,
    audit_admin_event=_audit_admin_event,
    ha_store=home_assistant_store,
    broadcast_fn=get_alert_broadcaster().broadcast,
)

# Transitional modular router activation.
# The admin router now resolves live dependencies against the current module state,
# so test suites that replace stores on jarvisappv4 keep working.
app.include_router(build_admin_router(build_admin_deps(sys.modules[__name__])))
app.include_router(build_alerts_router(build_alerts_deps(sys.modules[__name__])))
app.include_router(build_home_assistant_router(build_home_assistant_deps(sys.modules[__name__])))
app.include_router(build_memory_router(build_memory_deps(sys.modules[__name__])))
app.include_router(build_status_router(build_status_deps(sys.modules[__name__])))

# ---------------------------
# Skills (no LLM)
# ---------------------------
def wakeword_enabled() -> bool:
    return audio_wakeword_enabled(admin_settings_store.get)


def wakeword_phrase() -> str:
    return audio_wakeword_phrase(admin_settings_store.get)


def strip_wakeword(text: str) -> tuple[str, bool]:
    if isinstance(wakeword_engine, SoftwareWakewordEngine):
        return wakeword_engine.strip(text)
    return audio_strip_wakeword(text, wakeword_phrase())


def synthesize_tts(text: str, voice: str | None = None) -> tuple:
    return audio_synthesize_tts(text, logger, voice=voice or "")


def tts_preprocess_text(text: str) -> str:
    return audio_tts_preprocess_text(text)


def transcribe_local(audio_path: str) -> str:
    return audio_transcribe_local(audio_path, get_whisper)


def transcribe_gemini(audio_bytes: bytes, content_type: str | None) -> str:
    return audio_transcribe_gemini(audio_bytes, content_type, get_gemini)


def block_write_if_unauthorized(role: str, token: str | None, granted_permissions: list[str] | None = None) -> dict[str, object] | None:
    active_token = token if token and is_token_active(_tokens, token) else None
    return domain_block_write_if_unauthorized(
        role,
        active_token,
        granted_permissions=granted_permissions,
        emergency_stop_enabled=emergency_stop_enabled,
        permission_check=lambda active_role, _active_token, active_permissions: (
            role_has_permission(active_role, "actions.write.execute")
            or ((active_permissions or []) and "actions.write.execute" in set(active_permissions))
        ),
    )


def try_skill(text: str, role: str = "admin", token: str | None = None, granted_permissions: list[str] | None = None, user_prefs: dict | None = None, user_id: str | None = None) -> dict[str, object] | None:
    active_token = token if token and is_token_active(_tokens, token) else None
    return domain_try_skill(
        text,
        role=role,
        token=active_token,
        granted_permissions=granted_permissions,
        emergency_stop_enabled=emergency_stop_enabled,
        permission_check=lambda active_role, _active_token, active_permissions: (
            role_has_permission(active_role, "actions.write.execute")
            or ((active_permissions or []) and "actions.write.execute" in set(active_permissions))
        ),
        run_cmd=run_cmd,
        disk_usage=disk_usage,
        format_bytes=format_bytes,
        parse_meminfo=parse_meminfo,
        parse_ping=parse_ping,
        tail_lines=tail_lines,
        ensure_service_allowed=ensure_service_allowed,
        proxmox_vm_status=proxmox_vm_status,
        proxmox_lxc_status=proxmox_lxc_status,
        proxmox_vm_action=proxmox_vm_action,
        proxmox_lxc_action=proxmox_lxc_action,
        user_prefs=user_prefs,
        memory_store=memory_store,
        user_id=user_id,
    )


def rag_query_from_prompt(text: str) -> dict | None:
    return domain_rag_query_from_prompt(text)


def select_rag_hits(intent: dict, limit: int = 3) -> list[dict]:
    return domain_select_rag_hits(intent, rag_store=rag_store, limit=limit)


def format_rag_reply(intent: dict, hits: list[dict]) -> str:
    return domain_format_rag_reply(intent, hits)


def cloud_llm_available() -> bool:
    return domain_cloud_llm_available()


def rag_needs_smart_llm(text: str) -> bool:
    return domain_rag_needs_smart_llm(text)


def rag_llm_answer(user_text: str, hits: list[dict]) -> str:
    return domain_rag_llm_answer(
        user_text,
        hits,
        get_provider=get_provider,
        get_gemini=get_gemini,
        get_openai=get_openai,
    )



# ---------------------------
# Chat (Skills -> LLM fallback)
# ---------------------------
app.include_router(build_auth_chat_router(build_auth_chat_deps(sys.modules[__name__])))
app.include_router(build_voice_router(build_voice_deps(sys.modules[__name__])))

# ---------------------------
# Auto-backup scheduler
# ---------------------------
_auto_backup_task: asyncio.Task | None = None


def _write_auto_backup() -> str:
    """Write a timestamped backup JSON and return the path written."""
    import json as _json
    import datetime as _dt
    from pathlib import Path as _Path
    import tempfile as _tempfile

    preferred = _Path("/var/lib/jarvis/auto_backups")
    try:
        preferred.mkdir(parents=True, exist_ok=True)
        backup_dir = preferred
    except OSError:
        backup_dir = _Path(_tempfile.gettempdir()) / "jarvis" / "auto_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H-%M-%S")
    filename = backup_dir / f"jarvis_backup_{ts}.json"

    payload = {
        "backup_version": 1,
        "exported_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "auto": True,
        "users": user_store.list_users(),
        "groups": group_store.list_groups(),
        "memberships": membership_store.list_memberships(),
        "group_permissions": permission_store.list_group_permissions(),
        "user_permissions": permission_store.list_user_permissions(),
        "settings": admin_settings_store.get(),
        "credits": credit_store.data,
        "user_limits": user_limits_store.data,
        # byok_store excluded — users must re-enter API keys after restore
        # usage_log excluded — high-volume, not suitable for backup
    }
    filename.write_text(_json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    # Keep only the 7 most recent auto backups
    existing = sorted(backup_dir.glob("jarvis_backup_*.json"))
    for old in existing[:-7]:
        try:
            old.unlink()
        except OSError:
            pass

    return str(filename)


async def _auto_backup_loop() -> None:
    interval_hours = int(os.getenv("JARVIS_AUTO_BACKUP_INTERVAL_HOURS") or "24")
    interval_sec = max(3600, interval_hours * 3600)
    await asyncio.sleep(60)  # short initial delay so startup is not blocked
    while True:
        try:
            path = await asyncio.get_event_loop().run_in_executor(None, _write_auto_backup)
            logging.getLogger("jarvis").info("Auto-backup written: %s", path)
        except Exception as exc:
            logging.getLogger("jarvis").warning("Auto-backup failed: %s", exc)
        await asyncio.sleep(interval_sec)



# ---------------------------
# STT (local faster-whisper OR Gemini)
# ---------------------------
