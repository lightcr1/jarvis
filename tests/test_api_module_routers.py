import io
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.api_models import UnlockOut
from jarvis.api_voice import build_voice_router


class _FakePasswordStore:
    def __init__(self):
        self.passwords = {}

    def verify_password(self, user_id: str, password: str) -> bool:
        return self.passwords.get(user_id) == password

    def set_password(self, user_id: str, password: str) -> None:
        self.passwords[user_id] = password


class _FakeUserStore:
    def __init__(self):
        self.users = {
            "usr-admin": {"id": "usr-admin", "username": "admin", "role": "admin", "enabled": True},
            "usr-user": {"id": "usr-user", "username": "alice", "role": "standard_user", "enabled": True},
        }

    def find_by_username(self, username: str):
        for user in self.users.values():
            if user["username"] == username:
                return user
        return None

    def get_user(self, user_id: str):
        return self.users.get(user_id)

    def list_users(self):
        return list(self.users.values())

    def enabled_admin_count(self):
        return len([user for user in self.users.values() if user["role"] == "admin" and user["enabled"]])


class _FakePreferencesStore:
    def __init__(self):
        self.data = {}

    def get(self, user_id: str):
        return self.data.get(user_id, {})

    def update(self, user_id: str, payload: dict):
        self.data[user_id] = {**self.data.get(user_id, {}), **payload}
        return self.data[user_id]


class _FakeChatHistory:
    def __init__(self):
        self.sessions = {}
        self.counter = 0

    def ensure_session(self, session_id, owner_key, owner_user_id):
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]
        self.counter += 1
        new_id = session_id or f"s-{self.counter}"
        session = {"id": new_id, "owner_key": owner_key, "owner_user_id": owner_user_id, "messages": []}
        self.sessions[new_id] = session
        return session

    def append_message(self, session_id, role, text, owner_key, owner_user_id):
        self.sessions[session_id]["messages"].append({"role": role, "text": text})

    def list_sessions(self, owner_key):
        return [value for value in self.sessions.values() if value["owner_key"] == owner_key]

    def create_session(self, title, owner_key, owner_user_id):
        self.counter += 1
        session = {"id": f"s-{self.counter}", "title": title, "owner_key": owner_key, "owner_user_id": owner_user_id, "messages": []}
        self.sessions[session["id"]] = session
        return session

    def get_session(self, session_id, owner_key):
        session = self.sessions.get(session_id)
        if session and session["owner_key"] == owner_key:
            return session
        return None

    def delete_session(self, session_id, owner_key):
        session = self.get_session(session_id, owner_key)
        if not session:
            return False
        self.sessions.pop(session_id, None)
        return True


class _FakeAuditLog:
    def __init__(self):
        self.events = []

    def write(self, event, payload):
        self.events.append({"event": event, **payload})

    def read_events(self, **_kwargs):
        return list(self.events)

    def count_events(self, **_kwargs):
        return len(self.events)

    def aggregate_counts(self, **_kwargs):
        return {}


class _FakeRagStore:
    def __init__(self):
        self.data = {"updated_at": 0, "report": {}, "sources": {}}

    def search(self, _query, limit=5):
        return [{"source": "wikijs", "title": "Task", "text": "A task"}][:limit]

    def refresh(self):
        return {"ok": True}


class _FakeEngine:
    def process(self, text, _token, role, source, granted_permissions):
        return {"summary": f"engine:{text}:{role}:{source}:{len(granted_permissions)}", "data": {"route": "engine"}}


class ApiModuleRouterTests(unittest.TestCase):
    def test_auth_chat_router_handles_login_and_orb_guard(self):
        user_store = _FakeUserStore()
        password_store = _FakePasswordStore()
        password_store.set_password("usr-admin", "admin123")
        password_store.set_password("usr-user", "alice-pass")
        prefs = _FakePreferencesStore()
        audit = _FakeAuditLog()
        identity_tokens = {}
        tokens = {}
        chat_history = _FakeChatHistory()

        def require_identity_session(token):
            session = get_identity_session(token)
            if not session:
                raise HTTPException(401, "login required")
            return session

        def get_identity_session(token):
            if token == "sess-user":
                return {"token": token, "user": user_store.get_user("usr-user"), "role": "standard_user"}
            return None

        app = FastAPI()
        app.include_router(
            build_auth_chat_router(
                {
                    "ensure_default_admin_seeded": lambda: None,
                    "user_store": user_store,
                    "admin_password_store": password_store,
                    "audit_log": audit,
                    "issue_token": lambda: UnlockOut(token="unlock-token", expires_in_sec=60),
                    "token_fingerprint": lambda token: f"fp-{token}",
                    "issue_identity_token": lambda user_id, role: {"session_token": f"sess-{user_id}", "expires_in_sec": 60},
                    "user_preferences_store": prefs,
                    "identity_tokens": identity_tokens,
                    "require_identity_session": require_identity_session,
                    "normalize_role": lambda role: role or "guest_restricted",
                    "get_identity_session": get_identity_session,
                    "chat_owner_key": lambda session, guest: (f"user:{get_identity_session(session)['user']['id']}", get_identity_session(session)["user"]["id"]) if get_identity_session(session) else (f"guest:{guest or 'anonymous'}", None),
                    "chat_history": chat_history,
                    "rag_store": _FakeRagStore(),
                    "wakeword_enabled": lambda: False,
                    "wakeword_phrase": lambda: "hey jarvis",
                    "strip_wakeword": lambda text: (text, True),
                    "tokens": tokens,
                    "is_token_active": lambda _tokens, token: bool(token),
                    "resolve_effective_permissions": lambda *_args: set(),
                    "membership_store": object(),
                    "permission_store": object(),
                    "try_skill": lambda *_args, **_kwargs: None,
                    "rag_query_from_prompt": lambda _text: None,
                    "select_rag_hits": lambda *_args, **_kwargs: [],
                    "rag_needs_smart_llm": lambda _text: False,
                    "cloud_llm_available": lambda: False,
                    "format_rag_reply": lambda *_args, **_kwargs: "",
                    "rag_llm_answer": lambda *_args, **_kwargs: "",
                    "engine": _FakeEngine(),
                    "build_context_reply": lambda text: f"offline:{text}",
                    "get_provider": lambda: "local",
                    "local_ai_stub_reply": lambda text: f"local:{text}",
                    "get_gemini": lambda: None,
                    "get_openai": lambda: None,
                    "gemini_model": lambda: "gemini",
                    "openai_model": lambda: "gpt",
                    "openai_temperature": lambda: 0.3,
                    "openai_max_tokens": lambda: 120,
                    "system_prompt": lambda: "system",
                    "bearer_token_from_header": lambda auth: (auth or "").removeprefix("Bearer ").strip(),
                    "prune_expired_tokens": lambda _tokens: 0,
                    "passphrase": lambda: "test-pass",
                }
            )
        )
        client = TestClient(app)

        login = client.post("/auth/login", json={"username": "alice", "password": "alice-pass"})
        self.assertEqual(200, login.status_code)
        self.assertEqual("alice", login.json()["user"]["username"])

        orb_denied = client.post("/chat", headers={"X-Jarvis-Mode": "orb"}, json={"text": "hello", "source": "text"})
        self.assertEqual(401, orb_denied.status_code)

        orb_ok = client.post(
            "/chat",
            headers={"X-Jarvis-Mode": "orb", "X-Jarvis-Session": "sess-user"},
            json={"text": "hello", "source": "text"},
        )
        self.assertEqual(200, orb_ok.status_code)
        self.assertEqual("engine:hello:standard_user:text:0", orb_ok.json()["reply"])

    def test_admin_router_returns_status_summary(self):
        audit = _FakeAuditLog()
        user_store = _FakeUserStore()

        app = FastAPI()
        app.include_router(
            build_admin_router(
                {
                    "require_admin_access": lambda *_args, **_kwargs: ("usr-admin", "admin"),
                    "prepare_audit_filters": lambda event, role, actor_user_id, token_fingerprint: {
                        "event": event,
                        "role": role,
                        "actor_user_id": actor_user_id,
                        "token_fingerprint": token_fingerprint,
                    },
                    "validate_audit_query": lambda *_args: None,
                    "audit_log": audit,
                    "user_store": user_store,
                    "normalize_role": lambda role: role,
                    "audit_admin_event": lambda *_args, **_kwargs: None,
                    "admin_password_store": _FakePasswordStore(),
                    "user_preferences_store": _FakePreferencesStore(),
                    "membership_store": type("Memberships", (), {"list_memberships": lambda self: []})(),
                    "permission_store": type(
                        "Permissions",
                        (),
                        {
                            "list_group_permissions": lambda self: {},
                            "list_user_permissions": lambda self: {},
                        },
                    )(),
                    "group_store": type("Groups", (), {"list_groups": lambda self: []})(),
                    "known_permissions": {"assistant.chat"},
                    "get_active_user_or_raise": lambda store, user_id: store.get_user(user_id),
                    "build_permission_context": lambda *_args: {"effective": ["assistant.chat"]},
                    "permission_decision": lambda *_args: {"allowed": True, "source": "role"},
                    "settings_env_summary": lambda: {"voice": {"stt_provider": {"value": "local"}}},
                    "admin_settings_store": type("Settings", (), {"get": lambda self: {"voice": {}, "usage_limits": {}}})(),
                }
            )
        )
        client = TestClient(app)
        response = client.get("/admin/status/summary", headers={"Authorization": "Bearer tok", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": "usr-admin"})
        self.assertEqual(200, response.status_code)
        body = response.json()
        self.assertEqual(2, body["counts"]["users"])
        self.assertEqual("at_risk", body["counts"]["admin_lockout_state"])

    def test_voice_router_requires_session_for_orb_and_returns_tts(self):
        app = FastAPI()
        app.include_router(
            build_voice_router(
                {
                    "require_identity_session": lambda token: {"user": {"id": "usr-user"}} if token == "sess-user" else (_ for _ in ()).throw(HTTPException(401, "login required")),
                    "get_stt_provider": lambda: "local",
                    "transcribe_local": lambda _path: "status jarvis",
                    "transcribe_gemini": lambda _audio, _content_type: "gemini text",
                    "synthesize_tts": lambda text: f"wav:{text}".encode(),
                    "logger": type("Logger", (), {"exception": lambda self, _msg: None})(),
                    "subprocess": type(
                        "Subprocess",
                        (),
                        {
                            "DEVNULL": None,
                            "run": staticmethod(lambda *args, **kwargs: None),
                        },
                    )(),
                    "uuid4_hex": lambda: "abc123",
                }
            )
        )
        client = TestClient(app)

        denied = client.post(
            "/stt",
            headers={"X-Jarvis-Mode": "orb"},
            files={"file": ("audio.wav", b"abc", "audio/wav")},
        )
        self.assertEqual(401, denied.status_code)

        allowed = client.post(
            "/stt",
            headers={"X-Jarvis-Mode": "orb", "X-Jarvis-Session": "sess-user"},
            files={"file": ("audio.wav", b"abc", "audio/wav")},
        )
        self.assertEqual(200, allowed.status_code)
        self.assertEqual("status jarvis", allowed.json()["text"])

        tts = client.post("/tts", json={"text": "hello"})
        self.assertEqual(200, tts.status_code)
        self.assertEqual(b"wav:hello", tts.content)


if __name__ == "__main__":
    unittest.main()
