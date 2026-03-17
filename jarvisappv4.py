import sys
import logging
import os
import re
import subprocess
import uuid

from fastapi import FastAPI, HTTPException

from jarvis.proxmox_module import build_router, proxmox_lxc_status, proxmox_vm_status
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
    transcribe_gemini as audio_transcribe_gemini,
    transcribe_local as audio_transcribe_local,
    wakeword_enabled as audio_wakeword_enabled,
    wakeword_phrase as audio_wakeword_phrase,
)
from jarvis.ai_clients import (
    SYSTEM_PROMPT,
    build_context_reply,
    get_gemini,
    get_openai,
    get_provider,
    get_whisper,
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
from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.api_voice import build_voice_router
from jarvis.api_models import UnlockOut
from jarvis.frontend_routes import frontend_router, mount_frontend_assets
from jarvis.router_dependencies import build_admin_deps, build_auth_chat_deps, build_voice_deps
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
from jarvis.session_auth import bearer_token_from_header, enforce_token_capacity, is_token_active, prune_expired_tokens

app = FastAPI(title="Jarvis Backend")
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


@app.get("/health")
def health():
    return {"ok": True}


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


def _settings_env_summary() -> dict[str, object]:
    return runtime_settings_env_summary(
        admin_settings_store=admin_settings_store,
        wakeword_enabled=wakeword_enabled,
        wakeword_phrase=wakeword_phrase,
        get_stt_provider=get_stt_provider,
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

# Transitional modular router activation.
# The admin router now resolves live dependencies against the current module state,
# so test suites that replace stores on jarvisappv4 keep working.
app.include_router(build_admin_router(build_admin_deps(sys.modules[__name__])))

# ---------------------------
# Skills (no LLM)
# ---------------------------
def wakeword_enabled() -> bool:
    return audio_wakeword_enabled(admin_settings_store.get)


def wakeword_phrase() -> str:
    return audio_wakeword_phrase(admin_settings_store.get)


def strip_wakeword(text: str) -> tuple[str, bool]:
    return audio_strip_wakeword(text, wakeword_phrase())


def synthesize_tts(text: str) -> bytes:
    return audio_synthesize_tts(text, logger)


def transcribe_local(audio_path: str) -> str:
    return audio_transcribe_local(audio_path, get_whisper)


def transcribe_gemini(audio_bytes: bytes, content_type: str | None) -> str:
    return audio_transcribe_gemini(audio_bytes, content_type, get_gemini)


def block_write_if_unauthorized(role: str, token: str | None, granted_permissions: list[str] | None = None) -> dict[str, object] | None:
    return domain_block_write_if_unauthorized(
        role,
        token,
        granted_permissions=granted_permissions,
        emergency_stop_enabled=emergency_stop_enabled,
        permission_check=lambda active_role, _active_token, active_permissions: (
            role_has_permission(active_role, "actions.write.execute")
            or ((active_permissions or []) and "actions.write.execute" in set(active_permissions))
        ),
    )


def try_skill(text: str, role: str = "admin", token: str | None = None, granted_permissions: list[str] | None = None) -> dict[str, object] | None:
    return domain_try_skill(
        text,
        role=role,
        token=token,
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
# STT (local faster-whisper OR Gemini)
# ---------------------------
