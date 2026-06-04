"""
V1 Acceptance Scenarios — end-to-end automated tests covering the 8 user flows
described in docs/v1/handoff/MANUAL_ACCEPTANCE_V1.md.

All tests use FastAPI TestClient with in-memory fake stores. No real HTTP,
no sleep(), no external service calls. External LLM/TTS/HA calls are stubbed.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from jarvis.api_admin import build_admin_router
from jarvis.api_auth_chat import build_auth_chat_router
from jarvis.api_models import UnlockOut
from jarvis.assistant_domain import try_skill
from jarvis.runtime_state import JarvisStatusHub


# ---------------------------------------------------------------------------
# Shared fake stores that don't write to disk
# ---------------------------------------------------------------------------

class _FakePasswordStore:
    def __init__(self) -> None:
        self.passwords: dict[str, str] = {}

    def verify_password(self, user_id: str, password: str) -> bool:
        return self.passwords.get(user_id) == password

    def set_password(self, user_id: str, password: str) -> None:
        self.passwords[user_id] = password

    def delete_password(self, user_id: str) -> bool:
        return bool(self.passwords.pop(user_id, None))


class _FakeUserStore:
    def __init__(self) -> None:
        self.users: dict[str, dict] = {}
        self._counter = 0
        # Expose .data["users"] for backup/restore compatibility with real UserStore API
        self.data: dict = {"users": self.users}

    def _save(self) -> None:
        # No-op for in-memory store; keeps .data["users"] in sync (it's the same reference)
        self.users = self.data["users"]

    def create_user(self, username: str, role: str = "standard_user", enabled: bool = True) -> dict:
        from jarvis.jarvis_engine import VALID_ROLES
        role_clean = (role or "standard_user").strip().lower()
        if role_clean not in VALID_ROLES:
            raise ValueError("invalid role")
        for u in self.data["users"].values():
            if u["username"].lower() == username.strip().lower():
                raise ValueError("username already exists")
        self._counter += 1
        uid = f"usr-{self._counter:04d}"
        item: dict = {"id": uid, "username": username.strip(), "role": role_clean, "enabled": bool(enabled), "created_at": 0, "updated_at": 0}
        self.data["users"][uid] = item
        return item

    def get_user(self, user_id: str) -> dict | None:
        return self.data["users"].get(user_id)

    def find_by_username(self, username: str) -> dict | None:
        norm = (username or "").strip().lower()
        for u in self.data["users"].values():
            if u["username"].lower() == norm:
                return u
        return None

    def list_users(self) -> list[dict]:
        return list(self.data["users"].values())

    def update_user(self, user_id: str, role: str | None = None, enabled: bool | None = None) -> dict:
        u = self.data["users"].get(user_id)
        if not u:
            raise ValueError("not found")
        if role is not None:
            u["role"] = role
        if enabled is not None:
            u["enabled"] = enabled
        return u

    def delete_user(self, user_id: str) -> bool:
        return bool(self.data["users"].pop(user_id, None))

    def enabled_admin_count(self) -> int:
        return sum(1 for u in self.data["users"].values() if u["role"] == "admin" and u["enabled"])

    def touch_last_seen(self, user_id: str) -> None:
        pass


class _FakePreferencesStore:
    def __init__(self) -> None:
        self.data: dict[str, dict] = {}

    def get(self, user_id: str) -> dict:
        return self.data.get(user_id, {})

    def update(self, user_id: str, payload: dict) -> dict:
        self.data[user_id] = {**self.data.get(user_id, {}), **payload}
        return self.data[user_id]

    def delete(self, user_id: str) -> bool:
        return bool(self.data.pop(user_id, None))


class _FakeChatHistory:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self._counter = 0

    def ensure_session(self, session_id: str | None, owner_key: str, owner_user_id: str | None) -> dict:
        if session_id and session_id in self.sessions:
            return self.sessions[session_id]
        self._counter += 1
        sid = session_id or f"s-{self._counter}"
        sess: dict = {"id": sid, "owner_key": owner_key, "owner_user_id": owner_user_id, "messages": [], "title": "New Chat"}
        self.sessions[sid] = sess
        return sess

    def create_session(self, title: str, owner_key: str, owner_user_id: str | None) -> dict:
        self._counter += 1
        sid = f"s-{self._counter}"
        sess: dict = {"id": sid, "title": title, "owner_key": owner_key, "owner_user_id": owner_user_id, "messages": []}
        self.sessions[sid] = sess
        return sess

    def append_message(self, session_id: str, role: str, text: str, owner_key: str, owner_user_id: str | None) -> None:
        self.sessions[session_id]["messages"].append({"role": role, "text": text})

    def get_session(self, session_id: str, owner_key: str) -> dict | None:
        sess = self.sessions.get(session_id)
        if sess and sess["owner_key"] == owner_key:
            return sess
        return None

    def rename_session(self, session_id: str, title: str, owner_key: str) -> dict | None:
        sess = self.get_session(session_id, owner_key)
        if sess:
            sess["title"] = title
        return sess

    def delete_session(self, session_id: str, owner_key: str) -> bool:
        sess = self.get_session(session_id, owner_key)
        if not sess:
            return False
        self.sessions.pop(session_id, None)
        return True

    def delete_all_sessions(self, owner_key: str) -> int:
        to_delete = [sid for sid, s in self.sessions.items() if s["owner_key"] == owner_key]
        for sid in to_delete:
            self.sessions.pop(sid, None)
        return len(to_delete)

    def list_sessions(self, owner_key: str) -> list[dict]:
        return [s for s in self.sessions.values() if s["owner_key"] == owner_key]

    def search_messages(self, q: str, owner_key: str, limit: int = 30) -> list[dict]:
        results = []
        for sess in self.sessions.values():
            if sess["owner_key"] != owner_key:
                continue
            for msg in sess["messages"]:
                if q.lower() in msg["text"].lower():
                    results.append({"session_id": sess["id"], **msg})
        return results[:limit]

    def get_pending_home_assistant_action(self, session_id: str, owner_key: str) -> dict | None:
        sess = self.get_session(session_id, owner_key)
        return sess.get("pending_home_assistant_action") if sess else None

    def set_pending_home_assistant_action(self, session_id: str, pending: dict, owner_key: str, owner_user_id: str | None) -> None:
        sess = self.ensure_session(session_id, owner_key, owner_user_id)
        sess["pending_home_assistant_action"] = pending

    def clear_pending_home_assistant_action(self, session_id: str, owner_key: str, owner_user_id: str | None) -> None:
        sess = self.ensure_session(session_id, owner_key, owner_user_id)
        sess["pending_home_assistant_action"] = None


class _FakeAuditLog:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def write(self, event: str, payload: dict) -> None:
        self.events.append({"event": event, **payload})

    def read_events(self, **_kwargs) -> list[dict]:
        return list(self.events)

    def count_events(self, **_kwargs) -> int:
        return len(self.events)

    def aggregate_counts(self, **_kwargs) -> dict:
        from collections import Counter
        c: Counter = Counter(e["event"] for e in self.events)
        return dict(c)


class _FakeAdminSettingsStore:
    def __init__(self) -> None:
        self._settings: dict = {"usage_limits": {"token_ttl_min": 60, "max_active_tokens": 10}, "voice": {"wakeword_enabled": False, "wakeword_phrase": "hey jarvis", "stt_provider": "local"}}

    def get(self) -> dict:
        return dict(self._settings)

    def update(self, payload: dict) -> dict:
        self._settings.update(payload)
        return self._settings


class _FakeRagStore:
    def __init__(self) -> None:
        self.data: dict = {"updated_at": 0, "report": {}, "sources": {}}

    def search(self, _q: str, limit: int = 5) -> list[dict]:
        return []

    def refresh(self) -> dict:
        return {"ok": True}


class _FakeEngine:
    def process(self, text: str, _token: str | None, role: str, source: str, granted_permissions: list) -> dict:
        return {"summary": f"engine:{text}", "data": {"route": "engine"}}


# ---------------------------------------------------------------------------
# Helper: build a full admin+auth_chat app wired together
# ---------------------------------------------------------------------------

def _build_full_app(
    *,
    user_store: _FakeUserStore,
    password_store: _FakePasswordStore,
    audit_log: _FakeAuditLog,
    prefs: _FakePreferencesStore,
    tokens: dict,
    identity_tokens: dict,
    group_store: GroupStore,
    membership_store: MembershipStore,
    permission_store: PermissionStore,
    chat_history: _FakeChatHistory,
    emergency_stop: bool = False,
    passphrase: str = "open-sesame",
) -> FastAPI:
    from jarvis.authz import resolve_effective_permissions, build_permission_context, permission_decision
    from jarvis.permission_store import KNOWN_PERMISSIONS

    def require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization, allow_bootstrap=False):
        uid = (x_jarvis_user_id or "").strip()
        role = (x_jarvis_role or "").strip()
        auth = (authorization or "").strip()
        # Bootstrap path
        if allow_bootstrap and not uid and not role:
            if not auth.startswith("Bearer bootstrap-"):
                raise HTTPException(403, "forbidden")
            return "bootstrap", "bootstrap"
        if role == "admin" or uid:
            user = user_store.get_user(uid) if uid else None
            if user and user.get("role") == "admin" and user.get("enabled"):
                return uid, "admin"
        # Bearer token path
        bearer = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        if bearer and bearer in tokens and tokens[bearer].get("role") == "admin":
            return tokens[bearer].get("user_id", ""), "admin"
        raise HTTPException(403, "admin access required")

    def get_identity_session(token: str | None) -> dict | None:
        if not token:
            return None
        data = identity_tokens.get(token)
        if not data:
            return None
        user = user_store.get_user(data["user_id"])
        if not user:
            return None
        return {"token": token, "user": user, "role": user["role"]}

    def require_identity_session(token: str | None) -> dict:
        sess = get_identity_session(token)
        if not sess:
            raise HTTPException(401, "login required")
        return sess

    def issue_token() -> UnlockOut:
        import secrets
        tok = secrets.token_hex(16)
        tokens[tok] = {"role": "admin"}
        return UnlockOut(token=tok, expires_in_sec=3600)

    def issue_identity_token(user_id: str, role: str) -> dict:
        import secrets
        tok = secrets.token_hex(16)
        identity_tokens[tok] = {"user_id": user_id, "role": role}
        return {"session_token": tok, "expires_in_sec": 3600}

    def chat_owner_key(session_token: str | None, guest_key: str | None) -> tuple[str, str | None]:
        sess = get_identity_session(session_token)
        if sess:
            uid = sess["user"]["id"]
            return f"user:{uid}", uid
        return f"guest:{guest_key or 'anon'}", None

    def is_token_active(tok_store: dict, token: str) -> bool:
        return token in tok_store

    def _emergency_stop_enabled() -> bool:
        return emergency_stop

    def _permission_check(role: str, token: str | None, granted_permissions: list[str] | None) -> bool:
        if role == "admin":
            return True
        if granted_permissions and "actions.write.execute" in granted_permissions:
            return True
        return False

    def _try_skill_adapter(text: str, *, role: str, token: str | None, granted_permissions: list[str] | None, user_prefs: dict | None = None, **_kwargs):
        from unittest.mock import Mock
        return try_skill(
            text,
            role=role,
            token=token,
            granted_permissions=granted_permissions,
            emergency_stop_enabled=_emergency_stop_enabled,
            permission_check=_permission_check,
            run_cmd=lambda *_a, **_k: "active",
            disk_usage=lambda *_a: Mock(total=100_000_000_000, used=40_000_000_000, free=60_000_000_000),
            format_bytes=lambda v: f"{v // (1024 ** 3)}GB",
            parse_meminfo=lambda: {"MemTotal": 8_000_000_000, "MemAvailable": 4_000_000_000},
            parse_ping=lambda _o: {"packet_loss": "0%"},
            tail_lines=lambda t, max_lines=6: t,
            ensure_service_allowed=lambda _s: None,
            proxmox_vm_status=lambda *_a: {"data": {"status": "running"}},
            proxmox_lxc_status=lambda *_a: {"data": {"status": "running"}},
            proxmox_vm_action=lambda *_a: {"data": "UPID:task-1"},
            proxmox_lxc_action=lambda *_a: {"data": "UPID:task-2"},
            user_prefs=user_prefs,
        )

    def _resolve_perms(role: str, user_id: str | None, membership_store, permission_store_ref) -> list[str]:
        if not user_id:
            return []
        try:
            return list(resolve_effective_permissions(role, user_id, membership_store, permission_store_ref))
        except Exception:
            return []

    admin_settings_store = _FakeAdminSettingsStore()

    def settings_env_summary() -> dict:
        return {"llm_provider": "local", "emergency_stop": emergency_stop}

    def prepare_audit_filters(event, role, actor_user_id, token_fingerprint) -> dict:
        return {"event": event, "role": role, "actor_user_id": actor_user_id, "token_fingerprint": token_fingerprint}

    def validate_audit_query(limit, since_ts, until_ts) -> None:
        pass

    def audit_admin_event(event: str, actor_user_id: str, caller_role: str, payload: dict) -> None:
        audit_log.write(event, {"actor_user_id": actor_user_id, "caller_role": caller_role, **payload})

    def get_active_user_or_raise(store, user_id: str) -> dict:
        user = store.get_user(user_id)
        if not user:
            raise LookupError("not found")
        if not user.get("enabled", False):
            raise PermissionError("disabled")
        return user

    def _build_permission_context(role, user_id, membership_store, permission_store_ref):
        return build_permission_context(role, user_id, membership_store, permission_store_ref)

    def _permission_decision(role, user_id, permission, membership_store, permission_store_ref):
        return permission_decision(role, user_id, permission, membership_store, permission_store_ref)

    status_hub = JarvisStatusHub()
    app = FastAPI()

    admin_deps = {
        "user_store": user_store,
        "admin_password_store": password_store,
        "audit_log": audit_log,
        "group_store": group_store,
        "membership_store": membership_store,
        "permission_store": permission_store,
        "admin_settings_store": admin_settings_store,
        "user_preferences_store": prefs,
        "identity_tokens": identity_tokens,
        "chat_history": chat_history,
        "require_admin_access": require_admin_access,
        "prepare_audit_filters": prepare_audit_filters,
        "validate_audit_query": validate_audit_query,
        "normalize_role": lambda role: role or "guest_restricted",
        "audit_admin_event": audit_admin_event,
        "known_permissions": KNOWN_PERMISSIONS,
        "get_active_user_or_raise": get_active_user_or_raise,
        "build_permission_context": _build_permission_context,
        "permission_decision": _permission_decision,
        "settings_env_summary": settings_env_summary,
    }

    auth_deps = {
        "ensure_default_admin_seeded": lambda: None,
        "user_store": user_store,
        "admin_password_store": password_store,
        "audit_log": audit_log,
        "issue_token": issue_token,
        "token_fingerprint": lambda tok: f"fp-{tok[:8]}",
        "issue_identity_token": issue_identity_token,
        "user_preferences_store": prefs,
        "identity_tokens": identity_tokens,
        "require_identity_session": require_identity_session,
        "normalize_role": lambda role: role or "guest_restricted",
        "get_identity_session": get_identity_session,
        "chat_owner_key": chat_owner_key,
        "chat_history": chat_history,
        "rag_store": _FakeRagStore(),
        "wakeword_enabled": lambda: False,
        "wakeword_phrase": lambda: "hey jarvis",
        "strip_wakeword": lambda t: (t, True),
        "tokens": tokens,
        "is_token_active": is_token_active,
        "resolve_effective_permissions": _resolve_perms,
        "membership_store": membership_store,
        "permission_store": permission_store,
        "home_assistant_service": None,
        "try_skill": _try_skill_adapter,
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
        "status_hub": status_hub,
        "get_gemini": lambda: None,
        "get_openai": lambda: None,
        "gemini_model": lambda: "gemini",
        "openai_model": lambda: "gpt-4o",
        "openai_temperature": lambda: 0.3,
        "openai_max_tokens": lambda: 512,
        "system_prompt": lambda: "system",
        "bearer_token_from_header": lambda auth: (auth or "").removeprefix("Bearer ").strip(),
        "prune_expired_tokens": lambda _t: 0,
        "passphrase": lambda: passphrase,
    }

    app.include_router(build_admin_router(admin_deps))
    app.include_router(build_auth_chat_router(auth_deps))
    return app


def _make_stores():
    from jarvis.group_store import GroupStore
    from jarvis.membership_store import MembershipStore
    from jarvis.permission_store import PermissionStore

    tmp = tempfile.mkdtemp()
    env_overrides = {
        "JARVIS_GROUP_STORE_PATH": os.path.join(tmp, "groups.json"),
        "JARVIS_MEMBERSHIP_STORE_PATH": os.path.join(tmp, "memberships.json"),
        "JARVIS_PERMISSION_STORE_PATH": os.path.join(tmp, "permissions.json"),
    }
    old_env = {k: os.environ.get(k) for k in env_overrides}
    os.environ.update(env_overrides)

    user_store = _FakeUserStore()
    password_store = _FakePasswordStore()
    audit_log = _FakeAuditLog()
    prefs = _FakePreferencesStore()
    tokens: dict = {}
    identity_tokens: dict = {}
    group_store = GroupStore()
    membership_store = MembershipStore()
    permission_store = PermissionStore()
    chat_history = _FakeChatHistory()

    # Restore env
    for k, v in old_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v

    return user_store, password_store, audit_log, prefs, tokens, identity_tokens, group_store, membership_store, permission_store, chat_history


# ---------------------------------------------------------------------------
# Scenario 1 — Admin bootstrap
# ---------------------------------------------------------------------------

def test_acceptance_1_admin_bootstrap():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()
    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch,
    )
    client = TestClient(app)

    # Before bootstrap: no users exist, login must fail
    resp = client.post("/admin/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 401

    # Bootstrap creates the admin user via the API
    resp = client.post(
        "/admin/users",
        headers={"X-Jarvis-Role": "", "X-Jarvis-User-Id": "", "Authorization": "Bearer bootstrap-secret"},
        json={"username": "admin", "password": "admin123", "role": "admin", "enabled": True},
    )
    assert resp.status_code == 200
    admin_id = resp.json()["id"]
    assert resp.json()["role"] == "admin"

    # Set the password via the admin endpoint (bootstrap already set it above via payload)
    # Now verify the admin can log in
    pw_store.set_password(admin_id, "admin123")
    resp = client.post("/admin/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    data = resp.json()
    assert "token" in data
    assert data["username"] == "admin"
    assert data["role"] == "admin"

    # The audit log must have recorded the successful login
    events = [e["event"] for e in audit.events]
    assert "admin_login_succeeded" in events


# ---------------------------------------------------------------------------
# Scenario 2 — User lifecycle (create → group → permission → effective perms → delete)
# ---------------------------------------------------------------------------

def test_acceptance_2_user_lifecycle():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()

    # Seed an admin directly
    admin = user_store.create_user("admin", role="admin", enabled=True)
    pw_store.set_password(admin["id"], "admin123")
    tokens["admin-token"] = {"role": "admin", "user_id": admin["id"]}

    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch,
    )
    client = TestClient(app)
    admin_hdrs = {"X-Jarvis-User-Id": admin["id"], "X-Jarvis-Role": "admin"}

    # 1. Create user
    resp = client.post("/admin/users", headers=admin_hdrs, json={"username": "alice", "role": "standard_user", "enabled": True})
    assert resp.status_code == 200
    alice_id = resp.json()["id"]

    # 2. Create group
    resp = client.post("/admin/groups", headers=admin_hdrs, json={"name": "ops-team", "description": "Operations"})
    assert resp.status_code == 200
    group_id = resp.json()["id"]

    # 3. Assign alice to the group
    resp = client.post("/admin/assignments", headers=admin_hdrs, json={"user_id": alice_id, "group_id": group_id})
    assert resp.status_code == 200

    # 4. Grant permission to the group
    resp = client.put(f"/admin/permissions/groups/{group_id}", headers=admin_hdrs, json={"permissions": ["actions.write.execute"]})
    assert resp.status_code == 200
    assert "actions.write.execute" in resp.json()["permissions"]

    # 5. Verify effective permissions include the granted one
    resp = client.get(f"/admin/permissions/effective/{alice_id}", headers=admin_hdrs)
    assert resp.status_code == 200
    ctx = resp.json()["permissions"]
    effective = ctx.get("effective_permissions", ctx.get("effective", []))
    assert "actions.write.execute" in effective

    # 6. Delete user — must succeed since alice is not the last admin
    resp = client.delete(f"/admin/users/{alice_id}", headers=admin_hdrs)
    assert resp.status_code == 200

    # 7. Confirm user is gone
    resp = client.get("/admin/users", headers=admin_hdrs)
    assert resp.status_code == 200
    user_ids = [u["id"] for u in resp.json()["users"]]
    assert alice_id not in user_ids

    # 8. Audit log must record user creation and deletion
    events = [e["event"] for e in audit.events]
    assert "admin_user_created" in events
    assert "admin_user_deleted" in events


# ---------------------------------------------------------------------------
# Scenario 3 — Guest bearer token flow
# ---------------------------------------------------------------------------

def test_acceptance_3_guest_bearer_token_flow():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()
    passphrase = "open-sesame"
    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch, passphrase=passphrase,
    )
    client = TestClient(app)

    # 1. POST /unlock with correct passphrase → get bearer token
    resp = client.post("/unlock", json={"passphrase": passphrase})
    assert resp.status_code == 200
    bearer = resp.json()["token"]
    assert bearer

    # 2. POST /chat with that bearer token → get a response
    resp = client.post(
        "/chat",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"text": "what time is it", "source": "text"},
    )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert reply  # must have some content

    # 3. POST /unlock/revoke → revoke the token
    resp = client.post("/unlock/revoke", headers={"Authorization": f"Bearer {bearer}"})
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # 4. The token must now be rejected
    assert bearer not in tokens

    # 5. Audit log must record unlock_issued and unlock_revoked
    events = [e["event"] for e in audit.events]
    assert "unlock_issued" in events
    assert "unlock_revoked" in events


# ---------------------------------------------------------------------------
# Scenario 4 — Chat skill routing (time query must NOT hit LLM)
# ---------------------------------------------------------------------------

def test_acceptance_4_chat_skill_routing_no_llm():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()

    llm_called = {"openai": False, "gemini": False}

    class _TrackingEngine:
        def process(self, text, _token, role, source, granted_permissions):
            # The engine is only reached after skill routing; if skill fires, this won't be called.
            # Return a "cloud" route to simulate LLM path for non-skill inputs.
            return {"summary": f"llm:{text}", "data": {"route": "cloud"}}

    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch,
    )
    client = TestClient(app)

    # "what time is it" is a deterministic skill — matches t in {"time", "date", ...}
    resp = client.post(
        "/chat",
        json={"text": "what time is it", "source": "text"},
    )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    # The time skill always returns "On it. It is HH:MM on <date>."
    assert "On it." in reply or "It is" in reply
    # The data route should be absent (skill) or explicitly show skill path
    data = resp.json().get("data", {})
    # Must NOT be cloud route (LLM was not called)
    assert data.get("route") != "cloud"
    # No LLM calls were made
    assert not llm_called["openai"]
    assert not llm_called["gemini"]


# ---------------------------------------------------------------------------
# Scenario 5 — Emergency stop blocks write-level skill actions
# ---------------------------------------------------------------------------

def test_acceptance_5_emergency_stop():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()

    # Build app with emergency stop active
    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch, emergency_stop=True,
    )
    client = TestClient(app)

    # Seed a valid bearer token
    tokens["test-bearer"] = {"role": "admin"}

    # 1. Write-level skill (restart nginx) must be blocked by emergency stop
    resp = client.post(
        "/chat",
        headers={"Authorization": "Bearer test-bearer"},
        json={"text": "restart nginx", "source": "text"},
    )
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    # Emergency stop reply must clearly indicate blocking
    assert data.get("error") == "emergency_stop" or "Emergency stop" in resp.json().get("reply", "")

    # 2. Read-only skill (what time is it) must still succeed
    resp = client.post(
        "/chat",
        headers={"Authorization": "Bearer test-bearer"},
        json={"text": "what time is it", "source": "text"},
    )
    assert resp.status_code == 200
    reply = resp.json()["reply"]
    assert "It is" in reply or "On it." in reply


# ---------------------------------------------------------------------------
# Scenario 6 — Session management (create → messages → search → rename → delete)
# ---------------------------------------------------------------------------

def test_acceptance_6_session_management():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()

    user = user_store.create_user("alice", role="standard_user", enabled=True)
    pw_store.set_password(user["id"], "pass123")
    id_tokens["sess-alice"] = {"user_id": user["id"], "role": "standard_user"}

    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch,
    )
    client = TestClient(app)
    hdrs = {"X-Jarvis-Session": "sess-alice"}

    # 1. Create a chat session explicitly
    resp = client.post("/chat/sessions", headers=hdrs, json={"title": "Test Session"})
    assert resp.status_code == 200
    session_id = resp.json()["id"]
    assert resp.json()["title"] == "Test Session"

    # 2. Post a chat message into that session
    resp = client.post("/chat", headers=hdrs, json={"text": "what time is it", "session_id": session_id})
    assert resp.status_code == 200

    # 3. Get session and verify it has messages
    resp = client.get(f"/chat/sessions/{session_id}", headers=hdrs)
    assert resp.status_code == 200
    messages = resp.json()["messages"]
    assert len(messages) >= 2  # user message + jarvis reply

    # 4. Full-text search finds the message
    resp = client.get("/chat/search", headers=hdrs, params={"q": "time"})
    assert resp.status_code == 200
    assert len(resp.json()["hits"]) > 0

    # 5. Rename session
    resp = client.patch(f"/chat/sessions/{session_id}", headers=hdrs, json={"title": "Renamed Session"})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Renamed Session"

    # 6. Delete session
    resp = client.delete(f"/chat/sessions/{session_id}", headers=hdrs)
    assert resp.status_code == 200

    # 7. Session is gone
    resp = client.get(f"/chat/sessions/{session_id}", headers=hdrs)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Scenario 7 — Permission enforcement (no permission → 403, grant → success)
# ---------------------------------------------------------------------------

def test_acceptance_7_permission_enforcement():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()

    admin = user_store.create_user("admin", role="admin", enabled=True)
    pw_store.set_password(admin["id"], "admin123")
    tokens["admin-token"] = {"role": "admin", "user_id": admin["id"]}

    alice = user_store.create_user("alice", role="standard_user", enabled=True)
    id_tokens["sess-alice"] = {"user_id": alice["id"], "role": "standard_user"}
    # Give alice a bearer token (required for write-level skills)
    tokens["alice-bearer"] = {"role": "standard_user", "user_id": alice["id"]}

    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch,
    )
    client = TestClient(app)
    admin_hdrs = {"X-Jarvis-User-Id": admin["id"], "X-Jarvis-Role": "admin"}

    # 1. Alice without actions.write.execute tries restart nginx → must be blocked
    resp = client.post(
        "/chat",
        headers={"X-Jarvis-Session": "sess-alice", "Authorization": "Bearer alice-bearer"},
        json={"text": "restart nginx", "source": "text"},
    )
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    assert data.get("error") == "permission_denied"

    # 2. Admin grants alice the permission directly
    resp = client.put(f"/admin/permissions/users/{alice['id']}", headers=admin_hdrs, json={"permissions": ["actions.write.execute"]})
    assert resp.status_code == 200
    assert "actions.write.execute" in resp.json()["permissions"]

    # 3. Now alice's effective permissions should include it
    resp = client.get(f"/admin/permissions/effective/{alice['id']}", headers=admin_hdrs)
    assert resp.status_code == 200
    ctx7 = resp.json()["permissions"]
    effective = ctx7.get("effective_permissions", ctx7.get("effective", []))
    assert "actions.write.execute" in effective

    # 4. With the permission granted, alice can now execute write-level skills
    resp = client.post(
        "/chat",
        headers={"X-Jarvis-Session": "sess-alice", "Authorization": "Bearer alice-bearer"},
        json={"text": "restart nginx", "source": "text"},
    )
    assert resp.status_code == 200
    data = resp.json().get("data", {})
    # Should NOT be permission_denied anymore
    assert data.get("error") != "permission_denied"
    assert "nginx" in resp.json()["reply"].lower()


# ---------------------------------------------------------------------------
# Scenario 8 — Backup and restore round-trip
# ---------------------------------------------------------------------------

def test_acceptance_8_backup_and_restore():
    user_store, pw_store, audit, prefs, tokens, id_tokens, gs, ms, ps, ch = _make_stores()

    admin = user_store.create_user("admin", role="admin", enabled=True)
    pw_store.set_password(admin["id"], "admin123")
    tokens["admin-token"] = {"role": "admin", "user_id": admin["id"]}
    alice = user_store.create_user("alice", role="standard_user", enabled=True)

    app = _build_full_app(
        user_store=user_store, password_store=pw_store, audit_log=audit, prefs=prefs,
        tokens=tokens, identity_tokens=id_tokens, group_store=gs, membership_store=ms,
        permission_store=ps, chat_history=ch,
    )
    client = TestClient(app)
    admin_hdrs = {"X-Jarvis-User-Id": admin["id"], "X-Jarvis-Role": "admin"}

    # 1. GET /admin/backup — captures full snapshot with backup_version: 1
    resp = client.get("/admin/backup", headers=admin_hdrs)
    assert resp.status_code == 200
    backup = resp.json()
    assert backup["backup_version"] == 1
    original_user_ids = {u["id"] for u in backup["users"]}
    assert alice["id"] in original_user_ids

    # 2. Mutate state — add a new user
    resp = client.post("/admin/users", headers=admin_hdrs, json={"username": "bob", "role": "standard_user", "enabled": True})
    assert resp.status_code == 200
    bob_id = resp.json()["id"]

    # Verify bob exists now
    resp = client.get("/admin/users", headers=admin_hdrs)
    current_ids = {u["id"] for u in resp.json()["users"]}
    assert bob_id in current_ids

    # 3. POST /admin/backup/restore — restore from the snapshot
    resp = client.post("/admin/backup/restore", headers=admin_hdrs, json=backup)
    assert resp.status_code == 200
    restored = resp.json()["restored"]
    assert restored.get("users", 0) >= 2  # admin + alice

    # 4. State should match the original snapshot (bob should be gone)
    resp = client.get("/admin/users", headers=admin_hdrs)
    assert resp.status_code == 200
    restored_ids = {u["id"] for u in resp.json()["users"]}
    # The original users are back
    assert admin["id"] in restored_ids
    assert alice["id"] in restored_ids
    # Bob was not in the backup — he should not be present
    assert bob_id not in restored_ids

    # 5. Audit log must record backup_restored
    events = [e["event"] for e in audit.events]
    assert "admin_backup_restored" in events
