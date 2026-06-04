import io
import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.api_home_assistant import build_home_assistant_router
from jarvis.api_models import HomeAssistantDiscoveryCandidateIn, UnlockOut
from jarvis.api_voice import build_voice_router
from jarvis.runtime_state import JarvisStatusHub


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

    def get_pending_home_assistant_action(self, session_id, owner_key):
        session = self.get_session(session_id, owner_key)
        if not session:
            return None
        return session.get("pending_home_assistant_action")

    def set_pending_home_assistant_action(self, session_id, pending, owner_key, owner_user_id):
        session = self.ensure_session(session_id, owner_key, owner_user_id)
        session["pending_home_assistant_action"] = pending

    def clear_pending_home_assistant_action(self, session_id, owner_key, owner_user_id):
        session = self.ensure_session(session_id, owner_key, owner_user_id)
        session["pending_home_assistant_action"] = None

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


class _FakeHAStore:
    def __init__(self, calendar_items):
        self._calendar_items = calendar_items

    def list_calendar_items(self):
        return list(self._calendar_items)


class _FakeHomeAssistantService:
    def __init__(self):
        self.created = []
        self.entities = []
        self.items = []
        self.calendar_items = []
        self.inbox_items = []
        self.system_targets = []
        self.requests = []
        self.automations = []
        self.store = _FakeHAStore(self.calendar_items)

    def overview(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "counts": {"managed_entities": len(self.entities), "discovery_candidates": len(self.created), "shopping_list_items": len(self.items), "calendar_items": 0, "inbox_items": 0, "system_targets": len(self.system_targets), "control_requests": len(self.requests)}}

    def list_discovery_candidates(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.device_discovery")
        return {"policy": {"access_granted": True}, "candidates": list(self.created)}

    def create_discovery_candidate(self, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.device_discovery")
        item = {"id": f"cand-{len(self.created) + 1}", **payload}
        self.created.append(item)
        return {"policy": {"access_granted": True}, "candidate": item}

    def approve_discovery_candidate(self, candidate_id, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.integration_management")
        entity = {"entity_id": f"entity.{candidate_id}", "label": payload.get("label") or candidate_id, "kind": payload.get("kind") or "light", "area": payload.get("area") or ""}
        self.entities.append(entity)
        return {"policy": {"access_granted": True}, "candidate": {"id": candidate_id, "approval_status": "approved"}, "entity": entity}

    def list_managed_entities(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "entities": list(self.entities)}

    def list_shopping_list_items(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "items": list(self.items)}

    def add_shopping_list_item(self, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        item = {"id": f"item-{len(self.items) + 1}", **payload}
        self.items.append(item)
        return {"policy": {"access_granted": True}, "item": item}

    def add_calendar_item(self, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        item = {"id": f"cal-{len(self.calendar_items) + 1}", **payload}
        self.calendar_items.append(item)
        return {"policy": {"access_granted": True}, "item": item}

    def list_calendar_items(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "items": list(self.calendar_items)}

    def add_inbox_item(self, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        item = {"id": f"inbox-{len(self.inbox_items) + 1}", **payload}
        self.inbox_items.append(item)
        return {"policy": {"access_granted": True}, "item": item}

    def list_inbox_items(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "items": list(self.inbox_items)}

    def sync_managed_entities(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {
            "policy": {"access_granted": True},
            "entities": [{"entity_id": "entity.synced", "state": "on"}],
            "sync": {"configured": True, "synced_count": 1, "total_entities": 1, "timestamp": 1},
        }

    def list_control_requests(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "requests": list(self.requests)}

    def health_status(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {
            "policy": {"access_granted": True},
            "integration": {"configured": True, "mode": "external_home_assistant", "healthy": True, "base_url": "http://ha.local"},
            "health": {"managed_entities": 1, "unavailable_entities": 0, "pending_confirmations": len([r for r in self.requests if r.get("status") == "pending_confirmation"]), "configured": True},
            "alerts": {"unavailable_entities": [], "pending_requests": list(self.requests)},
        }

    def security_posture(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {
            "policy": {"access_granted": True},
            "security": {
                "confirmation_ttl_sec": 300,
                "remote_control_requires_capability": True,
                "system_control_preapproved_only": True,
                "remote_allowed_cidrs": [],
                "pending_confirmations": len([r for r in self.requests if r.get("status") == "pending_confirmation"]),
                "expired_confirmations": len([r for r in self.requests if r.get("status") == "expired"]),
            },
        }

    def device_profiles(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "profiles": {"light": {"actions": [{"action": "turn_on", "label": "Turn on", "risk_level": "medium", "remote": False}]}}}

    def system_target_profiles(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "profiles": {"pc": {"actions": [{"action": "restart", "label": "Restart", "risk_level": "high", "remote": True}]}}}

    def area_summary(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "areas": [{"area": "office", "entity_count": 1, "unavailable_count": 0, "kinds": ["light"]}]}

    def list_automation_rules(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "automations": list(getattr(self, "automations", []))}

    def create_automation_rule(self, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.automation_management")
        automations = getattr(self, "automations", [])
        item = {"id": f"auto-{len(automations) + 1}", "enabled": True, **payload}
        automations.append(item)
        self.automations = automations
        return {"policy": {"access_granted": True}, "automation": item}

    def toggle_automation_rule(self, rule_id, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.automation_management")
        for item in getattr(self, "automations", []):
            if item["id"] == rule_id:
                item["enabled"] = bool(payload.get("enabled", not item.get("enabled", True)))
                return {"policy": {"access_granted": True}, "automation": dict(item)}
        raise LookupError("automation rule not found")

    def list_recovery_playbooks(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {
            "policy": {"access_granted": True},
            "playbooks": [
                {"id": "sync_entities", "title": "Refresh entity states", "required_permission": "home_assistant.access", "risk_level": "low"},
                {"id": "disable_automations", "title": "Disable all automations", "required_permission": "home_assistant.automation_management", "risk_level": "medium"},
            ],
        }

    def execute_recovery_playbook(self, playbook_id, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {
            "policy": {"access_granted": True},
            "playbook": {"id": playbook_id, "title": playbook_id},
            "result": {"disabled_count": 1 if playbook_id == "disable_automations" else 0},
            "executed_at": 1,
        }

    def list_system_targets(self, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("home assistant access requires explicit permission")
        return {"policy": {"access_granted": True}, "targets": list(self.system_targets)}

    def create_system_target(self, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.integration_management")
        item = {"id": f"sys-{len(self.system_targets) + 1}", "status": "ready", **payload}
        self.system_targets.append(item)
        return {"policy": {"access_granted": True}, "target": item}

    def request_system_target_action(self, target_id, payload, *, user_id, role, client_ip=None):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.system_control")
        target = next((item for item in self.system_targets if item["id"] == target_id), None)
        if not target:
            raise LookupError("system target not found")
        if payload.get("action") not in set(target.get("allowed_actions", [])):
            raise ValueError("system action is not preapproved for this target")
        request = {
            "id": f"sys-req-{len(self.requests) + 1}",
            "request_type": "system_target",
            "target_id": target_id,
            "entity_id": target_id,
            "entity_label": target.get("label", target_id),
            "action": payload.get("action"),
            "risk_level": "high",
            "status": "pending_confirmation",
            "required_capability": "home_assistant.system_control",
        }
        self.requests.append(request)
        return {"policy": {"access_granted": True}, "request": request, "target": target, "executed": False}

    def request_entity_action(self, entity_id, payload, *, user_id, role, client_ip=None):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.device_control")
        request = {
            "id": f"req-{len(self.requests) + 1}",
            "entity_id": entity_id,
            "entity_label": entity_id,
            "action": payload.get("action"),
            "risk_level": "high" if payload.get("remote") else "medium",
            "status": "pending_confirmation" if payload.get("remote") else "executed",
        }
        self.requests.append(request)
        return {"policy": {"access_granted": True}, "request": request, "entity": {"entity_id": entity_id}, "executed": request["status"] == "executed"}

    def confirm_control_request(self, request_id, payload, *, user_id, role):
        if user_id != "usr-ha":
            raise PermissionError("missing permission: home_assistant.security_device_control")
        for item in self.requests:
            if item["id"] == request_id:
                item["status"] = "executed" if payload.get("confirmed", True) else "denied"
                return {"policy": {"access_granted": True}, "request": dict(item), "entity": {"entity_id": item["entity_id"]}, "executed": item["status"] == "executed"}
        raise LookupError("control request not found")


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
                    "home_assistant_service": _FakeHomeAssistantService(),
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
                    "local_ai_chat_reply": lambda messages, **_kw: f"local:{messages[-1]['content'] if messages else ''}",
                    "status_hub": JarvisStatusHub(),
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

    def test_auth_chat_router_handles_home_assistant_intents(self):
        user_store = _FakeUserStore()
        user_store.users["usr-ha"] = {"id": "usr-ha", "username": "ha", "role": "standard_user", "enabled": True}
        password_store = _FakePasswordStore()
        password_store.set_password("usr-ha", "ha-pass")
        prefs = _FakePreferencesStore()
        audit = _FakeAuditLog()
        chat_history = _FakeChatHistory()
        ha_service = _FakeHomeAssistantService()

        def get_identity_session(token):
            if token == "sess-ha":
                return {"token": token, "user": user_store.get_user("usr-ha"), "role": "standard_user"}
            return None

        def require_identity_session(token):
            session = get_identity_session(token)
            if not session:
                raise HTTPException(401, "login required")
            return session

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
                    "identity_tokens": {},
                    "require_identity_session": require_identity_session,
                    "normalize_role": lambda role: role or "guest_restricted",
                    "get_identity_session": get_identity_session,
                    "chat_owner_key": lambda session, guest: (f"user:{get_identity_session(session)['user']['id']}", get_identity_session(session)["user"]["id"]) if get_identity_session(session) else (f"guest:{guest or 'anonymous'}", None),
                    "chat_history": chat_history,
                    "rag_store": _FakeRagStore(),
                    "wakeword_enabled": lambda: False,
                    "wakeword_phrase": lambda: "hey jarvis",
                    "strip_wakeword": lambda text: (text, True),
                    "tokens": {},
                    "is_token_active": lambda _tokens, token: bool(token),
                    "resolve_effective_permissions": lambda *_args: {"home_assistant.access"},
                    "membership_store": object(),
                    "permission_store": object(),
                    "home_assistant_service": ha_service,
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
                    "local_ai_chat_reply": lambda messages, **_kw: f"local:{messages[-1]['content'] if messages else ''}",
                    "status_hub": JarvisStatusHub(),
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

        sync_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, synchronisiere meine Home-Assistant-Geräte", "source": "text"},
        )
        self.assertEqual(200, sync_response.status_code)
        self.assertIn("synchronisiert", sync_response.json()["reply"])

        calendar_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, erstelle morgen um 09:00 einen Kalendereintrag für Wartung", "source": "text"},
        )
        self.assertEqual(200, calendar_response.status_code)
        self.assertIn("Kalendereintrag angelegt", calendar_response.json()["reply"])
        self.assertIn("T09:00:00Z", calendar_response.json()["reply"])

        weekday_calendar_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, plane am Freitag abends einen Termin für Team Essen", "source": "text"},
        )
        self.assertEqual(200, weekday_calendar_response.status_code)
        self.assertIn("Team Essen", weekday_calendar_response.json()["reply"])
        self.assertIn("T19:00:00Z", weekday_calendar_response.json()["reply"])

        inbox_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, erstelle eine Inbox-Nachricht für Technik-Team Update", "source": "text"},
        )
        self.assertEqual(200, inbox_response.status_code)
        self.assertIn("Inbox-Eintrag angelegt", inbox_response.json()["reply"])

        shopping_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, füge Milch zur Einkaufsliste hinzu", "source": "text"},
        )
        self.assertEqual(200, shopping_response.status_code)
        self.assertIn("Einkaufslisten-Eintrag angelegt", shopping_response.json()["reply"])

        calendar_list_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, zeige meinen Kalender", "source": "text"},
        )
        self.assertEqual(200, calendar_list_response.status_code)
        self.assertIn("Kalendereinträge", calendar_list_response.json()["reply"])

        inbox_list_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, zeige meine Inbox", "source": "text"},
        )
        self.assertEqual(200, inbox_list_response.status_code)
        self.assertIn("Inbox", inbox_list_response.json()["reply"])

        ha_service.entities.append({"entity_id": "entity.living_room_lamp", "label": "Lampe Wohnzimmer", "kind": "light"})
        ha_service.entities.append({"entity_id": "entity.lock.frontdoor", "label": "Haustür", "kind": "lock"})
        ha_service.entities.append({"entity_id": "entity.garage.main", "label": "Garage", "kind": "garage_door"})
        switch_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, schalte die Lampe Wohnzimmer aus", "source": "text"},
        )
        self.assertEqual(200, switch_response.status_code)
        self.assertIn("ausgeschaltet", switch_response.json()["reply"])

        unlock_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, entriegle die Haustür", "source": "text"},
        )
        self.assertEqual(200, unlock_response.status_code)
        self.assertIn("Freigabe", unlock_response.json()["reply"])

        open_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, öffne die Garage", "source": "text"},
        )
        self.assertEqual(200, open_response.status_code)
        self.assertIn("Freigabe", open_response.json()["reply"])

        missing_entity_action_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, schalte die Haustür", "source": "text"},
        )
        self.assertEqual(200, missing_entity_action_response.status_code)
        self.assertIn("Mögliche Aktionen", missing_entity_action_response.json()["reply"])

        followup_session_id = missing_entity_action_response.json()["session_id"]
        entity_followup_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"session_id": followup_session_id, "text": "Entriegeln", "source": "text"},
        )
        self.assertEqual(200, entity_followup_response.status_code)
        self.assertIn("Freigabe", entity_followup_response.json()["reply"])

        pending_calendar_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, erstelle einen Kalendereintrag", "source": "text"},
        )
        self.assertEqual(200, pending_calendar_response.status_code)
        self.assertIn("Titel und eine Zeitangabe", pending_calendar_response.json()["reply"])

        calendar_followup_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"session_id": pending_calendar_response.json()["session_id"], "text": "Morgen um 10:00 für Wartung", "source": "text"},
        )
        self.assertEqual(200, calendar_followup_response.status_code)
        self.assertIn("Kalendereintrag angelegt", calendar_followup_response.json()["reply"])
        self.assertIn("Wartung", calendar_followup_response.json()["reply"])

        pending_inbox_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, erstelle eine Inbox-Nachricht", "source": "text"},
        )
        self.assertEqual(200, pending_inbox_response.status_code)
        self.assertIn("Inbox-Nachricht", pending_inbox_response.json()["reply"])

        inbox_followup_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"session_id": pending_inbox_response.json()["session_id"], "text": "Server Update", "source": "text"},
        )
        self.assertEqual(200, inbox_followup_response.status_code)
        self.assertIn("Inbox-Eintrag angelegt", inbox_followup_response.json()["reply"])
        self.assertIn("Server Update", inbox_followup_response.json()["reply"])

        pending_shopping_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, füge etwas zur Einkaufsliste hinzu", "source": "text"},
        )
        self.assertEqual(200, pending_shopping_response.status_code)
        self.assertIn("Einkaufsliste", pending_shopping_response.json()["reply"])

        shopping_followup_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"session_id": pending_shopping_response.json()["session_id"], "text": "Kaffee", "source": "text"},
        )
        self.assertEqual(200, shopping_followup_response.status_code)
        self.assertIn("Einkaufslisten-Eintrag angelegt", shopping_followup_response.json()["reply"])
        self.assertIn("Kaffee", shopping_followup_response.json()["reply"])

        ha_service.requests.append({
            "id": "req-99",
            "entity_id": "entity.living_room_lamp",
            "entity_label": "Lampe Wohnzimmer",
            "action": "turn_on",
            "risk_level": "high",
            "status": "pending_confirmation",
        })
        confirm_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, bestätige die Freigabe für Lampe Wohnzimmer", "source": "text"},
        )
        self.assertEqual(200, confirm_response.status_code)
        self.assertIn("bestätigt", confirm_response.json()["reply"])

        create_automation_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, erstelle Automation Abendlicht im Wohnzimmer", "source": "text"},
        )
        self.assertEqual(200, create_automation_response.status_code)
        self.assertIn("Automation angelegt", create_automation_response.json()["reply"])

        pending_automation_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, erstelle eine Automation", "source": "text"},
        )
        self.assertEqual(200, pending_automation_response.status_code)
        self.assertIn("Automation heißen", pending_automation_response.json()["reply"])

        automation_followup_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"session_id": pending_automation_response.json()["session_id"], "text": "Nachtlicht", "source": "text"},
        )
        self.assertEqual(200, automation_followup_response.status_code)
        self.assertIn("Automation angelegt", automation_followup_response.json()["reply"])
        self.assertIn("Nachtlicht", automation_followup_response.json()["reply"])

        list_automation_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, zeige meine Automationen", "source": "text"},
        )
        self.assertEqual(200, list_automation_response.status_code)
        self.assertIn("Automationen", list_automation_response.json()["reply"])

        toggle_automation_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, deaktiviere Automation Abendlicht im Wohnzimmer", "source": "text"},
        )
        self.assertEqual(200, toggle_automation_response.status_code)
        self.assertIn("deaktiviert", toggle_automation_response.json()["reply"])

        list_recovery_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, zeige die Recovery Playbooks", "source": "text"},
        )
        self.assertEqual(200, list_recovery_response.status_code)
        self.assertIn("Wiederherstellungen", list_recovery_response.json()["reply"])

        execute_recovery_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, führe das Playbook Refresh entity states aus", "source": "text"},
        )
        self.assertEqual(200, execute_recovery_response.status_code)
        self.assertIn("Wiederherstellung ausgeführt", execute_recovery_response.json()["reply"])

        ha_service.system_targets.append({"id": "sys-1", "label": "Office PC", "status": "ready", "allowed_actions": ["restart"]})
        list_systems_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, zeige meine Systeme", "source": "text"},
        )
        self.assertEqual(200, list_systems_response.status_code)
        self.assertIn("Systeme", list_systems_response.json()["reply"])

        system_action_response = client.post(
            "/chat",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"text": "Jarvis, starte das System Office PC neu", "source": "text"},
        )
        self.assertEqual(200, system_action_response.status_code)
        self.assertIn("Freigabe", system_action_response.json()["reply"])

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
                    "synthesize_tts": lambda text, voice="": f"wav:{text}".encode(),
                    "get_identity_session": lambda _token: None,
                    "user_preferences_store": None,
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
                    "status_hub": JarvisStatusHub(),
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

    def test_home_assistant_router_enforces_session_and_permissions(self):
        def require_identity_session(token):
            if token == "sess-ha":
                return {"user": {"id": "usr-ha", "role": "standard_user"}, "role": "standard_user"}
            if token == "sess-user":
                return {"user": {"id": "usr-user", "role": "standard_user"}, "role": "standard_user"}
            raise HTTPException(401, "login required")

        app = FastAPI()
        app.include_router(
            build_home_assistant_router(
                {
                    "require_identity_session": require_identity_session,
                    "home_assistant_service": _FakeHomeAssistantService(),
                }
            )
        )
        client = TestClient(app)

        denied = client.get("/home-assistant/overview", headers={"X-Jarvis-Session": "sess-user"})
        self.assertEqual(403, denied.status_code)

        allowed = client.get("/home-assistant/overview", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, allowed.status_code)
        self.assertTrue(allowed.json()["policy"]["access_granted"])

        created = client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": "sess-ha"},
            json=HomeAssistantDiscoveryCandidateIn(
                ip_address="10.0.0.15",
                label="Desk Lamp",
                suggested_type="light",
                suggested_area="office",
            ).model_dump(),
        )
        self.assertEqual(200, created.status_code)
        self.assertEqual("Desk Lamp", created.json()["candidate"]["label"])

        approved = client.post(
            "/home-assistant/discovery/candidates/cand-1/approve",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"label": "Desk Lamp", "kind": "light", "area": "office"},
        )
        self.assertEqual(200, approved.status_code)
        self.assertEqual("approved", approved.json()["candidate"]["approval_status"])

        entities = client.get("/home-assistant/entities", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, entities.status_code)
        self.assertEqual(1, len(entities.json()["entities"]))

        shopping = client.post(
            "/home-assistant/shopping-list/items",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"title": "Milk"},
        )
        self.assertEqual(200, shopping.status_code)

        system_target = client.post(
            "/home-assistant/system-targets",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"label": "Office PC", "target_kind": "pc", "allowed_actions": ["restart"]},
        )
        self.assertEqual(200, system_target.status_code)
        target_id = system_target.json()["target"]["id"]

        system_profiles = client.get("/home-assistant/system-target-profiles", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, system_profiles.status_code)
        self.assertIn("pc", system_profiles.json()["profiles"])

        system_action = client.post(
            f"/home-assistant/system-targets/{target_id}/actions",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"action": "restart", "remote": True},
        )
        self.assertEqual(200, system_action.status_code)
        self.assertFalse(system_action.json()["executed"])

        shopping_items = client.get("/home-assistant/shopping-list", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, shopping_items.status_code)
        self.assertEqual("Milk", shopping_items.json()["items"][0]["title"])

        synced = client.post("/home-assistant/sync/entities", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, synced.status_code)
        self.assertEqual(1, synced.json()["sync"]["synced_count"])

        health = client.get("/home-assistant/health", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, health.status_code)
        self.assertTrue(health.json()["health"]["configured"])

        profiles = client.get("/home-assistant/device-profiles", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, profiles.status_code)
        self.assertIn("light", profiles.json()["profiles"])

        areas = client.get("/home-assistant/areas", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, areas.status_code)
        self.assertEqual("office", areas.json()["areas"][0]["area"])

        automation = client.post(
            "/home-assistant/automations",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"name": "Evening lights", "target_area": "office"},
        )
        self.assertEqual(200, automation.status_code)

        automations = client.get("/home-assistant/automations", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, automations.status_code)
        self.assertEqual(1, len(automations.json()["automations"]))

        toggled = client.post(
            "/home-assistant/automations/auto-1/toggle",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"enabled": False},
        )
        self.assertEqual(200, toggled.status_code)
        self.assertFalse(toggled.json()["automation"]["enabled"])

        playbooks = client.get("/home-assistant/recovery-playbooks", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, playbooks.status_code)
        self.assertEqual(2, len(playbooks.json()["playbooks"]))

        executed = client.post("/home-assistant/recovery-playbooks/disable_automations/execute", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, executed.status_code)
        self.assertEqual(1, executed.json()["result"]["disabled_count"])

        action = client.post(
            "/home-assistant/entities/entity.cand-1/actions",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"action": "unlock", "remote": True},
        )
        self.assertEqual(200, action.status_code)
        self.assertFalse(action.json()["executed"])

        queue = client.get("/home-assistant/control-requests", headers={"X-Jarvis-Session": "sess-ha"})
        self.assertEqual(200, queue.status_code)
        self.assertEqual(2, len(queue.json()["requests"]))

        confirm = client.post(
            "/home-assistant/control-requests/req-2/confirm",
            headers={"X-Jarvis-Session": "sess-ha"},
            json={"confirmed": True},
        )
        self.assertEqual(200, confirm.status_code)
        self.assertTrue(confirm.json()["executed"])


class DailyBriefingEndpointTests(unittest.TestCase):
    def _make_client(self, briefing_text="Good morning, sir.", ha_service=None):
        user_store = _FakeUserStore()
        user_store.users["usr-1"] = {"id": "usr-1", "username": "alice", "role": "standard_user", "enabled": True}
        prefs = _FakePreferencesStore()
        audit = _FakeAuditLog()

        def get_identity_session(token):
            if token == "sess-1":
                return {"token": token, "user": user_store.get_user("usr-1"), "role": "standard_user"}
            return None

        app = FastAPI()
        app.include_router(
            build_auth_chat_router({
                "ensure_default_admin_seeded": lambda: None,
                "user_store": user_store,
                "admin_password_store": _FakePasswordStore(),
                "audit_log": audit,
                "issue_token": lambda: UnlockOut(token="t", expires_in_sec=60),
                "token_fingerprint": lambda t: f"fp-{t}",
                "issue_identity_token": lambda uid, role: {"session_token": f"sess-{uid}", "expires_in_sec": 60},
                "user_preferences_store": prefs,
                "identity_tokens": {},
                "require_identity_session": lambda t: (_ for _ in ()).throw(HTTPException(401)) if not get_identity_session(t) else get_identity_session(t),
                "normalize_role": lambda role: role or "guest_restricted",
                "get_identity_session": get_identity_session,
                "chat_owner_key": lambda s, g: (f"user:{get_identity_session(s)['user']['id']}", get_identity_session(s)["user"]["id"]) if get_identity_session(s) else (f"guest:{g or 'anon'}", None),
                "chat_history": _FakeChatHistory(),
                "rag_store": _FakeRagStore(),
                "wakeword_enabled": lambda: False,
                "wakeword_phrase": lambda: "hey jarvis",
                "strip_wakeword": lambda t: (t, True),
                "tokens": {},
                "is_token_active": lambda _t, tok: bool(tok),
                "resolve_effective_permissions": lambda *_: set(),
                "membership_store": object(),
                "permission_store": object(),
                "home_assistant_service": ha_service,
                "try_skill": lambda text, **_kw: {"reply": briefing_text} if "briefing" in text else None,
                "rag_query_from_prompt": lambda _t: None,
                "select_rag_hits": lambda *_a, **_k: [],
                "rag_needs_smart_llm": lambda _t: False,
                "cloud_llm_available": lambda: False,
                "format_rag_reply": lambda *_a, **_k: "",
                "rag_llm_answer": lambda *_a, **_k: "",
                "engine": _FakeEngine(),
                "build_context_reply": lambda t: f"offline:{t}",
                "get_provider": lambda: "local",
                "local_ai_stub_reply": lambda t: f"local:{t}",
                "local_ai_chat_reply": lambda msgs, **_k: f"local:{msgs[-1]['content'] if msgs else ''}",
                "status_hub": JarvisStatusHub(),
                "get_gemini": lambda: None,
                "get_openai": lambda: None,
                "gemini_model": lambda: "gemini",
                "openai_model": lambda: "gpt",
                "openai_temperature": lambda: 0.3,
                "openai_max_tokens": lambda: 120,
                "system_prompt": lambda: "system",
                "bearer_token_from_header": lambda auth: (auth or "").removeprefix("Bearer ").strip(),
                "prune_expired_tokens": lambda _t: 0,
                "passphrase": lambda: "test-pass",
            })
        )
        return TestClient(app)

    def test_daily_briefing_returns_text_and_date(self):
        client = self._make_client(briefing_text="Good morning, sir. All systems nominal.")
        resp = client.get("/chat/daily-briefing", headers={"X-Jarvis-Session": "sess-1"})
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertIn("text", data)
        self.assertIn("date", data)
        self.assertEqual("Good morning, sir. All systems nominal.", data["text"])
        import re
        self.assertRegex(data["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_daily_briefing_without_auth_uses_guest_role(self):
        client = self._make_client(briefing_text="Good day, sir.")
        resp = client.get("/chat/daily-briefing")
        self.assertEqual(200, resp.status_code)
        self.assertIn("text", resp.json())

    def test_daily_briefing_appends_todays_calendar_events(self):
        from datetime import date
        today = date.today().isoformat()
        ha_service = _FakeHomeAssistantService()
        ha_service.calendar_items.append({"id": "ev-1", "title": "Team Standup", "starts_at": f"{today}T09:00:00Z"})
        client = self._make_client(briefing_text="Good morning, sir.", ha_service=ha_service)
        resp = client.get("/chat/daily-briefing", headers={"X-Jarvis-Session": "sess-1"})
        self.assertEqual(200, resp.status_code)
        text = resp.json()["text"]
        self.assertIn("Team Standup", text)
        self.assertIn("09:00", text)

    def test_daily_briefing_ignores_past_calendar_events(self):
        ha_service = _FakeHomeAssistantService()
        ha_service.calendar_items.append({"id": "ev-old", "title": "Old Meeting", "starts_at": "2024-01-01T09:00:00Z"})
        client = self._make_client(briefing_text="Good morning, sir.", ha_service=ha_service)
        resp = client.get("/chat/daily-briefing", headers={"X-Jarvis-Session": "sess-1"})
        self.assertEqual(200, resp.status_code)
        self.assertNotIn("Old Meeting", resp.json()["text"])


if __name__ == "__main__":
    unittest.main()
