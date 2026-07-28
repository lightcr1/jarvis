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
    proxmox_health,
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
    default_identity_sessions_path as runtime_default_identity_sessions_path,
    get_identity_session as runtime_get_identity_session,
    issue_identity_token as runtime_issue_identity_token,
    issue_token as runtime_issue_token,
    load_identity_tokens as runtime_load_identity_tokens,
    normalize_filter as runtime_normalize_filter,
    prepare_audit_filters as runtime_prepare_audit_filters,
    prune_identity_tokens as runtime_prune_identity_tokens,
    save_identity_tokens as runtime_save_identity_tokens,
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
from jarvis.api_device_sync import build_device_sync_router
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
from jarvis.api_tasks import build_tasks_router
from jarvis.tasks.service import TaskService
from jarvis.tasks.store import TaskStore
from jarvis.integration_credentials import IntegrationCredentialStore
from jarvis.api_calendar import build_calendar_router
from jarvis.calendar.service import CalendarService
from jarvis.calendar.store import CalendarEventStore
from jarvis.api_workspace import build_workspace_router
from jarvis.workspace.service import WorkspaceService
from jarvis.workspace.store import WorkspaceTargetStore
from jarvis.api_files import build_files_router
from jarvis.files.service import FileService
from jarvis.files.store import FileStore
from jarvis.api_email import build_email_router
from jarvis.email.service import EmailService
from jarvis.email.store import EmailDraftStore, EmailMessageStore
from jarvis.api_notifications import build_notifications_router
from jarvis.push_store import PushSubscriptionStore
from jarvis.push_vapid import get_vapid_keys
from jarvis.push_service import fanout_push
from jarvis.proactive_suggestions import SuggestionEngine
from jarvis.api_policies import build_policies_router
from jarvis.policy_store import PolicyStore
from jarvis.policy_engine import PolicyEngine
from jarvis.playbook_store import PlaybookStore
from jarvis.playbook_executor import PlaybookExecutor, build_default_action_dispatch
from jarvis.router_dependencies import build_admin_deps, build_alerts_deps, build_auth_chat_deps, build_calendar_deps, build_device_sync_deps, build_email_deps, build_files_deps, build_home_assistant_deps, build_memory_deps, build_notifications_deps, build_policies_deps, build_status_deps, build_tasks_deps, build_voice_deps, build_workspace_deps
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
    global _auto_backup_task, _morning_briefing_task, wakeword_engine
    global _weekly_digest_task, _nightly_summary_task, _suggestions_task
    _WARN_IF_MISSING = ["OPENAI_API_KEY", "JARVIS_PASSPHRASE"]
    for _var in _WARN_IF_MISSING:
        if not os.getenv(_var):
            logging.warning("JARVIS startup: env var %s is not set — dependent features will fail", _var)
    if os.getenv("JARVIS_AUTO_BACKUP_DISABLED", "").strip().lower() not in {"1", "true", "yes"}:
        _auto_backup_task = asyncio.create_task(_auto_backup_loop())
    _morning_briefing_task = asyncio.create_task(_morning_briefing_loop())
    _weekly_digest_task = asyncio.create_task(_weekly_digest_loop())
    _nightly_summary_task = asyncio.create_task(_nightly_summary_loop())
    _suggestions_task = asyncio.create_task(_suggestions_loop())
    prune_expired_tokens(_tokens)
    alert_engine.start()
    policy_engine.start()
    wakeword_engine = create_wakeword_engine(admin_settings_store.get())
    wakeword_engine.start(asyncio.get_event_loop(), _on_wakeword_detected)
    yield
    wakeword_engine.stop()
    alert_engine.stop()
    policy_engine.stop()
    for _task in (_auto_backup_task, _morning_briefing_task, _weekly_digest_task, _nightly_summary_task, _suggestions_task):
        if _task:
            _task.cancel()

app = FastAPI(title="Jarvis Backend", lifespan=_lifespan)
logger = logging.getLogger("jarvis.audio")

mount_frontend_assets(app)
app.include_router(frontend_router)


_tokens: dict[str, float] = {}  # token -> expires_epoch
_IDENTITY_SESSIONS_PATH = runtime_default_identity_sessions_path()
_identity_tokens: dict[str, dict] = runtime_load_identity_tokens(_IDENTITY_SESSIONS_PATH)  # token -> {user_id, role, exp}, persisted across restarts


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
task_store = TaskStore()
push_subscription_store = PushSubscriptionStore()
policy_store = PolicyStore()
playbook_store = PlaybookStore()
integration_credential_store = IntegrationCredentialStore()
calendar_event_store = CalendarEventStore()
email_message_store = EmailMessageStore()
email_draft_store = EmailDraftStore()
workspace_target_store = WorkspaceTargetStore()
file_store = FileStore()

wakeword_engine: NullWakewordEngine | SoftwareWakewordEngine = NullWakewordEngine()

DEFAULT_ADMIN_USERNAME = (os.getenv("JARVIS_DEFAULT_ADMIN_USERNAME") or "admin").strip() or "admin"
DEFAULT_ADMIN_PASSWORD = (os.getenv("JARVIS_DEFAULT_ADMIN_PASSWORD") or "admin123").strip() or "admin123"
if DEFAULT_ADMIN_PASSWORD == "admin123":
    logger.warning("SECURITY: JARVIS_DEFAULT_ADMIN_PASSWORD is not set — using insecure default 'admin123'. Set this env var before exposing JARVIS to a network.")


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
        path=_IDENTITY_SESSIONS_PATH,
    )


def _get_identity_session(x_jarvis_session: str | None) -> dict | None:
    return runtime_get_identity_session(
        identity_tokens=_identity_tokens,
        x_jarvis_session=x_jarvis_session,
        user_store=user_store,
        normalize_role=normalize_role,
        path=_IDENTITY_SESSIONS_PATH,
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
    return runtime_prune_identity_tokens(_identity_tokens, _IDENTITY_SESSIONS_PATH)


def _persist_identity_tokens() -> None:
    runtime_save_identity_tokens(_identity_tokens, _IDENTITY_SESSIONS_PATH)


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

suggestion_engine = SuggestionEngine()


def _alert_push_fanout(payload: dict, connected_user_ids: set[str]):
    return fanout_push(payload, connected_user_ids, push_subscription_store, get_vapid_keys())


get_alert_broadcaster().configure_push_fanout(_alert_push_fanout)

policy_engine = PolicyEngine(
    policy_store=policy_store,
    run_cmd=run_cmd,
    ensure_service_allowed=ensure_service_allowed,
    emergency_stop_enabled=emergency_stop_enabled,
    write_permission_check=lambda: role_has_permission("admin", "actions.write.execute"),
    audit_admin_event=_audit_admin_event,
    ha_store=home_assistant_store,
    broadcast_fn=get_alert_broadcaster().broadcast,
)

playbook_executor = PlaybookExecutor(
    store=playbook_store,
    action_dispatch=build_default_action_dispatch(run_cmd, ensure_service_allowed),
    audit_admin_event=_audit_admin_event,
    emergency_stop_enabled=emergency_stop_enabled,
    broadcast_fn=get_alert_broadcaster().broadcast,
)

task_service = TaskService(
    store=task_store,
    user_store=user_store,
    membership_store=membership_store,
    permission_store=permission_store,
    resolve_effective_permissions=resolve_effective_permissions,
    normalize_role=normalize_role,
    audit_log=audit_log,
)

calendar_service = CalendarService(
    store=calendar_event_store,
    credential_store=integration_credential_store,
    user_store=user_store,
    membership_store=membership_store,
    permission_store=permission_store,
    resolve_effective_permissions=resolve_effective_permissions,
    normalize_role=normalize_role,
    audit_log=audit_log,
)

email_service = EmailService(
    message_store=email_message_store,
    draft_store=email_draft_store,
    credential_store=integration_credential_store,
    user_store=user_store,
    membership_store=membership_store,
    permission_store=permission_store,
    resolve_effective_permissions=resolve_effective_permissions,
    normalize_role=normalize_role,
    audit_log=audit_log,
)

workspace_service = WorkspaceService(
    store=workspace_target_store,
    credential_store=integration_credential_store,
    membership_store=membership_store,
    permission_store=permission_store,
    resolve_effective_permissions=resolve_effective_permissions,
    normalize_role=normalize_role,
    audit_log=audit_log,
    guacamole_url_fn=lambda: os.getenv("JARVIS_WORKSPACE_GUACAMOLE_URL"),
    guacamole_secret_fn=lambda: os.getenv("JARVIS_WORKSPACE_JSON_SECRET"),
)

file_service = FileService(
    store=file_store,
    user_store=user_store,
    membership_store=membership_store,
    permission_store=permission_store,
    resolve_effective_permissions=resolve_effective_permissions,
    normalize_role=normalize_role,
    user_limits_store=user_limits_store,
    admin_settings_store=admin_settings_store,
    audit_log=audit_log,
)

# Transitional modular router activation.
# The admin router now resolves live dependencies against the current module state,
# so test suites that replace stores on jarvisappv4 keep working.
app.include_router(build_admin_router(build_admin_deps(sys.modules[__name__])))
app.include_router(build_alerts_router(build_alerts_deps(sys.modules[__name__])))
app.include_router(build_device_sync_router(build_device_sync_deps(sys.modules[__name__])))
app.include_router(build_home_assistant_router(build_home_assistant_deps(sys.modules[__name__])))
app.include_router(build_memory_router(build_memory_deps(sys.modules[__name__])))
app.include_router(build_status_router(build_status_deps(sys.modules[__name__])))
app.include_router(build_tasks_router(build_tasks_deps(sys.modules[__name__])))
app.include_router(build_notifications_router(build_notifications_deps(sys.modules[__name__])))
app.include_router(build_policies_router(build_policies_deps(sys.modules[__name__])))
app.include_router(build_calendar_router(build_calendar_deps(sys.modules[__name__])))
app.include_router(build_email_router(build_email_deps(sys.modules[__name__])))
app.include_router(build_workspace_router(build_workspace_deps(sys.modules[__name__])))
app.include_router(build_files_router(build_files_deps(sys.modules[__name__])))

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
        task_service=task_service,
        calendar_service=calendar_service,
        email_service=email_service,
        file_service=file_service,
        get_provider=get_provider,
        get_gemini=get_gemini,
        get_openai=get_openai,
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
_morning_briefing_task: asyncio.Task | None = None
_weekly_digest_task: asyncio.Task | None = None
_nightly_summary_task: asyncio.Task | None = None
_suggestions_task: asyncio.Task | None = None

_auto_backup_log: list[dict] = []  # {"ts": int, "ok": bool} — most recent last, capped at 500
_briefing_sent_dates: dict[str, str] = {}  # user_id -> ISO date the morning briefing last fired


def _record_auto_backup_outcome(ok: bool) -> None:
    _auto_backup_log.append({"ts": int(_startup_time.time()), "ok": ok})
    if len(_auto_backup_log) > 500:
        del _auto_backup_log[: len(_auto_backup_log) - 500]


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
            _record_auto_backup_outcome(True)
        except Exception as exc:
            logging.getLogger("jarvis").warning("Auto-backup failed: %s", exc)
            _record_auto_backup_outcome(False)
        await asyncio.sleep(interval_sec)


def _next_briefing_seconds(hhmm: str, now) -> float:
    """Return seconds until the next occurrence of HH:MM from `now`."""
    from datetime import timedelta
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except Exception:
        return 3600.0
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def _calendar_lines_for_date(items: list[dict], date_str: str) -> list[str]:
    """Formats HA calendar items whose `starts_at` date matches `date_str` (YYYY-MM-DD)
    as "HH:MM — Title" lines, shared by the morning briefing and nightly summary loops.
    """
    lines: list[str] = []
    for item in items:
        starts = (item.get("starts_at") or "")[:10]
        if starts != date_str or not item.get("title"):
            continue
        raw = item.get("starts_at", "")
        hm_str = raw.split("T")[1][:5] if "T" in raw else ""
        lines.append(f"{hm_str} — {item['title']}" if hm_str else item["title"])
    return lines


def _user_role_and_permissions(uid: str) -> tuple[str, list[str]]:
    user = user_store.get_user(uid)
    role = normalize_role((user or {}).get("role") or "standard_user")
    effective = list(resolve_effective_permissions(role, uid, membership_store, permission_store))
    return role, effective


def _briefing_task_line(uid: str, role: str) -> str:
    try:
        open_tasks = [t for t in task_service.list_tasks(user_id=uid, role=role)["tasks"] if t.get("status") != "done"]
    except Exception:
        return ""
    if not open_tasks:
        return ""
    names = ", ".join(t["title"] for t in open_tasks[:3])
    if len(open_tasks) > 3:
        names += f", and {len(open_tasks) - 3} more"
    return f" You have {len(open_tasks)} open task(s): {names}."


def _briefing_calendar_line(uid: str, role: str) -> str:
    from datetime import datetime as _dt_cls, timedelta as _td
    try:
        now = _dt_cls.now().astimezone()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + _td(days=1)
        events = calendar_service.list_events(user_id=uid, role=role, start=int(start.timestamp()), end=int(end.timestamp()))["events"]
    except Exception:
        return ""
    if not events:
        return ""
    parts = [f"{_dt_cls.fromtimestamp(e['start']).astimezone().strftime('%H:%M')} {e['title']}" for e in events[:5]]
    return " Personal calendar today: " + "; ".join(parts) + "."


def _briefing_email_line(uid: str, role: str) -> str:
    try:
        email_service.sync_inbox(user_id=uid, role=role, limit=20)
        unread = email_service.list_messages(user_id=uid, role=role, unread_only=True)["messages"]
    except Exception:
        return ""
    if not unread:
        return ""
    return f" {len(unread)} unread email(s) in your inbox."


async def _morning_briefing_loop() -> None:
    from datetime import datetime as _dt_cls
    _log = logging.getLogger("jarvis")
    await asyncio.sleep(30)  # short initial delay
    while True:
        try:
            all_prefs = user_preferences_store.data.get("preferences", {})
            enabled_users = [
                (uid, prefs)
                for uid, prefs in all_prefs.items()
                if prefs.get("morning_briefing_enabled")
            ]
            if not enabled_users:
                await asyncio.sleep(60)
                continue

            now = _dt_cls.now()
            next_secs = min(
                _next_briefing_seconds(prefs.get("morning_briefing_time", "07:30"), now)
                for _, prefs in enabled_users
            )
            await asyncio.sleep(max(next_secs, 1))

            now = _dt_cls.now()
            current_hm = now.strftime("%H:%M")
            for uid, prefs in enabled_users:
                if prefs.get("morning_briefing_time", "07:30") != current_hm:
                    continue
                try:
                    role, effective = _user_role_and_permissions(uid)
                    skill_result = try_skill("briefing", role=role, token=None, granted_permissions=effective, user_id=uid)
                    reply_text = (skill_result or {}).get("reply", "Good morning. All systems nominal.")
                    try:
                        today = now.date().isoformat()
                        cal_lines = _calendar_lines_for_date(home_assistant_store.list_calendar_items(), today)
                        if cal_lines:
                            reply_text = reply_text.rstrip(".") + " Today: " + "; ".join(cal_lines) + "."
                    except Exception:
                        pass
                    reply_text += _briefing_task_line(uid, role)
                    loop = asyncio.get_event_loop()
                    reply_text += await loop.run_in_executor(None, _briefing_calendar_line, uid, role)
                    reply_text += await loop.run_in_executor(None, _briefing_email_line, uid, role)
                    from jarvis.api_alerts import get_alert_broadcaster
                    await get_alert_broadcaster().broadcast({
                        "type": "briefing",
                        "user_id": uid,
                        "text": reply_text,
                        "ts": int(_startup_time.time()),
                    })
                    _briefing_sent_dates[uid] = now.date().isoformat()
                    _log.info("Morning briefing broadcast for user %s", uid)
                except Exception as exc:
                    _log.warning("Morning briefing failed for user %s: %s", uid, exc)

            await asyncio.sleep(60)  # avoid re-firing in the same minute
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _log.warning("Morning briefing loop error: %s", exc)
            await asyncio.sleep(60)


# ---------------------------
# Weekly digest scheduler
# ---------------------------
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def _next_weekly_seconds(day_name: str, hhmm: str, now) -> float:
    """Return seconds until the next occurrence of `day_name` (e.g. "sunday") at HH:MM."""
    from datetime import timedelta
    try:
        target_day = _WEEKDAYS.index((day_name or "sunday").strip().lower())
    except ValueError:
        target_day = 6
    try:
        h, m = (int(x) for x in hhmm.split(":"))
    except Exception:
        h, m = 18, 0
    days_ahead = (target_day - now.weekday()) % 7
    target = (now + timedelta(days=days_ahead)).replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=7)
    return (target - now).total_seconds()


def _top_alert_events(history: list[dict], since_ts: float, limit: int = 5) -> list[dict]:
    """Selects the most notable alerts fired since `since_ts` — critical first, then
    most recent — capped at `limit` entries for a digest summary.
    """
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    recent = [e for e in history if e.get("timestamp", 0) >= since_ts]
    recent.sort(key=lambda e: (severity_rank.get(e.get("severity"), 3), -e.get("timestamp", 0)))
    return recent[:limit]


def _build_weekly_digest_text(
    cpu_pct: float | None,
    ram_pct: float | None,
    disk_pct: float | None,
    top_alerts: list[dict],
    backup_successes: int,
    backup_failures: int,
) -> str:
    if cpu_pct is not None and ram_pct is not None and disk_pct is not None:
        parts = [f"Current load: CPU {cpu_pct:.0f}%, RAM {ram_pct:.0f}%, disk {disk_pct:.0f}%."]
    else:
        parts = ["Resource snapshot unavailable."]
    if top_alerts:
        names = ", ".join(f"{a.get('rule_name', 'alert')} ({a.get('severity')})" for a in top_alerts)
        parts.append(f"Notable alerts this week: {names}.")
    else:
        parts.append("No alerts fired this week.")
    if backup_successes or backup_failures:
        parts.append(f"Auto-backups: {backup_successes} succeeded, {backup_failures} failed.")
    return " ".join(parts)


async def _weekly_digest_loop() -> None:
    from datetime import datetime as _dt_cls
    from jarvis.alert_engine import _read_cpu_percent, _read_disk_percent, _read_ram_percent
    _log = logging.getLogger("jarvis")
    await asyncio.sleep(45)  # short initial delay, staggered from the other loops
    while True:
        try:
            all_prefs = user_preferences_store.data.get("preferences", {})
            enabled_users = [(uid, p) for uid, p in all_prefs.items() if p.get("weekly_digest_enabled")]
            if not enabled_users:
                await asyncio.sleep(300)
                continue

            now = _dt_cls.now()
            next_secs = min(
                _next_weekly_seconds(p.get("weekly_digest_day", "sunday"), p.get("weekly_digest_time", "18:00"), now)
                for _, p in enabled_users
            )
            await asyncio.sleep(max(next_secs, 1))

            now = _dt_cls.now()
            current_hm = now.strftime("%H:%M")
            current_day = _WEEKDAYS[now.weekday()]
            week_ago_ts = _startup_time.time() - 7 * 86400
            history = alert_engine.get_history(limit=500)
            top_alerts = _top_alert_events(history, week_ago_ts)
            recent_backups = [b for b in _auto_backup_log if b["ts"] >= week_ago_ts]
            text = _build_weekly_digest_text(
                _read_cpu_percent(), _read_ram_percent(), _read_disk_percent(),
                top_alerts,
                sum(1 for b in recent_backups if b["ok"]),
                sum(1 for b in recent_backups if not b["ok"]),
            )

            from jarvis.api_alerts import get_alert_broadcaster
            for uid, prefs in enabled_users:
                if prefs.get("weekly_digest_day", "sunday") != current_day:
                    continue
                if prefs.get("weekly_digest_time", "18:00") != current_hm:
                    continue
                try:
                    await get_alert_broadcaster().broadcast({
                        "type": "weekly_digest",
                        "user_id": uid,
                        "text": text,
                        "ts": int(_startup_time.time()),
                    })
                    _log.info("Weekly digest broadcast for user %s", uid)
                except Exception as exc:
                    _log.warning("Weekly digest failed for user %s: %s", uid, exc)

            await asyncio.sleep(60)  # avoid re-firing in the same minute
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _log.warning("Weekly digest loop error: %s", exc)
            await asyncio.sleep(300)


# ---------------------------
# Nightly summary scheduler
# ---------------------------
def _count_sessions_active_on(sessions: list[dict], date_str: str) -> int:
    """Counts chat sessions whose `updated_at` falls on `date_str` — a proxy for
    "how many separate conversations happened today" (not raw message count, which
    would overcount long-lived sessions touched only briefly today).
    """
    from datetime import datetime as _dt_cls
    count = 0
    for session in sessions:
        ts = session.get("updated_at")
        if ts and _dt_cls.fromtimestamp(ts).date().isoformat() == date_str:
            count += 1
    return count


def _build_nightly_summary_text(
    chat_count_today: int,
    alerts_today: list[dict],
    briefing_sent: bool,
    tomorrow_calendar_lines: list[str],
) -> str:
    parts = [
        f"{chat_count_today} conversation{'s' if chat_count_today != 1 else ''} today"
        if chat_count_today else "No chat activity today"
    ]
    parts.append(f"{len(alerts_today)} alert{'s' if len(alerts_today) != 1 else ''} fired" if alerts_today else "no alerts fired")
    parts.append("morning briefing sent" if briefing_sent else "morning briefing not sent")
    summary = "; ".join(parts) + "."
    if tomorrow_calendar_lines:
        summary += " Tomorrow: " + "; ".join(tomorrow_calendar_lines) + "."
    return summary


async def _nightly_summary_loop() -> None:
    from datetime import datetime as _dt_cls, timedelta as _timedelta
    _log = logging.getLogger("jarvis")
    await asyncio.sleep(40)  # short initial delay, staggered from the other loops
    while True:
        try:
            all_prefs = user_preferences_store.data.get("preferences", {})
            enabled_users = [(uid, p) for uid, p in all_prefs.items() if p.get("nightly_summary_enabled")]
            if not enabled_users:
                await asyncio.sleep(120)
                continue

            now = _dt_cls.now()
            next_secs = min(
                _next_briefing_seconds(p.get("nightly_summary_time", "21:00"), now)
                for _, p in enabled_users
            )
            await asyncio.sleep(max(next_secs, 1))

            now = _dt_cls.now()
            current_hm = now.strftime("%H:%M")
            today = now.date().isoformat()
            tomorrow = (now.date() + _timedelta(days=1)).isoformat()
            today_start_ts = _dt_cls.combine(now.date(), _dt_cls.min.time()).timestamp()
            alerts_today = [e for e in alert_engine.get_history(limit=500) if e.get("timestamp", 0) >= today_start_ts]
            try:
                calendar_items = home_assistant_store.list_calendar_items()
            except Exception:
                calendar_items = []
            tomorrow_lines = _calendar_lines_for_date(calendar_items, tomorrow)

            from jarvis.api_alerts import get_alert_broadcaster
            for uid, prefs in enabled_users:
                if prefs.get("nightly_summary_time", "21:00") != current_hm:
                    continue
                try:
                    sessions = chat_history.list_sessions(f"user:{uid}")
                    chat_count = _count_sessions_active_on(sessions, today)
                    briefing_sent = _briefing_sent_dates.get(uid) == today
                    text = _build_nightly_summary_text(chat_count, alerts_today, briefing_sent, tomorrow_lines)
                    await get_alert_broadcaster().broadcast({
                        "type": "nightly_summary",
                        "user_id": uid,
                        "text": text,
                        "ts": int(_startup_time.time()),
                    })
                    _log.info("Nightly summary broadcast for user %s", uid)
                except Exception as exc:
                    _log.warning("Nightly summary failed for user %s: %s", uid, exc)

            await asyncio.sleep(60)  # avoid re-firing in the same minute
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _log.warning("Nightly summary loop error: %s", exc)
            await asyncio.sleep(120)


# ---------------------------
# Proactive suggestions scheduler
# ---------------------------
async def _suggestions_loop() -> None:
    _log = logging.getLogger("jarvis")
    interval = max(600, int(os.getenv("JARVIS_SUGGESTIONS_POLL_INTERVAL_SEC") or str(6 * 3600)))
    await asyncio.sleep(90)  # short initial delay, staggered from the other loops
    while True:
        try:
            learned = engine.learning.data.get("learned_replies", {})
            proxmox_snapshot: dict | None = None
            try:
                snapshot = proxmox_health()
                proxmox_snapshot = snapshot if snapshot.get("configured") else None
            except Exception:
                proxmox_snapshot = None

            events = suggestion_engine.evaluate(
                learned_replies=learned,
                proxmox_health=proxmox_snapshot,
                backup_log=_auto_backup_log,
            )
            if events:
                from jarvis.api_alerts import get_alert_broadcaster
                for event in events:
                    try:
                        await get_alert_broadcaster().broadcast(event)
                        _log.info("Suggestion broadcast: %s", event.get("kind"))
                    except Exception as exc:
                        _log.warning("Suggestion broadcast failed: %s", exc)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            _log.warning("Suggestions loop error: %s", exc)
        await asyncio.sleep(interval)


# ---------------------------
# STT (local faster-whisper OR Gemini)
# ---------------------------
