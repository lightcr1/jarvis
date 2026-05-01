from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class LiveRef(Generic[T]):
    getter: Callable[[], T]

    def get(self) -> T:
        return self.getter()


def live_attr(state: object, name: str) -> LiveRef[object]:
    return LiveRef(lambda: getattr(state, name))


def build_auth_chat_deps(state: object) -> dict:
    return {
        "ensure_default_admin_seeded": state.ensure_default_admin_seeded,
        "user_store": live_attr(state, "user_store"),
        "admin_password_store": live_attr(state, "admin_password_store"),
        "audit_log": live_attr(state, "audit_log"),
        "issue_token": state._issue_token,
        "token_fingerprint": state._token_fingerprint,
        "issue_identity_token": state._issue_identity_token,
        "user_preferences_store": live_attr(state, "user_preferences_store"),
        "identity_tokens": live_attr(state, "_identity_tokens"),
        "require_identity_session": state.require_identity_session,
        "normalize_role": state.normalize_role,
        "get_identity_session": state._get_identity_session,
        "chat_owner_key": state._chat_owner_key,
        "chat_history": live_attr(state, "chat_history"),
        "rag_store": live_attr(state, "rag_store"),
        "wakeword_enabled": state.wakeword_enabled,
        "wakeword_phrase": getattr(state, "wakeword_phrase", lambda: "hey jarvis"),
        "strip_wakeword": state.strip_wakeword,
        "tokens": live_attr(state, "_tokens"),
        "is_token_active": state.is_token_active,
        "resolve_effective_permissions": state.resolve_effective_permissions,
        "membership_store": live_attr(state, "membership_store"),
        "permission_store": live_attr(state, "permission_store"),
        "home_assistant_service": live_attr(state, "home_assistant_service"),
        "status_hub": live_attr(state, "status_hub"),
        "try_skill": state.try_skill,
        "rag_query_from_prompt": state.rag_query_from_prompt,
        "select_rag_hits": state.select_rag_hits,
        "rag_needs_smart_llm": state.rag_needs_smart_llm,
        "cloud_llm_available": state.cloud_llm_available,
        "format_rag_reply": state.format_rag_reply,
        "rag_llm_answer": state.rag_llm_answer,
        "engine": LiveRef(lambda: state.engine),
        "build_context_reply": state.build_context_reply,
        "get_provider": state.get_provider,
        "local_ai_chat_reply": state.local_ai_chat_reply,
        "local_ai_stub_reply": state.local_ai_stub_reply,
        "get_gemini": state.get_gemini,
        "get_openai": state.get_openai,
        "gemini_model": lambda: state.os.getenv("GEMINI_MODEL") or "gemini-2.5-flash",
        "openai_model": lambda: state.os.getenv("OPENAI_MODEL") or "gpt-4.1-mini",
        "openai_temperature": lambda: 0.3,
        "openai_max_tokens": lambda: int(state.os.getenv("OPENAI_MAX_TOKENS") or "120"),
        "system_prompt": lambda: state.SYSTEM_PROMPT,
        "bearer_token_from_header": state.bearer_token_from_header,
        "prune_expired_tokens": getattr(state, "prune_expired_tokens", lambda tokens: 0),
        "passphrase": lambda: (state.os.getenv("JARVIS_PASSPHRASE") or "").strip(),
    }


def build_admin_deps(state: object) -> dict:
    return {
        "require_admin_access": state.require_admin_access,
        "prepare_audit_filters": state._prepare_audit_filters,
        "validate_audit_query": state._validate_audit_query,
        "audit_log": live_attr(state, "audit_log"),
        "user_store": live_attr(state, "user_store"),
        "normalize_role": state.normalize_role,
        "audit_admin_event": state._audit_admin_event,
        "admin_password_store": live_attr(state, "admin_password_store"),
        "user_preferences_store": live_attr(state, "user_preferences_store"),
        "membership_store": live_attr(state, "membership_store"),
        "permission_store": live_attr(state, "permission_store"),
        "group_store": live_attr(state, "group_store"),
        "known_permissions": state.KNOWN_PERMISSIONS,
        "get_active_user_or_raise": state.get_active_user_or_raise,
        "build_permission_context": state.build_permission_context,
        "permission_decision": state.permission_decision,
        "settings_env_summary": state._settings_env_summary,
        "admin_settings_store": live_attr(state, "admin_settings_store"),
    }


def build_voice_deps(state: object) -> dict:
    return {
        "require_identity_session": state.require_identity_session,
        "get_identity_session": state._get_identity_session,
        "get_stt_provider": state.get_stt_provider,
        "transcribe_local": live_attr(state, "transcribe_local"),
        "transcribe_gemini": live_attr(state, "transcribe_gemini"),
        "synthesize_tts": live_attr(state, "synthesize_tts"),
        "user_preferences_store": live_attr(state, "user_preferences_store"),
        "status_hub": live_attr(state, "status_hub"),
        "logger": live_attr(state, "logger"),
        "subprocess": live_attr(state, "subprocess"),
        "uuid4_hex": lambda: state.uuid.uuid4().hex,
    }


def build_home_assistant_deps(state: object) -> dict:
    return {
        "require_identity_session": state.require_identity_session,
        "home_assistant_service": live_attr(state, "home_assistant_service"),
    }


def build_status_deps(state: object) -> dict:
    return {
        "status_hub": live_attr(state, "status_hub"),
    }


def build_alerts_deps(state: object) -> dict:
    return {
        "require_identity_session": state.require_identity_session,
        "home_assistant_service": live_attr(state, "home_assistant_service"),
    }
