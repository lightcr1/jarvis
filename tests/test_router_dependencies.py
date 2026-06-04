import os
import unittest
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.router_dependencies import build_admin_deps, build_auth_chat_deps


class _ListUserStore:
    def __init__(self, usernames: list[str]):
        self._users = [{"id": f"usr-{index:012x}", "username": name, "role": "admin", "enabled": True} for index, name in enumerate(usernames, start=1)]

    def list_users(self):
        return list(self._users)


class _EmptyStore:
    def list_users(self):
        return []

    def find_by_username(self, username: str):
        return None

    def get_user(self, user_id: str):
        return None

    def enabled_admin_count(self):
        return 0


class _NoopPasswords:
    def verify_password(self, user_id: str, password: str):
        return False

    def set_password(self, user_id: str, password: str):
        return None

    def delete_password(self, user_id: str):
        return False


class _NoopPreferences:
    def get(self, user_id: str):
        return {}

    def update(self, user_id: str, payload: dict):
        return payload

    def delete(self, user_id: str):
        return False


class _NoopMemberships:
    def list_memberships(self):
        return []

    def remove_user_memberships(self, user_id: str):
        return 0

    def remove_group_memberships(self, group_id: str):
        return 0


class _NoopPermissions:
    def list_group_permissions(self):
        return {}

    def list_user_permissions(self):
        return {}

    def clear_user_permissions(self, user_id: str):
        return False

    def clear_group_permissions(self, group_id: str):
        return False


class _NoopGroups:
    def list_groups(self):
        return []


class _NoopAudit:
    def write(self, event: str, payload: dict):
        return None

    def count_events(self):
        return 0

    def read_events(self, **kwargs):
        return []

    def aggregate_counts(self, **kwargs):
        return {}


class _NoopSettings:
    def get(self):
        return {"usage_limits": {}, "voice": {}}

    def update(self, payload: dict):
        return payload


class _NoopEngine:
    def process(self, text: str, token: str | None, role: str, source: str, granted_permissions: list[str]):
        return SimpleNamespace(summary="ok", data={})


class RouterDependencyTests(unittest.TestCase):
    def test_admin_router_uses_live_user_store_reference(self):
        state = SimpleNamespace(
            require_admin_access=lambda *args, **kwargs: ("usr-1", "admin"),
            _prepare_audit_filters=lambda event, role, actor_user_id, token_fingerprint: {
                "event": event,
                "role": role,
                "actor_user_id": actor_user_id,
                "token_fingerprint": token_fingerprint,
            },
            _validate_audit_query=lambda *args, **kwargs: None,
            audit_log=_NoopAudit(),
            user_store=_ListUserStore(["alpha"]),
            normalize_role=lambda role: role,
            _audit_admin_event=lambda *args, **kwargs: None,
            admin_password_store=_NoopPasswords(),
            user_preferences_store=_NoopPreferences(),
            membership_store=_NoopMemberships(),
            permission_store=_NoopPermissions(),
            group_store=_NoopGroups(),
            KNOWN_PERMISSIONS={"users.read"},
            get_active_user_or_raise=lambda store, user_id: store.get_user(user_id),
            build_permission_context=lambda *args, **kwargs: {},
            permission_decision=lambda *args, **kwargs: {"allowed": False},
            _settings_env_summary=lambda: {},
            admin_settings_store=_NoopSettings(),
            _identity_tokens={},
            _prune_identity_tokens=lambda t: None,
        )
        app = FastAPI()
        app.include_router(build_admin_router(build_admin_deps(state)))
        client = TestClient(app)

        first = client.get("/admin/users")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["users"][0]["username"], "alpha")

        state.user_store = _ListUserStore(["beta"])

        second = client.get("/admin/users")
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["users"][0]["username"], "beta")

    def test_auth_router_uses_live_identity_token_reference(self):
        state = SimpleNamespace(
            ensure_default_admin_seeded=lambda: None,
            user_store=_EmptyStore(),
            admin_password_store=_NoopPasswords(),
            audit_log=_NoopAudit(),
            _issue_token=lambda: SimpleNamespace(token="token", expires_in_sec=60),
            _token_fingerprint=lambda token: "fingerprint",
            _issue_identity_token=lambda user_id, role: {"session_token": "session"},
            user_preferences_store=_NoopPreferences(),
            _identity_tokens={"session-a": {"user_id": "usr-1"}},
            require_identity_session=lambda x_jarvis_session: {"user": {"id": "usr-1", "username": "admin", "role": "admin"}},
            normalize_role=lambda role: role,
            _get_identity_session=lambda token: None,
            _chat_owner_key=lambda session, guest: ("guest:test", None),
            chat_history=SimpleNamespace(
                ensure_session=lambda *args, **kwargs: {"id": "chat-1"},
                append_message=lambda *args, **kwargs: None,
                list_sessions=lambda **kwargs: [],
                create_session=lambda *args, **kwargs: {"id": "chat-1"},
                get_session=lambda *args, **kwargs: None,
                delete_session=lambda *args, **kwargs: False,
            ),
            rag_store=SimpleNamespace(data={"updated_at": 0, "report": {}, "sources": {}}, refresh=lambda: {}, search=lambda q, limit=5: []),
            wakeword_enabled=lambda: False,
            strip_wakeword=lambda text: (text, False),
            _tokens={},
            is_token_active=lambda tokens, token: False,
            resolve_effective_permissions=lambda *args, **kwargs: set(),
            membership_store=_NoopMemberships(),
            permission_store=_NoopPermissions(),
            try_skill=lambda *args, **kwargs: None,
            rag_query_from_prompt=lambda text: None,
            select_rag_hits=lambda intent, limit=3: [],
            rag_needs_smart_llm=lambda text: False,
            cloud_llm_available=lambda: False,
            format_rag_reply=lambda intent, hits: "reply",
            rag_llm_answer=lambda text, hits: "reply",
            engine=_NoopEngine(),
            build_context_reply=lambda text: "fallback",
            get_provider=lambda: "local",
            local_ai_chat_reply=lambda messages, system_prompt: "reply",
            local_ai_stub_reply=lambda text: "reply",
            get_gemini=lambda: None,
            get_openai=lambda: None,
            gemini_model=lambda: "gemini",
            openai_model=lambda: "gpt",
            openai_temperature=lambda: 0.2,
            openai_max_tokens=lambda: 128,
            SYSTEM_PROMPT="system",
            bearer_token_from_header=lambda auth: None,
            os=os,
        )
        app = FastAPI()
        app.include_router(build_auth_chat_router(build_auth_chat_deps(state)))
        client = TestClient(app)

        first = client.post("/auth/logout", headers={"X-Jarvis-Session": "session-a"})
        self.assertEqual(first.status_code, 200)
        self.assertNotIn("session-a", state._identity_tokens)

        state._identity_tokens = {"session-b": {"user_id": "usr-2"}}

        second = client.post("/auth/logout", headers={"X-Jarvis-Session": "session-b"})
        self.assertEqual(second.status_code, 200)
        self.assertNotIn("session-b", state._identity_tokens)


if __name__ == "__main__":
    unittest.main()
