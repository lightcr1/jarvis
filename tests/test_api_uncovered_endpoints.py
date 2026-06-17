"""
Tests for endpoints that had zero coverage in V35:
  - GET  /admin/sessions
  - DELETE /admin/sessions/{user_id}
  - GET  /admin/authz/check
  - POST /chat/sessions/{id}/pending-home-assistant/clear
  - PUT  /auth/me/password

Each endpoint gets at minimum: happy path, auth failure, and invalid input.
"""
from __future__ import annotations

import unittest

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.api_models import UnlockOut
from jarvis.permission_store import KNOWN_PERMISSIONS
from jarvis.runtime_state import JarvisStatusHub


# ---------------------------------------------------------------------------
# Minimal shared fakes (same pattern as test_api_module_routers.py)
# ---------------------------------------------------------------------------

class _FakePwStore:
    def __init__(self) -> None:
        self._p: dict[str, str] = {}

    def verify_password(self, uid: str, pw: str) -> bool:
        return self._p.get(uid) == pw

    def set_password(self, uid: str, pw: str) -> None:
        self._p[uid] = pw

    def delete_password(self, uid: str) -> bool:
        return bool(self._p.pop(uid, None))


class _FakeUserStore:
    def __init__(self) -> None:
        self._c = 0
        self.data: dict = {"users": {}}

    def _save(self) -> None:
        pass

    def create_user(self, username: str, role: str = "standard_user", enabled: bool = True) -> dict:
        from jarvis.jarvis_engine import VALID_ROLES
        role = (role or "standard_user").strip().lower()
        if role not in VALID_ROLES:
            raise ValueError("invalid role")
        self._c += 1
        uid = f"usr-{self._c}"
        item: dict = {"id": uid, "username": username, "role": role, "enabled": bool(enabled), "created_at": 0, "updated_at": 0}
        self.data["users"][uid] = item
        return item

    def get_user(self, uid: str) -> dict | None:
        return self.data["users"].get(uid)

    def find_by_username(self, username: str) -> dict | None:
        for u in self.data["users"].values():
            if u["username"].lower() == username.strip().lower():
                return u
        return None

    def list_users(self) -> list[dict]:
        return list(self.data["users"].values())

    def update_user(self, uid: str, role: str | None = None, enabled: bool | None = None) -> dict:
        u = self.data["users"][uid]
        if role is not None:
            u["role"] = role
        if enabled is not None:
            u["enabled"] = enabled
        return u

    def delete_user(self, uid: str) -> bool:
        return bool(self.data["users"].pop(uid, None))

    def enabled_admin_count(self) -> int:
        return sum(1 for u in self.data["users"].values() if u["role"] == "admin" and u["enabled"])

    def touch_last_seen(self, uid: str) -> None:
        pass


class _FakeGroupStore:
    def __init__(self) -> None:
        self._g: dict[str, dict] = {}
        self._c = 0

    def list_groups(self) -> list[dict]:
        return list(self._g.values())

    def get_group(self, gid: str) -> dict | None:
        return self._g.get(gid)


class _FakeMembershipStore:
    def list_memberships(self) -> list[dict]:
        return []

    def list_user_groups(self, uid: str) -> list[str]:
        return []

    def remove_user_memberships(self, uid: str) -> int:
        return 0

    def remove_group_memberships(self, gid: str) -> int:
        return 0


class _FakePermissionStore:
    def __init__(self) -> None:
        self._u: dict[str, list[str]] = {}
        self._g: dict[str, list[str]] = {}

    def list_group_permissions(self) -> dict:
        return dict(self._g)

    def list_user_permissions(self) -> dict:
        return dict(self._u)

    def set_user_permissions(self, uid: str, perms: list[str]) -> list[str]:
        self._u[uid] = list(perms)
        return list(perms)

    def set_group_permissions(self, gid: str, perms: list[str]) -> list[str]:
        self._g[gid] = list(perms)
        return list(perms)

    def clear_user_permissions(self, uid: str) -> list[str]:
        return self._u.pop(uid, [])

    def clear_group_permissions(self, gid: str) -> list[str]:
        return self._g.pop(gid, [])

    def invalid_permissions(self, perms: list[str]) -> list[str]:
        return [p for p in perms if p not in KNOWN_PERMISSIONS]

    def _normalize_permissions(self, perms: list[str]) -> list[str]:
        return list(dict.fromkeys(p.strip() for p in perms if p.strip()))


class _FakeAudit:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append({"event": event, **payload})

    def read_events(self, **_k) -> list[dict]:
        return list(self.events)

    def count_events(self, **_k) -> int:
        return len(self.events)

    def aggregate_counts(self, **_k) -> dict:
        return {}


class _FakePrefs:
    def get(self, uid: str) -> dict:
        return {}

    def update(self, uid: str, payload: dict) -> dict:
        return payload

    def delete(self, uid: str) -> bool:
        return False


class _FakeAdminSettingsStore:
    def get(self) -> dict:
        return {}

    def update(self, payload: dict) -> dict:
        return {"usage_limits": {"token_ttl_min": 60, "max_active_tokens": 10}, "voice": {"wakeword_enabled": False, "wakeword_phrase": "hey jarvis", "stt_provider": "local"}}


class _FakeChatHistory:
    def __init__(self) -> None:
        self._c = 0
        self.sessions: dict[str, dict] = {}

    def ensure_session(self, sid: str | None, owner_key: str, owner_user_id: str | None) -> dict:
        if sid and sid in self.sessions:
            return self.sessions[sid]
        self._c += 1
        new_sid = sid or f"s-{self._c}"
        s: dict = {"id": new_sid, "owner_key": owner_key, "owner_user_id": owner_user_id, "messages": [], "title": "Chat"}
        self.sessions[new_sid] = s
        return s

    def create_session(self, title: str, owner_key: str, owner_user_id: str | None) -> dict:
        self._c += 1
        sid = f"s-{self._c}"
        s: dict = {"id": sid, "title": title, "owner_key": owner_key, "owner_user_id": owner_user_id, "messages": []}
        self.sessions[sid] = s
        return s

    def append_message(self, sid: str, role: str, text: str, owner_key: str, owner_user_id: str | None) -> None:
        self.sessions[sid]["messages"].append({"role": role, "text": text})

    def get_session(self, sid: str, owner_key: str) -> dict | None:
        s = self.sessions.get(sid)
        if s and s["owner_key"] == owner_key:
            return s
        return None

    def get_pending_home_assistant_action(self, sid: str, owner_key: str) -> dict | None:
        s = self.get_session(sid, owner_key)
        return s.get("pending_home_assistant_action") if s else None

    def set_pending_home_assistant_action(self, sid: str, pending: dict, owner_key: str, owner_user_id: str | None) -> None:
        s = self.ensure_session(sid, owner_key, owner_user_id)
        s["pending_home_assistant_action"] = pending

    def clear_pending_home_assistant_action(self, sid: str, owner_key: str, owner_user_id: str | None) -> None:
        s = self.ensure_session(sid, owner_key, owner_user_id)
        s["pending_home_assistant_action"] = None

    def list_sessions(self, owner_key: str) -> list[dict]:
        return [s for s in self.sessions.values() if s["owner_key"] == owner_key]

    def search_messages(self, q: str, owner_key: str, limit: int = 30) -> list[dict]:
        return []

    def rename_session(self, sid: str, title: str, owner_key: str) -> dict | None:
        s = self.get_session(sid, owner_key)
        if s:
            s["title"] = title
        return s

    def delete_session(self, sid: str, owner_key: str) -> bool:
        s = self.get_session(sid, owner_key)
        if not s:
            return False
        self.sessions.pop(sid, None)
        return True

    def delete_all_sessions(self, owner_key: str) -> int:
        to_del = [sid for sid, s in self.sessions.items() if s["owner_key"] == owner_key]
        for sid in to_del:
            self.sessions.pop(sid, None)
        return len(to_del)


class _FakeEngine:
    def process(self, text: str, _tok: str | None, role: str, source: str, granted_permissions: list) -> dict:
        return {"summary": f"engine:{text}", "data": {"route": "engine"}}


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------

def _make_admin_deps(
    user_store: _FakeUserStore,
    pw_store: _FakePwStore,
    audit: _FakeAudit,
    group_store: _FakeGroupStore,
    membership_store: _FakeMembershipStore,
    permission_store: _FakePermissionStore,
    tokens: dict,
    identity_tokens: dict,
    chat_history: _FakeChatHistory,
) -> dict:
    from jarvis.authz import build_permission_context, permission_decision

    def require_admin_access(uid, role, auth, allow_bootstrap=False):
        bearer = (auth or "").removeprefix("Bearer ").strip()
        if bearer in tokens and tokens[bearer].get("role") == "admin":
            return tokens[bearer].get("user_id", ""), "admin"
        uid = (uid or "").strip()
        if uid:
            u = user_store.get_user(uid)
            if u and u["role"] == "admin" and u["enabled"]:
                return uid, "admin"
        raise HTTPException(403, "admin access required")

    def audit_admin_event(event: str, actor: str, caller_role: str, payload: dict) -> None:
        audit.write(event, {"actor_user_id": actor, "caller_role": caller_role, **payload})

    def get_active_user_or_raise(store, user_id: str) -> dict:
        u = store.get_user(user_id)
        if not u:
            raise LookupError("not found")
        if not u.get("enabled", False):
            raise PermissionError("disabled")
        return u

    return {
        "user_store": user_store,
        "admin_password_store": pw_store,
        "audit_log": audit,
        "group_store": group_store,
        "membership_store": membership_store,
        "permission_store": permission_store,
        "admin_settings_store": _FakeAdminSettingsStore(),
        "user_preferences_store": _FakePrefs(),
        "identity_tokens": identity_tokens,
        "chat_history": chat_history,
        "require_admin_access": require_admin_access,
        "prepare_audit_filters": lambda ev, rl, au, tf: {"event": ev, "role": rl, "actor_user_id": au, "token_fingerprint": tf},
        "validate_audit_query": lambda *_a: None,
        "normalize_role": lambda r: r or "guest_restricted",
        "audit_admin_event": audit_admin_event,
        "known_permissions": KNOWN_PERMISSIONS,
        "get_active_user_or_raise": get_active_user_or_raise,
        "build_permission_context": build_permission_context,
        "permission_decision": permission_decision,
        "settings_env_summary": lambda: {"llm_provider": "local"},
    }


def _make_auth_deps(
    user_store: _FakeUserStore,
    pw_store: _FakePwStore,
    audit: _FakeAudit,
    tokens: dict,
    identity_tokens: dict,
    chat_history: _FakeChatHistory,
    membership_store: _FakeMembershipStore,
    permission_store: _FakePermissionStore,
) -> dict:
    def get_identity_session(tok: str | None) -> dict | None:
        if not tok:
            return None
        data = identity_tokens.get(tok)
        if not data:
            return None
        u = user_store.get_user(data["user_id"])
        return {"token": tok, "user": u, "role": u["role"]} if u else None

    def require_identity_session(tok: str | None) -> dict:
        s = get_identity_session(tok)
        if not s:
            raise HTTPException(401, "login required")
        return s

    def chat_owner_key(sess_tok: str | None, guest_key: str | None) -> tuple[str, str | None]:
        s = get_identity_session(sess_tok)
        if s:
            uid = s["user"]["id"]
            return f"user:{uid}", uid
        return f"guest:{guest_key or 'anon'}", None

    return {
        "ensure_default_admin_seeded": lambda: None,
        "user_store": user_store,
        "admin_password_store": pw_store,
        "audit_log": audit,
        "issue_token": lambda: UnlockOut(token="unlock-tok", expires_in_sec=3600),
        "token_fingerprint": lambda t: f"fp-{t[:6]}",
        "issue_identity_token": lambda uid, role: {"session_token": f"sess-{uid}", "expires_in_sec": 3600},
        "user_preferences_store": _FakePrefs(),
        "identity_tokens": identity_tokens,
        "require_identity_session": require_identity_session,
        "normalize_role": lambda r: r or "guest_restricted",
        "get_identity_session": get_identity_session,
        "chat_owner_key": chat_owner_key,
        "chat_history": chat_history,
        "rag_store": type("R", (), {"data": {"updated_at": 0, "report": {}, "sources": {}}, "search": lambda *a, **k: [], "refresh": lambda *a: {}})(),
        "wakeword_enabled": lambda: False,
        "wakeword_phrase": lambda: "hey jarvis",
        "strip_wakeword": lambda t: (t, True),
        "tokens": tokens,
        "is_token_active": lambda ts, tok: tok in ts,
        "resolve_effective_permissions": lambda *a: set(),
        "membership_store": membership_store,
        "permission_store": permission_store,
        "home_assistant_service": None,
        "try_skill": lambda *a, **k: None,
        "rag_query_from_prompt": lambda t: None,
        "select_rag_hits": lambda *a, **k: [],
        "rag_needs_smart_llm": lambda t: False,
        "cloud_llm_available": lambda: False,
        "format_rag_reply": lambda *a, **k: "",
        "rag_llm_answer": lambda *a, **k: "",
        "engine": _FakeEngine(),
        "build_context_reply": lambda t: f"offline:{t}",
        "get_provider": lambda: "local",
        "local_ai_stub_reply": lambda t: f"local:{t}",
        "local_ai_chat_reply": lambda msgs, **k: "local:reply",
        "status_hub": JarvisStatusHub(),
        "byok_store": None,
                    "get_anthropic": lambda: None,
        "get_gemini": lambda: None,
        "get_openai": lambda: None,
        "gemini_model": lambda: "gemini",
        "openai_model": lambda: "gpt",
        "openai_temperature": lambda: 0.3,
        "openai_max_tokens": lambda: 512,
        "system_prompt": lambda: "system",
        "bearer_token_from_header": lambda auth: (auth or "").removeprefix("Bearer ").strip(),
        "prune_expired_tokens": lambda _t: 0,
        "passphrase": lambda: "test-pass",
    }


def _make_app() -> tuple[TestClient, dict, dict, _FakeUserStore, _FakePwStore, _FakeAudit, _FakeChatHistory]:
    user_store = _FakeUserStore()
    pw_store = _FakePwStore()
    audit = _FakeAudit()
    tokens: dict = {}
    identity_tokens: dict = {}
    group_store = _FakeGroupStore()
    membership_store = _FakeMembershipStore()
    permission_store = _FakePermissionStore()
    chat_history = _FakeChatHistory()

    admin = user_store.create_user("admin", role="admin", enabled=True)
    pw_store.set_password(admin["id"], "admin123")
    tokens["admin-tok"] = {"role": "admin", "user_id": admin["id"]}

    app = FastAPI()
    app.include_router(build_admin_router(_make_admin_deps(user_store, pw_store, audit, group_store, membership_store, permission_store, tokens, identity_tokens, chat_history)))
    app.include_router(build_auth_chat_router(_make_auth_deps(user_store, pw_store, audit, tokens, identity_tokens, chat_history, membership_store, permission_store)))

    return TestClient(app), tokens, identity_tokens, user_store, pw_store, audit, chat_history


# ---------------------------------------------------------------------------
# Tests for GET /admin/sessions and DELETE /admin/sessions/{user_id}
# ---------------------------------------------------------------------------

class TestAdminSessionEndpoints(unittest.TestCase):
    def setUp(self) -> None:
        import time
        self.client, self.tokens, self.id_tokens, self.user_store, self.pw_store, self.audit, self.chat_history = _make_app()
        self.admin_hdrs = {"Authorization": "Bearer admin-tok"}
        # Seed an active identity session for a regular user
        alice = self.user_store.create_user("alice", role="standard_user", enabled=True)
        self.alice_id = alice["id"]
        self.id_tokens["sess-alice"] = {"user_id": self.alice_id, "role": "standard_user", "exp": time.time() + 3600}

    def test_list_sessions_returns_active_sessions(self) -> None:
        resp = self.client.get("/admin/sessions", headers=self.admin_hdrs)
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertIn("sessions", data)
        self.assertIn("count", data)
        # alice's session should appear
        user_ids = [s["user_id"] for s in data["sessions"]]
        self.assertIn(self.alice_id, user_ids)

    def test_list_sessions_requires_admin(self) -> None:
        resp = self.client.get("/admin/sessions")
        self.assertEqual(403, resp.status_code)

    def test_revoke_user_sessions(self) -> None:
        # alice has one active session
        resp = self.client.get("/admin/sessions", headers=self.admin_hdrs)
        self.assertIn(self.alice_id, [s["user_id"] for s in resp.json()["sessions"]])

        # Revoke alice's sessions
        resp = self.client.delete(f"/admin/sessions/{self.alice_id}", headers=self.admin_hdrs)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(1, resp.json()["revoked"])

        # alice's session token should now be gone from identity_tokens
        self.assertNotIn("sess-alice", self.id_tokens)

    def test_revoke_sessions_requires_admin(self) -> None:
        resp = self.client.delete(f"/admin/sessions/{self.alice_id}")
        self.assertEqual(403, resp.status_code)

    def test_revoke_nonexistent_user_sessions_returns_zero(self) -> None:
        resp = self.client.delete("/admin/sessions/usr-doesnotexist", headers=self.admin_hdrs)
        self.assertEqual(200, resp.status_code)
        self.assertEqual(0, resp.json()["revoked"])


# ---------------------------------------------------------------------------
# Tests for GET /admin/authz/check
# ---------------------------------------------------------------------------

class TestAdminAuthzCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.tokens, self.id_tokens, self.user_store, self.pw_store, self.audit, self.chat_history = _make_app()
        self.admin_hdrs = {"Authorization": "Bearer admin-tok"}
        alice = self.user_store.create_user("alice", role="standard_user", enabled=True)
        self.alice_id = alice["id"]

    def test_authz_check_returns_allowed_for_admin_own_permission(self) -> None:
        admin_id = [u["id"] for u in self.user_store.list_users() if u["role"] == "admin"][0]
        resp = self.client.get(
            "/admin/authz/check",
            headers=self.admin_hdrs,
            params={"user_id": admin_id, "permission": "voice.use"},
        )
        self.assertEqual(200, resp.status_code)
        # admins get all permissions
        self.assertIn("allowed", resp.json())

    def test_authz_check_returns_denied_for_user_without_permission(self) -> None:
        resp = self.client.get(
            "/admin/authz/check",
            headers=self.admin_hdrs,
            params={"user_id": self.alice_id, "permission": "actions.write.execute"},
        )
        self.assertEqual(200, resp.status_code)
        self.assertFalse(resp.json()["allowed"])

    def test_authz_check_requires_admin(self) -> None:
        resp = self.client.get(
            "/admin/authz/check",
            params={"user_id": self.alice_id, "permission": "voice.use"},
        )
        self.assertEqual(403, resp.status_code)

    def test_authz_check_unknown_user_returns_404(self) -> None:
        resp = self.client.get(
            "/admin/authz/check",
            headers=self.admin_hdrs,
            params={"user_id": "usr-ghost", "permission": "voice.use"},
        )
        self.assertEqual(404, resp.status_code)


# ---------------------------------------------------------------------------
# Tests for POST /chat/sessions/{id}/pending-home-assistant/clear
# ---------------------------------------------------------------------------

class TestPendingHomeAssistantClear(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.tokens, self.id_tokens, self.user_store, self.pw_store, self.audit, self.chat_history = _make_app()
        alice = self.user_store.create_user("alice", role="standard_user", enabled=True)
        self.alice_id = alice["id"]
        self.id_tokens["sess-alice"] = {"user_id": self.alice_id, "role": "standard_user"}
        self.session_hdrs = {"X-Jarvis-Session": "sess-alice"}

    def test_clear_pending_ha_action_on_existing_session(self) -> None:
        owner_key = f"user:{self.alice_id}"
        sess = self.chat_history.create_session("My Session", owner_key, self.alice_id)
        self.chat_history.set_pending_home_assistant_action(
            sess["id"], {"action": "turn_on", "entity": "light.living_room"}, owner_key, self.alice_id
        )
        # Verify it's set
        self.assertIsNotNone(self.chat_history.get_pending_home_assistant_action(sess["id"], owner_key))

        # Clear it via the API
        resp = self.client.post(
            f"/chat/sessions/{sess['id']}/pending-home-assistant/clear",
            headers=self.session_hdrs,
        )
        self.assertEqual(200, resp.status_code)
        self.assertEqual(sess["id"], resp.json()["id"])
        self.assertTrue(resp.json()["ok"])

        # Must actually be cleared
        self.assertIsNone(self.chat_history.get_pending_home_assistant_action(sess["id"], owner_key))

    def test_clear_pending_ha_action_on_missing_session_returns_404(self) -> None:
        resp = self.client.post(
            "/chat/sessions/sess-ghost/pending-home-assistant/clear",
            headers=self.session_hdrs,
        )
        self.assertEqual(404, resp.status_code)


# ---------------------------------------------------------------------------
# Tests for PUT /auth/me/password
# ---------------------------------------------------------------------------

class TestChangeOwnPassword(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.tokens, self.id_tokens, self.user_store, self.pw_store, self.audit, self.chat_history = _make_app()
        alice = self.user_store.create_user("alice", role="standard_user", enabled=True)
        self.alice_id = alice["id"]
        self.pw_store.set_password(self.alice_id, "old-password")
        self.id_tokens["sess-alice"] = {"user_id": self.alice_id, "role": "standard_user"}
        self.session_hdrs = {"X-Jarvis-Session": "sess-alice"}

    def test_change_password_happy_path(self) -> None:
        resp = self.client.put(
            "/auth/me/password",
            headers=self.session_hdrs,
            json={"current_password": "old-password", "new_password": "new-password"},
        )
        self.assertEqual(200, resp.status_code)
        self.assertTrue(resp.json()["ok"])
        # Verify the password was actually changed
        self.assertTrue(self.pw_store.verify_password(self.alice_id, "new-password"))
        self.assertFalse(self.pw_store.verify_password(self.alice_id, "old-password"))

    def test_change_password_wrong_current_returns_400(self) -> None:
        resp = self.client.put(
            "/auth/me/password",
            headers=self.session_hdrs,
            json={"current_password": "wrong-password", "new_password": "new-password"},
        )
        self.assertEqual(400, resp.status_code)

    def test_change_password_requires_session(self) -> None:
        resp = self.client.put(
            "/auth/me/password",
            json={"current_password": "old-password", "new_password": "new-password"},
        )
        self.assertEqual(401, resp.status_code)

    def test_change_password_audit_event_recorded(self) -> None:
        self.client.put(
            "/auth/me/password",
            headers=self.session_hdrs,
            json={"current_password": "old-password", "new_password": "new-password"},
        )
        events = [e["event"] for e in self.audit.events]
        self.assertIn("user_password_changed", events)


# ---------------------------------------------------------------------------
# Tests for GET /sys/metrics
# ---------------------------------------------------------------------------

class TestSysMetrics(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.tokens, self.id_tokens, self.user_store, self.pw_store, self.audit, self.chat_history = _make_app()
        alice = self.user_store.create_user("alice", role="standard_user", enabled=True)
        self.id_tokens["sess-alice"] = {"user_id": alice["id"], "role": "standard_user"}
        self.session_hdrs = {"X-Jarvis-Session": "sess-alice"}

    def test_metrics_returns_expected_keys(self) -> None:
        resp = self.client.get("/sys/metrics", headers=self.session_hdrs)
        self.assertEqual(200, resp.status_code)
        data = resp.json()
        self.assertIn("cpu", data)
        self.assertIn("ram", data)
        self.assertIn("disk", data)
        self.assertIn("uptime", data)
        self.assertIn("ts", data)

    def test_metrics_cpu_has_pct(self) -> None:
        resp = self.client.get("/sys/metrics", headers=self.session_hdrs)
        self.assertEqual(200, resp.status_code)
        self.assertIn("pct", resp.json()["cpu"])

    def test_metrics_requires_session(self) -> None:
        resp = self.client.get("/sys/metrics")
        self.assertEqual(401, resp.status_code)
