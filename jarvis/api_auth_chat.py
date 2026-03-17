from fastapi import APIRouter, Header, HTTPException

from .api_models import (
    AdminLoginIn,
    AdminLoginOut,
    ChatIn,
    ChatOut,
    ChatSessionCreateIn,
    UnlockIn,
    UnlockOut,
    UserLoginIn,
    UserPreferencesIn,
)
from .router_dependencies import LiveRef


def build_auth_chat_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    ensure_default_admin_seeded = deps["ensure_default_admin_seeded"]
    issue_token = deps["issue_token"]
    token_fingerprint = deps["token_fingerprint"]
    issue_identity_token = deps["issue_identity_token"]
    require_identity_session = deps["require_identity_session"]
    normalize_role = deps["normalize_role"]
    get_identity_session = deps["get_identity_session"]
    chat_owner_key = deps["chat_owner_key"]
    wakeword_enabled = deps["wakeword_enabled"]
    strip_wakeword = deps["strip_wakeword"]
    is_token_active = deps["is_token_active"]
    resolve_effective_permissions = deps["resolve_effective_permissions"]
    try_skill = deps["try_skill"]
    rag_query_from_prompt = deps["rag_query_from_prompt"]
    select_rag_hits = deps["select_rag_hits"]
    rag_needs_smart_llm = deps["rag_needs_smart_llm"]
    cloud_llm_available = deps["cloud_llm_available"]
    format_rag_reply = deps["format_rag_reply"]
    rag_llm_answer = deps["rag_llm_answer"]
    build_context_reply = deps["build_context_reply"]
    get_provider = deps["get_provider"]
    local_ai_stub_reply = deps["local_ai_stub_reply"]
    get_gemini = deps["get_gemini"]
    get_openai = deps["get_openai"]

    @router.post("/admin/login", response_model=AdminLoginOut)
    def admin_login(payload: AdminLoginIn):
        ensure_default_admin_seeded()

        user = current("user_store").find_by_username(payload.username)
        if not user or user.get("role") != "admin" or not bool(user.get("enabled", False)):
            current("audit_log").write("admin_login_failed", {"username": (payload.username or "").strip(), "reason": "invalid_credentials"})
            raise HTTPException(401, "Invalid admin credentials")

        if not current("admin_password_store").verify_password(user["id"], payload.password):
            current("audit_log").write("admin_login_failed", {"username": user.get("username", ""), "user_id": user["id"], "reason": "invalid_credentials"})
            raise HTTPException(401, "Invalid admin credentials")

        issued = issue_token()
        current("audit_log").write(
            "admin_login_succeeded",
            {
                "user_id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "expires_in_sec": issued.expires_in_sec,
                "token_fingerprint": token_fingerprint(issued.token),
            },
        )
        return AdminLoginOut(
            token=issued.token,
            expires_in_sec=issued.expires_in_sec,
            user_id=user["id"],
            username=user["username"],
            role=user["role"],
        )

    @router.post("/auth/login")
    def user_login(payload: UserLoginIn):
        user = current("user_store").find_by_username(payload.username)
        if not user or not bool(user.get("enabled", False)) or user.get("role") == "service_system":
            raise HTTPException(401, "Invalid credentials")
        if not current("admin_password_store").verify_password(user["id"], payload.password):
            raise HTTPException(401, "Invalid credentials")
        issued = issue_identity_token(user["id"], user["role"])
        preferences = current("user_preferences_store").get(user["id"])
        current("audit_log").write("user_login_succeeded", {"user_id": user["id"], "username": user["username"], "role": user["role"]})
        return {
            **issued,
            "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            "preferences": preferences,
        }

    @router.post("/auth/logout")
    def user_logout(x_jarvis_session: str | None = Header(default=None)):
        token = (x_jarvis_session or "").strip()
        if token:
            current("identity_tokens").pop(token, None)
        return {"ok": True}

    @router.get("/auth/me")
    def auth_me(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user = session["user"]
        return {
            "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            "preferences": current("user_preferences_store").get(user["id"]),
        }

    @router.get("/auth/me/preferences")
    def auth_get_preferences(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        return {"preferences": current("user_preferences_store").get(session["user"]["id"])}

    @router.put("/auth/me/preferences")
    def auth_update_preferences(payload: UserPreferencesIn, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        updated = current("user_preferences_store").update(session["user"]["id"], payload.model_dump())
        current("audit_log").write("user_preferences_updated", {"user_id": session["user"]["id"]})
        return {"preferences": updated}

    @router.post("/admin/session")
    def admin_session(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user = session["user"]
        if normalize_role(user.get("role")) != "admin":
            raise HTTPException(403, "admin role required")
        issued = issue_token()
        current("audit_log").write("admin_session_issued", {"user_id": user["id"], "username": user["username"]})
        return {
            "token": issued.token,
            "expires_in_sec": issued.expires_in_sec,
            "user_id": user["id"],
            "username": user["username"],
            "role": user["role"],
        }

    @router.post("/unlock", response_model=UnlockOut)
    def unlock(payload: UnlockIn):
        expected = deps["passphrase"]()
        if not expected:
            current("audit_log").write("unlock_failed", {"reason": "passphrase_not_set"})
            raise HTTPException(500, "JARVIS_PASSPHRASE not set")

        if (payload.passphrase or "").strip().lower() != expected.lower():
            current("audit_log").write("unlock_failed", {"reason": "wrong_passphrase"})
            raise HTTPException(401, "Wrong passphrase")

        issued = issue_token()
        current("audit_log").write(
            "unlock_issued",
            {
                "expires_in_sec": issued.expires_in_sec,
                "active_token_count": len(current("tokens")),
                "token_fingerprint": token_fingerprint(issued.token),
            },
        )
        return issued

    @router.post("/unlock/revoke")
    def unlock_revoke(authorization: str | None = Header(default=None)):
        pruned = deps["prune_expired_tokens"](current("tokens"))
        token = deps["bearer_token_from_header"](authorization)
        if not token:
            current("audit_log").write("unlock_revoke_denied", {"reason": "missing_token", "pruned_count": pruned})
            raise HTTPException(401, "Missing token")
        if not is_token_active(current("tokens"), token):
            current("audit_log").write(
                "unlock_revoke_denied",
                {"reason": "inactive_token", "pruned_count": pruned, "token_fingerprint": token_fingerprint(token)},
            )
            raise HTTPException(401, "Token expired or invalid")
        current("tokens").pop(token, None)
        current("audit_log").write(
            "unlock_revoked",
            {
                "active_token_count": len(current("tokens")),
                "pruned_count": pruned,
                "token_fingerprint": token_fingerprint(token),
            },
        )
        return {"ok": True}

    @router.post("/chat", response_model=ChatOut)
    def chat(
        payload: ChatIn,
        authorization: str | None = Header(default=None),
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_guest_key: str | None = Header(default=None),
        x_jarvis_mode: str | None = Header(default=None),
    ):
        text = (payload.text or "").strip()
        source = (payload.source or "text").strip().lower()
        mode = (x_jarvis_mode or "").strip().lower()
        identity_session = get_identity_session(x_jarvis_session)
        owner_key, effective_user_id = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        active_user = identity_session["user"] if identity_session else None
        role = normalize_role(active_user.get("role") if active_user else "guest_restricted")

        if mode == "orb" and not active_user:
            raise HTTPException(401, "orb login required")

        if source == "voice" and wakeword_enabled():
            stripped, detected = strip_wakeword(text)
            if not detected:
                phrase = deps["wakeword_phrase"]()
                return {
                    "reply": f"Awaiting wake word. Say: '{phrase}'.",
                    "data": {"wakeword_required": phrase},
                    "session_id": payload.session_id,
                }
            text = stripped

        session = current("chat_history").ensure_session(payload.session_id, owner_key=owner_key, owner_user_id=effective_user_id)
        session_id = session["id"]
        if not text:
            return {"reply": "Say that again.", "session_id": session_id}

        token = deps["bearer_token_from_header"](authorization)
        if token and not is_token_active(current("tokens"), token):
            token = None

        current("chat_history").append_message(session_id, "user", text, owner_key=owner_key, owner_user_id=effective_user_id)
        granted_permissions = sorted(resolve_effective_permissions(role, effective_user_id, current("membership_store"), current("permission_store")))

        skill_first = try_skill(text, role=role, token=token, granted_permissions=granted_permissions)
        if skill_first:
            reply = skill_first.get("reply", "Done.")
            data = skill_first.get("data") or {}
            if data.get("error") == "permission_denied":
                current("audit_log").write("permission_denied", {"role": role, "source": source, "text": text, "data": data, "path": "try_skill"})
            if data.get("error") == "emergency_stop":
                current("audit_log").write("emergency_stop_blocked", {"role": role, "source": source, "text": text, "path": "try_skill"})
            current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
            return {"reply": reply, "data": data, "session_id": session_id}

        rag_intent = rag_query_from_prompt(text)
        if rag_intent:
            rag_hits = select_rag_hits(rag_intent, limit=5 if rag_intent.get("mode") == "tasks" else 3)
            if rag_hits:
                needs_smart = rag_needs_smart_llm(text)
                if needs_smart and not cloud_llm_available():
                    reply = "Understood. Für diese intelligente Wiki/Repo-Auswertung brauche ich Cloud-KI (OPENAI_API_KEY oder GEMINI_API_KEY)."
                    data = {"route": "rag", "rag": rag_hits, "intent": rag_intent, "error": "cloud_llm_required"}
                    current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                    return {"reply": reply, "data": data, "session_id": session_id}

                if needs_smart and cloud_llm_available():
                    try:
                        reply = rag_llm_answer(text, rag_hits)
                    except Exception:
                        reply = format_rag_reply(rag_intent, rag_hits)
                else:
                    reply = format_rag_reply(rag_intent, rag_hits)

                data = {"route": "rag", "rag": rag_hits, "intent": rag_intent, "smart": needs_smart}
                current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                return {"reply": reply, "data": data, "session_id": session_id}

        response = current("engine").process(text, token, role=role, source=source, granted_permissions=granted_permissions)
        summary = response.get("summary", "") if isinstance(response, dict) else getattr(response, "summary", "")
        data = response.get("data", {}) if isinstance(response, dict) else (getattr(response, "data", {}) or {})

        if data.get("error") == "permission_denied":
            current("audit_log").write("permission_denied", {"role": role, "source": source, "text": text, "data": data})
        if data.get("error") == "emergency_stop":
            current("audit_log").write("emergency_stop_blocked", {"role": role, "source": source, "text": text, "path": "engine"})
        if data.get("confirm") in {"YES", "YES, proceed"}:
            current("audit_log").write("dangerous_action_confirmation_requested", {"role": role, "source": source, "text": text, "risk": data.get("risk")})

        if data.get("route") != "cloud":
            current("chat_history").append_message(session_id, "jarvis", summary, owner_key=owner_key, owner_user_id=effective_user_id)
            return {"reply": summary, "data": data, "session_id": session_id}

        provider = get_provider()

        try:
            if provider == "local":
                reply = local_ai_stub_reply(text)
                current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                return {"reply": reply, "session_id": session_id}

            if provider == "gemini":
                gemini = get_gemini()
                resp = gemini.models.generate_content(
                    model=deps["gemini_model"](),
                    contents=[{"role": "user", "parts": [{"text": text}]}],
                )
                out = (getattr(resp, "text", "") or "").strip() or "On it. (No output returned.)"
                current("chat_history").append_message(session_id, "jarvis", out, owner_key=owner_key, owner_user_id=effective_user_id)
                return {"reply": out, "session_id": session_id}

            client = get_openai()
            resp = client.chat.completions.create(
                model=deps["openai_model"](),
                messages=[{"role": "system", "content": deps["system_prompt"]()}, {"role": "user", "content": text}],
                temperature=float(deps["openai_temperature"]()),
                max_tokens=int(deps["openai_max_tokens"]()),
            )
            out = (resp.choices[0].message.content or "").strip()
            current("chat_history").append_message(session_id, "jarvis", out, owner_key=owner_key, owner_user_id=effective_user_id)
            return {"reply": out, "session_id": session_id}
        except Exception:
            reply = build_context_reply(text)
            current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
            return {
                "reply": reply,
                "data": {
                    "route": "offline_assistant",
                    "reason": "cloud_unavailable",
                },
                "session_id": session_id,
            }

    @router.get("/chat/sessions")
    def list_chat_sessions(x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        return {"sessions": current("chat_history").list_sessions(owner_key=owner_key)}

    @router.post("/chat/sessions")
    def create_chat_session(payload: ChatSessionCreateIn, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, owner_user_id = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        return current("chat_history").create_session(payload.title, owner_key=owner_key, owner_user_id=owner_user_id)

    @router.get("/chat/sessions/{session_id}")
    def get_chat_session(session_id: str, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        session = current("chat_history").get_session(session_id, owner_key=owner_key)
        if not session:
            raise HTTPException(404, "session not found")
        return session

    @router.delete("/chat/sessions/{session_id}")
    def delete_chat_session(session_id: str, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        deleted = current("chat_history").delete_session(session_id, owner_key=owner_key)
        if not deleted:
            raise HTTPException(404, "session not found")
        return {"ok": True, "id": session_id}

    @router.get("/rag/status")
    def rag_status():
        return {
            "updated_at": current("rag_store").data.get("updated_at", 0),
            "report": current("rag_store").data.get("report", {}),
            "counts": {key: len(value) for key, value in (current("rag_store").data.get("sources") or {}).items()},
        }

    @router.post("/rag/refresh")
    def rag_refresh():
        return {"report": current("rag_store").refresh()}

    @router.get("/rag/search")
    def rag_search(q: str):
        return {"results": current("rag_store").search(q, limit=5)}

    return router
