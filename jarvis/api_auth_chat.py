import json as _json
import logging as _logging
import os as _os
import time as _time
from datetime import datetime, date as _date

_log = _logging.getLogger(__name__)

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from .rate_limiter import _rate

from .ai_clients import build_system_prompt
from .ai_router import AIRouter
from .secret_crypto import SecretEncryptionUnavailable
from .api_models import (
    AdminLoginIn,
    AdminLoginOut,
    ByokKeyIn,
    ByokKeyOut,
    ChatIn,
    ChatOut,
    ChatSessionCreateIn,
    ChatSessionUpdateIn,
    SignupConfigOut,
    SignupIn,
    SignupResendIn,
    SignupVerifyIn,
    UnlockIn,
    UnlockOut,
    UserChangePasswordIn,
    UserLoginIn,
    UserPreferencesIn,
)
from .email_service import EmailServiceUnavailable, is_configured as _email_configured, send_verification_email as _send_verification_email
from .pending_signup_store import (
    PendingSignupStore as _PendingSignupStore,
    SignupCodeExpired,
    SignupCodeInvalid,
    SignupCodeLocked,
)
from .home_assistant.chat_intents import execute_home_assistant_chat_intent
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
    _ai_router_enabled = _os.getenv("JARVIS_USE_AI_ROUTER", "1").strip() not in ("0", "false", "no", "")

    def _make_ai_router() -> AIRouter:
        return AIRouter(
            byok_store=deps.get("byok_store") and current("byok_store"),
            usage_log_store=deps.get("usage_log_store") and current("usage_log_store"),
            credit_store=deps.get("credit_store") and current("credit_store"),
            user_limits_store=deps.get("user_limits_store") and current("user_limits_store"),
            admin_settings_store=deps.get("admin_settings_store") and current("admin_settings_store"),
            build_context_reply=build_context_reply,
            rate_limiter=_rate,
        )

    def auth_capabilities(user_id: str, role: str) -> dict[str, bool]:
        effective_permissions = set(resolve_effective_permissions(role, user_id, current("membership_store"), current("permission_store")))
        first_admin_user_id = None
        for listed_user in current("user_store").list_users():
            if listed_user.get("role") == "admin":
                first_admin_user_id = listed_user.get("id")
                break
        home_assistant_access = bool(
            "home_assistant.access" in effective_permissions
            or (first_admin_user_id and user_id == first_admin_user_id)
        )
        return {"home_assistant_access": home_assistant_access}

    def _get_llm_history(session_id: str, owner_key: str, limit: int = 20) -> list[dict]:
        """Return last `limit` messages from session as OpenAI-format dicts, excluding the just-appended user message."""
        try:
            sess = current("chat_history").get_session(session_id, owner_key=owner_key)
            if not sess:
                return []
            msgs = sess.get("messages", [])
            history = msgs[:-1][-limit:]
            result = [{"role": "user" if m["role"] == "user" else "assistant", "content": m["text"]} for m in history]
            # Ensure history starts with a user message (required by some LLM APIs)
            while result and result[0]["role"] != "user":
                result = result[1:]
            return result
        except Exception:
            return []

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
            "capabilities": auth_capabilities(user["id"], user["role"]),
        }

    @router.post("/auth/logout")
    def user_logout(x_jarvis_session: str | None = Header(default=None)):
        token = (x_jarvis_session or "").strip()
        if token:
            current("identity_tokens").pop(token, None)
        return {"ok": True}

    # ── Self-service signup ──────────────────────────────────────────────────

    def _signup_enabled() -> bool:
        if _os.getenv("JARVIS_SIGNUP_ENABLED", "").strip() in ("0", "false", "no"):
            return False
        return _email_configured()

    @router.get("/auth/signup/config", response_model=SignupConfigOut)
    def signup_config():
        return SignupConfigOut(enabled=_signup_enabled())

    @router.post("/auth/signup")
    def signup_request(payload: SignupIn):
        if not _signup_enabled():
            raise HTTPException(503, "Self-service signup is not available")
        if not _rate.allow(f"signup:{payload.email}", limit=5, window=900):
            raise HTTPException(429, "Too many signup attempts — try again later")

        user_store = current("user_store")
        pending: _PendingSignupStore = current("pending_signup_store")

        if user_store.find_by_username(payload.username) or pending.username_pending(payload.username):
            raise HTTPException(409, "Username already taken")
        if user_store.find_by_email(payload.email) or pending.email_pending(payload.email):
            raise HTTPException(409, "Email already registered")
        cred = current("admin_password_store").hash_password(payload.password)
        code = pending.generate_code()
        pending.put(payload.email, payload.username, cred, code)

        try:
            _send_verification_email(payload.email, code)
        except EmailServiceUnavailable as exc:
            _log.error("Signup email failed: %s", exc)
            raise HTTPException(503, "Email delivery failed — please try again later") from exc

        current("audit_log").write("signup_requested", {"email_hash": payload.email[:3] + "***", "username": payload.username})
        return {"ok": True, "email": payload.email}

    @router.post("/auth/signup/verify")
    def signup_verify(payload: SignupVerifyIn):
        if not _signup_enabled():
            raise HTTPException(503, "Self-service signup is not available")
        if not _rate.allow(f"signup_verify:{payload.email}", limit=10, window=600):
            raise HTTPException(429, "Too many verification attempts")

        pending: _PendingSignupStore = current("pending_signup_store")
        try:
            record = pending.verify_code(payload.email, payload.code)
        except SignupCodeExpired:
            raise HTTPException(410, "Verification code has expired — please sign up again")
        except SignupCodeLocked:
            raise HTTPException(429, "Too many failed attempts — please sign up again")
        except SignupCodeInvalid as exc:
            raise HTTPException(400, str(exc))

        user_store = current("user_store")
        admin_pw = current("admin_password_store")

        if user_store.find_by_username(record["username"]):
            pending.delete(payload.email)
            raise HTTPException(409, "Username was just taken — please sign up again with a different username")
        if user_store.find_by_email(payload.email):
            pending.delete(payload.email)
            raise HTTPException(409, "Email already registered")

        created = user_store.create_user(record["username"], role="standard_user", enabled=True, email=payload.email)
        admin_pw.set_record(created["id"], record["cred"])
        pending.delete(payload.email)

        issued = issue_identity_token(created["id"], created["role"])
        preferences = current("user_preferences_store").get(created["id"])
        current("audit_log").write("signup_completed", {"user_id": created["id"], "username": created["username"]})
        return {
            **issued,
            "user": {"id": created["id"], "username": created["username"], "role": created["role"]},
            "preferences": preferences,
            "capabilities": auth_capabilities(created["id"], created["role"]),
        }

    @router.post("/auth/signup/resend")
    def signup_resend(payload: SignupResendIn):
        if not _signup_enabled():
            raise HTTPException(503, "Self-service signup is not available")
        if not _rate.allow(f"signup_resend:{payload.email}", limit=3, window=600):
            raise HTTPException(429, "Too many resend requests — wait a while")

        pending: _PendingSignupStore = current("pending_signup_store")
        record = pending.get(payload.email)
        if not record:
            raise HTTPException(404, "No pending signup found for this email")

        new_code = pending.generate_code()
        pending.put(payload.email, record["username"], record["cred"], new_code)
        try:
            _send_verification_email(payload.email, new_code)
        except EmailServiceUnavailable as exc:
            raise HTTPException(503, "Email delivery failed") from exc

        return {"ok": True, "email": payload.email}

    @router.get("/auth/me")
    def auth_me(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user = session["user"]
        return {
            "user": {"id": user["id"], "username": user["username"], "role": user["role"]},
            "preferences": current("user_preferences_store").get(user["id"]),
            "capabilities": auth_capabilities(user["id"], user["role"]),
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

    @router.put("/auth/me/password")
    def auth_change_password(payload: UserChangePasswordIn, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id = session["user"]["id"]
        pw_store = current("admin_password_store")
        if not pw_store.verify_password(user_id, payload.current_password):
            raise HTTPException(400, "current password is incorrect")
        pw_store.set_password(user_id, payload.new_password)
        current("audit_log").write("user_password_changed", {"user_id": user_id})
        return {"ok": True}

    @router.get("/auth/me/keys")
    def auth_list_keys(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        return {"keys": current("byok_store").list_masked(session["user"]["id"])}

    @router.put("/auth/me/keys/{provider}")
    def auth_set_key(provider: str, payload: ByokKeyIn, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id = session["user"]["id"]
        try:
            masked_record = current("byok_store").set_key(user_id, provider, payload.api_key)
        except SecretEncryptionUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        current("audit_log").write("byok_key_set", {"user_id": user_id, "provider": provider})
        return {"key": masked_record}

    @router.delete("/auth/me/keys/{provider}")
    def auth_delete_key(provider: str, x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id = session["user"]["id"]
        deleted = current("byok_store").delete_key(user_id, provider)
        if deleted:
            current("audit_log").write("byok_key_deleted", {"user_id": user_id, "provider": provider})
        return {"deleted": deleted}

    @router.get("/auth/me/billing")
    def auth_me_billing(x_jarvis_session: str | None = Header(default=None)):
        session = require_identity_session(x_jarvis_session)
        user_id = session["user"]["id"]
        balance_chf = current("credit_store").get_balance(user_id)
        limits = current("user_limits_store").get(user_id)
        recent_usage = current("usage_log_store").recent(user_id=user_id, limit=10)
        return {
            "user_id": user_id,
            "balance_chf": balance_chf,
            "limits": limits,
            "recent_usage": recent_usage,
        }

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
        x_jarvis_role: str | None = Header(default=None),
        x_jarvis_confirm: str | None = Header(default=None),
    ):
        text = (payload.text or "").strip()
        source = (payload.source or "text").strip().lower()
        mode = (x_jarvis_mode or "").strip().lower()
        identity_session = get_identity_session(x_jarvis_session)
        owner_key, effective_user_id = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        active_user = identity_session["user"] if identity_session else None
        role = normalize_role(active_user.get("role") if active_user else x_jarvis_role or "guest_restricted")

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

        rl_key = effective_user_id or (x_jarvis_guest_key or "anon")
        if not _rate.allow(f"chat:{rl_key}", limit=30, window=60.0):
            raise HTTPException(429, "Rate limit exceeded — slow down")

        token = deps["bearer_token_from_header"](authorization)
        if token and not is_token_active(current("tokens"), token):
            token = None

        current("chat_history").append_message(session_id, "user", text, owner_key=owner_key, owner_user_id=effective_user_id)
        granted_permissions = sorted(resolve_effective_permissions(role, effective_user_id, current("membership_store"), current("permission_store")))
        status_token = current("status_hub").begin("processing", source=source, mode=mode or "chat")

        try:
            home_assistant_service = current("home_assistant_service")
            pending_home_assistant_action = current("chat_history").get_pending_home_assistant_action(session_id, owner_key=owner_key)
            ha_intent = (
                execute_home_assistant_chat_intent(
                    home_assistant_service,
                    text,
                    user_id=effective_user_id,
                    role=role,
                    pending_action=pending_home_assistant_action,
                )
                if home_assistant_service and pending_home_assistant_action
                else None
            )
            if not ha_intent and home_assistant_service and auth_capabilities(effective_user_id, role).get("home_assistant_access"):
                ha_intent = execute_home_assistant_chat_intent(home_assistant_service, text, user_id=effective_user_id, role=role)
            if ha_intent:
                reply = ha_intent.get("reply", "Done.")
                data = ha_intent.get("data") or {}
                follow_up = data.get("follow_up")
                if isinstance(follow_up, dict):
                    current("chat_history").set_pending_home_assistant_action(session_id, follow_up, owner_key=owner_key, owner_user_id=effective_user_id)
                else:
                    current("chat_history").clear_pending_home_assistant_action(session_id, owner_key=owner_key, owner_user_id=effective_user_id)
                current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                return {"reply": reply, "data": data, "session_id": session_id}

            _skill_prefs = current("user_preferences_store").get(effective_user_id) if effective_user_id else {}
            skill_first = try_skill(text, role=role, token=token, granted_permissions=granted_permissions, user_prefs=_skill_prefs)
            if skill_first:
                reply = skill_first.get("reply", "Done.")
                data = dict(skill_first.get("data") or {})
                save_to_prefs = data.pop("save_to_prefs", None)
                prefs_update = None
                if save_to_prefs and effective_user_id:
                    prefs_update = current("user_preferences_store").update(effective_user_id, save_to_prefs)
                if data.get("error") == "permission_denied":
                    current("audit_log").write("permission_denied", {"role": role, "source": source, "text": text, "data": data, "path": "try_skill"})
                if data.get("error") == "emergency_stop":
                    current("audit_log").write("emergency_stop_blocked", {"role": role, "source": source, "text": text, "path": "try_skill"})
                current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                result: dict = {"reply": reply, "data": data, "session_id": session_id}
                if prefs_update:
                    result["prefs_update"] = prefs_update
                return result

            rag_intent = rag_query_from_prompt(text)
            if rag_intent:
                rag_hits = select_rag_hits(rag_intent, limit=5 if rag_intent.get("mode") == "tasks" else 3)
                if rag_hits:
                    needs_smart = rag_needs_smart_llm(text)
                    if needs_smart and not cloud_llm_available():
                        reply = "Understood. For this intelligent wiki/repo query I need a cloud LLM (set OPENAI_API_KEY or GEMINI_API_KEY)."
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

            # ── AI Router path (JARVIS_USE_AI_ROUTER=1) ──────────────────────
            if _ai_router_enabled:
                router_obj = _make_ai_router()
                is_voice = source == "voice" or mode == "orb"
                history = _get_llm_history(session_id, owner_key)
                decision = router_obj.resolve(
                    user_id=effective_user_id,
                    role=role,
                    text=text,
                    history_len=len(history),
                    voice_mode=is_voice,
                )
                confirmed = (x_jarvis_confirm or "").strip().lower() == "billing"
                pf = router_obj.preflight(decision, user_id=effective_user_id, confirmed=confirmed)
                if not pf.allowed:
                    if pf.requires_confirmation:
                        reply_text = f"This request uses {decision.model} (~{decision.estimated_cost_chf:.4f} CHF). Confirm by resending with X-Jarvis-Confirm: billing."
                        current("chat_history").append_message(session_id, "jarvis", reply_text, owner_key=owner_key, owner_user_id=effective_user_id)
                        return {"reply": reply_text, "data": {"billing_confirmation": pf.billing_confirmation}, "session_id": session_id}
                    reply_text = build_context_reply(text)
                    current("chat_history").append_message(session_id, "jarvis", reply_text, owner_key=owner_key, owner_user_id=effective_user_id)
                    return {"reply": reply_text, "data": {"billing_blocked": pf.reason}, "session_id": session_id}
                user_prefs = current("user_preferences_store").get(effective_user_id) if effective_user_id else {}
                display_name = (user_prefs or {}).get("display_name")
                persona_tone = (user_prefs or {}).get("persona_tone", "formal")
                sys_prompt = build_system_prompt(display_name, voice_mode=is_voice, persona_tone=persona_tone)
                messages = history + [{"role": "user", "content": text}]
                try:
                    reply_text = router_obj.run_once(decision, messages=messages, system_prompt=sys_prompt, max_tokens=pf.clamped_max_tokens)
                    current("chat_history").append_message(session_id, "jarvis", reply_text, owner_key=owner_key, owner_user_id=effective_user_id)
                    router_obj.finalize(decision, user_id=effective_user_id, conversation_id=session_id, input_tokens=len(text) // 4, output_tokens=len(reply_text) // 4)
                    return {"reply": reply_text, "data": {"model_tier": decision.tier.value, "provider": decision.provider}, "session_id": session_id}
                except Exception:
                    _log.exception("AI router provider error [%s/%s uid=%s]", decision.provider, decision.model, effective_user_id)
                    router_obj.finalize(decision, user_id=effective_user_id, conversation_id=session_id, input_tokens=0, output_tokens=0, status="error", error="provider_error")
                    fallback_dec = router_obj.resolve_system_fallback(decision)
                    if fallback_dec:
                        try:
                            reply_text = router_obj.run_once(fallback_dec, messages=messages, system_prompt=sys_prompt, max_tokens=fallback_dec.clamped_max_tokens)
                            current("chat_history").append_message(session_id, "jarvis", reply_text, owner_key=owner_key, owner_user_id=effective_user_id)
                            router_obj.finalize(fallback_dec, user_id=effective_user_id, conversation_id=session_id, input_tokens=len(text) // 4, output_tokens=len(reply_text) // 4)
                            return {"reply": reply_text, "data": {"model_tier": fallback_dec.tier.value, "provider": fallback_dec.provider, "byok_fallback": True}, "session_id": session_id}
                        except Exception:
                            _log.exception("AI router fallback error [%s/%s uid=%s]", fallback_dec.provider, fallback_dec.model, effective_user_id)
                    fallback = build_context_reply(text)
                    current("chat_history").append_message(session_id, "jarvis", fallback, owner_key=owner_key, owner_user_id=effective_user_id)
                    return {"reply": fallback, "data": {"route": "offline_assistant", "reason": "cloud_unavailable"}, "session_id": session_id}

            # AI router disabled — use offline fallback
            reply = build_context_reply(text)
            current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
            return {"reply": reply, "data": {"route": "offline_assistant", "reason": "router_disabled"}, "session_id": session_id}
        finally:
            current("status_hub").end(status_token)

    @router.post("/chat/stream")
    def chat_stream(
        payload: ChatIn,
        authorization: str | None = Header(default=None),
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_guest_key: str | None = Header(default=None),
        x_jarvis_mode: str | None = Header(default=None),
        x_jarvis_role: str | None = Header(default=None),
        x_jarvis_confirm: str | None = Header(default=None),
    ):
        text = (payload.text or "").strip()
        source = (payload.source or "text").strip().lower()
        mode = (x_jarvis_mode or "").strip().lower()
        identity_session = get_identity_session(x_jarvis_session)
        owner_key, effective_user_id = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        active_user = identity_session["user"] if identity_session else None
        role = normalize_role(active_user.get("role") if active_user else x_jarvis_role or "guest_restricted")

        if mode == "orb" and not active_user:
            def _err():
                yield f"data: {_json.dumps({'type': 'error', 'detail': 'orb login required'})}\n\n"
            return StreamingResponse(_err(), media_type="text/event-stream")

        if source == "voice" and wakeword_enabled():
            stripped, detected = strip_wakeword(text)
            if not detected:
                phrase = deps["wakeword_phrase"]()
                _wake_reply = f"Awaiting wake word. Say: '{phrase}'."
                def _wake(r=_wake_reply, p=phrase, sid=payload.session_id):
                    yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': {'wakeword_required': p}})}\n\n"
                return StreamingResponse(_wake(), media_type="text/event-stream")
            text = stripped

        session = current("chat_history").ensure_session(payload.session_id, owner_key=owner_key, owner_user_id=effective_user_id)
        session_id = session["id"]

        if not text:
            def _empty():
                yield f"data: {_json.dumps({'type': 'done', 'reply': 'Say that again.', 'session_id': session_id})}\n\n"
            return StreamingResponse(_empty(), media_type="text/event-stream")

        rl_key = effective_user_id or (x_jarvis_guest_key or "anon")
        if not _rate.allow(f"chat:{rl_key}", limit=30, window=60.0):
            def _rl():
                yield f"data: {_json.dumps({'type': 'error', 'detail': 'Rate limit exceeded — slow down'})}\n\n"
            return StreamingResponse(_rl(), media_type="text/event-stream")

        token = deps["bearer_token_from_header"](authorization)
        if token and not is_token_active(current("tokens"), token):
            token = None

        current("chat_history").append_message(session_id, "user", text, owner_key=owner_key, owner_user_id=effective_user_id)
        granted_permissions = sorted(resolve_effective_permissions(role, effective_user_id, current("membership_store"), current("permission_store")))
        status_token = current("status_hub").begin("processing", source=source, mode=mode or "chat")

        try:
            home_assistant_service = current("home_assistant_service")
            pending_home_assistant_action = current("chat_history").get_pending_home_assistant_action(session_id, owner_key=owner_key)
            ha_intent = (
                execute_home_assistant_chat_intent(
                    home_assistant_service,
                    text,
                    user_id=effective_user_id,
                    role=role,
                    pending_action=pending_home_assistant_action,
                )
                if home_assistant_service and pending_home_assistant_action
                else None
            )
            if not ha_intent and home_assistant_service and auth_capabilities(effective_user_id, role).get("home_assistant_access"):
                ha_intent = execute_home_assistant_chat_intent(home_assistant_service, text, user_id=effective_user_id, role=role)

            if ha_intent:
                reply = ha_intent.get("reply", "Done.")
                data = ha_intent.get("data") or {}
                follow_up = data.get("follow_up")
                if isinstance(follow_up, dict):
                    current("chat_history").set_pending_home_assistant_action(session_id, follow_up, owner_key=owner_key, owner_user_id=effective_user_id)
                else:
                    current("chat_history").clear_pending_home_assistant_action(session_id, owner_key=owner_key, owner_user_id=effective_user_id)
                current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                def _ha(r=reply, d=data, sid=session_id):
                    yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': d})}\n\n"
                return StreamingResponse(_ha(), media_type="text/event-stream")

            _skill_prefs = current("user_preferences_store").get(effective_user_id) if effective_user_id else {}
            skill_first = try_skill(text, role=role, token=token, granted_permissions=granted_permissions, user_prefs=_skill_prefs)
            if skill_first:
                reply = skill_first.get("reply", "Done.")
                data = dict(skill_first.get("data") or {})
                save_to_prefs = data.pop("save_to_prefs", None)
                prefs_update = None
                if save_to_prefs and effective_user_id:
                    prefs_update = current("user_preferences_store").update(effective_user_id, save_to_prefs)
                if data.get("error") == "permission_denied":
                    current("audit_log").write("permission_denied", {"role": role, "source": source, "text": text, "data": data, "path": "try_skill"})
                if data.get("error") == "emergency_stop":
                    current("audit_log").write("emergency_stop_blocked", {"role": role, "source": source, "text": text, "path": "try_skill"})
                current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                def _skill(r=reply, d=data, sid=session_id, pu=prefs_update):
                    event: dict = {"type": "done", "reply": r, "session_id": sid, "data": d}
                    if pu:
                        event["prefs_update"] = pu
                    yield f"data: {_json.dumps(event)}\n\n"
                return StreamingResponse(_skill(), media_type="text/event-stream")

            rag_intent = rag_query_from_prompt(text)
            if rag_intent:
                rag_hits = select_rag_hits(rag_intent, limit=5 if rag_intent.get("mode") == "tasks" else 3)
                if rag_hits:
                    needs_smart = rag_needs_smart_llm(text)
                    if needs_smart and not cloud_llm_available():
                        reply = "Understood. Für diese intelligente Wiki/Repo-Auswertung brauche ich Cloud-KI (OPENAI_API_KEY oder GEMINI_API_KEY)."
                        data = {"route": "rag", "rag": rag_hits, "intent": rag_intent, "error": "cloud_llm_required"}
                        current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                        def _rag_no_cloud(r=reply, d=data, sid=session_id):
                            yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': d})}\n\n"
                        return StreamingResponse(_rag_no_cloud(), media_type="text/event-stream")

                    if needs_smart and cloud_llm_available():
                        try:
                            reply = rag_llm_answer(text, rag_hits)
                        except Exception:
                            reply = format_rag_reply(rag_intent, rag_hits)
                    else:
                        reply = format_rag_reply(rag_intent, rag_hits)

                    data = {"route": "rag", "rag": rag_hits, "intent": rag_intent, "smart": needs_smart}
                    current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
                    def _rag(r=reply, d=data, sid=session_id):
                        yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': d})}\n\n"
                    return StreamingResponse(_rag(), media_type="text/event-stream")

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
                def _engine(r=summary, d=data, sid=session_id):
                    yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': d})}\n\n"
                return StreamingResponse(_engine(), media_type="text/event-stream")

            # ── AI Router streaming path (JARVIS_USE_AI_ROUTER=1) ────────────
            if _ai_router_enabled:
                router_obj = _make_ai_router()
                is_voice_r = source == "voice" or mode == "orb"
                history_r = _get_llm_history(session_id, owner_key)
                decision_r = router_obj.resolve(
                    user_id=effective_user_id,
                    role=role,
                    text=text,
                    history_len=len(history_r),
                    voice_mode=is_voice_r,
                )
                confirmed_r = (x_jarvis_confirm or "").strip().lower() == "billing"
                pf_r = router_obj.preflight(decision_r, user_id=effective_user_id, confirmed=confirmed_r)

                if not pf_r.allowed:
                    if pf_r.requires_confirmation:
                        _conf_reply = f"This request uses {decision_r.model} (~{decision_r.estimated_cost_chf:.4f} CHF). Confirm by resending with X-Jarvis-Confirm: billing."
                        current("chat_history").append_message(session_id, "jarvis", _conf_reply, owner_key=owner_key, owner_user_id=effective_user_id)
                        def _billing_confirm(r=_conf_reply, bc=pf_r.billing_confirmation, sid=session_id):
                            yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': {'billing_confirmation': bc}})}\n\n"
                        return StreamingResponse(_billing_confirm(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
                    _block_reply = build_context_reply(text)
                    current("chat_history").append_message(session_id, "jarvis", _block_reply, owner_key=owner_key, owner_user_id=effective_user_id)
                    def _billing_block(r=_block_reply, reason=pf_r.reason, sid=session_id):
                        yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': {'billing_blocked': reason}})}\n\n"
                    return StreamingResponse(_billing_block(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

                user_prefs_r = current("user_preferences_store").get(effective_user_id) if effective_user_id else {}
                display_name_r = (user_prefs_r or {}).get("display_name")
                persona_tone_r = (user_prefs_r or {}).get("persona_tone", "formal")
                sys_prompt_r = build_system_prompt(display_name_r, voice_mode=is_voice_r, persona_tone=persona_tone_r)
                messages_r = history_r + [{"role": "user", "content": text}]
                stream_status_token_r = status_token
                status_token = None

                def router_stream(txt=text, sid=session_id, ok=owner_key, ouid=effective_user_id, dec=decision_r, ro=router_obj, msgs=messages_r, sp=sys_prompt_r, mt=pf_r.clamped_max_tokens, stk=stream_status_token_r):
                    try:
                        full = ""
                        for chunk in ro.run_stream(dec, messages=msgs, system_prompt=sp, max_tokens=mt):
                            full += chunk
                            yield f"data: {_json.dumps({'type': 'token', 'token': chunk})}\n\n"
                        current("chat_history").append_message(sid, "jarvis", full, owner_key=ok, owner_user_id=ouid)
                        ro.finalize(dec, user_id=ouid, conversation_id=sid, input_tokens=len(txt) // 4, output_tokens=len(full) // 4)
                        yield f"data: {_json.dumps({'type': 'done', 'reply': full, 'session_id': sid, 'data': {'model_tier': dec.tier.value, 'provider': dec.provider}})}\n\n"
                    except Exception:
                        _log.exception("AI router stream error [%s/%s uid=%s]", dec.provider, dec.model, ouid)
                        ro.finalize(dec, user_id=ouid, conversation_id=sid, input_tokens=0, output_tokens=0, status="error", error="provider_error")
                        fb_dec = ro.resolve_system_fallback(dec)
                        if fb_dec:
                            try:
                                fb_text = ro.run_once(fb_dec, messages=msgs, system_prompt=sp, max_tokens=mt)
                                current("chat_history").append_message(sid, "jarvis", fb_text, owner_key=ok, owner_user_id=ouid)
                                ro.finalize(fb_dec, user_id=ouid, conversation_id=sid, input_tokens=len(txt) // 4, output_tokens=len(fb_text) // 4)
                                yield f"data: {_json.dumps({'type': 'token', 'token': fb_text})}\n\n"
                                yield f"data: {_json.dumps({'type': 'done', 'reply': fb_text, 'session_id': sid, 'data': {'model_tier': fb_dec.tier.value, 'provider': fb_dec.provider, 'byok_fallback': True}})}\n\n"
                                return
                            except Exception:
                                _log.exception("AI router fallback stream error [%s/%s uid=%s]", fb_dec.provider, fb_dec.model, ouid)
                        fallback = build_context_reply(txt)
                        current("chat_history").append_message(sid, "jarvis", fallback, owner_key=ok, owner_user_id=ouid)
                        yield f"data: {_json.dumps({'type': 'done', 'reply': fallback, 'session_id': sid, 'data': {'route': 'offline_assistant', 'reason': 'cloud_unavailable'}})}\n\n"
                    finally:
                        current("status_hub").end(stk)

                return StreamingResponse(
                    router_stream(),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )

            # AI router disabled — use offline fallback
            reply = build_context_reply(text)
            current("chat_history").append_message(session_id, "jarvis", reply, owner_key=owner_key, owner_user_id=effective_user_id)
            def _router_disabled(r=reply, sid=session_id):
                yield f"data: {_json.dumps({'type': 'done', 'reply': r, 'session_id': sid, 'data': {'route': 'offline_assistant', 'reason': 'router_disabled'}})}\n\n"
            return StreamingResponse(_router_disabled(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        finally:
            current("status_hub").end(status_token)

    @router.get("/chat/sessions")
    def list_chat_sessions(x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        return {"sessions": current("chat_history").list_sessions(owner_key=owner_key)}

    @router.get("/chat/search")
    def search_chat_messages(q: str = "", limit: int = 30, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        hits = current("chat_history").search_messages(q, owner_key=owner_key, limit=limit)
        return {"hits": hits}

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

    @router.patch("/chat/sessions/{session_id}")
    def update_chat_session(payload: ChatSessionUpdateIn, session_id: str, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        session = current("chat_history").rename_session(session_id, payload.title, owner_key=owner_key)
        if not session:
            raise HTTPException(404, "session not found")
        return session

    @router.post("/chat/sessions/{session_id}/pending-home-assistant/clear")
    def clear_pending_home_assistant_action(session_id: str, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, owner_user_id = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        session = current("chat_history").get_session(session_id, owner_key=owner_key)
        if not session:
            raise HTTPException(404, "session not found")
        current("chat_history").clear_pending_home_assistant_action(session_id, owner_key=owner_key, owner_user_id=owner_user_id)
        return {"ok": True, "id": session_id}

    @router.post("/chat/sessions/{session_id}/pending-billing/clear")
    def clear_pending_billing(session_id: str, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        """Dismiss an expensive-model billing confirmation dialog. Stateless — confirmation is per-request."""
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        session = current("chat_history").get_session(session_id, owner_key=owner_key)
        if not session:
            raise HTTPException(404, "session not found")
        return {"ok": True, "id": session_id}

    @router.delete("/chat/sessions/{session_id}")
    def delete_chat_session(session_id: str, x_jarvis_session: str | None = Header(default=None), x_jarvis_guest_key: str | None = Header(default=None)):
        owner_key, _ = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        deleted = current("chat_history").delete_session(session_id, owner_key=owner_key)
        if not deleted:
            raise HTTPException(404, "session not found")
        return {"ok": True, "id": session_id}

    @router.get("/chat/daily-briefing")
    def daily_briefing(
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_guest_key: str | None = Header(default=None),
    ):
        _, effective_user_id = chat_owner_key(x_jarvis_session, x_jarvis_guest_key)
        identity_session = get_identity_session(x_jarvis_session)
        active_user = identity_session["user"] if identity_session else None
        role = normalize_role(active_user.get("role") if active_user else "guest_restricted")
        granted_permissions = sorted(resolve_effective_permissions(
            role, effective_user_id, current("membership_store"), current("permission_store")
        ))
        user_prefs = current("user_preferences_store").get(effective_user_id) if effective_user_id else {}

        skill_result = try_skill(
            "briefing",
            role=role,
            token=None,
            granted_permissions=granted_permissions,
            user_prefs=user_prefs,
        )
        base_text: str = skill_result.get("reply", "Good day, sir. All systems nominal.") if skill_result else "All systems nominal."

        calendar_lines: list[str] = []
        ha_service = current("home_assistant_service")
        if ha_service:
            today = _date.today().isoformat()
            try:
                for item in ha_service.store.list_calendar_items():
                    starts = (item.get("starts_at") or "")[:10]
                    if starts == today and item.get("title"):
                        time_part = item.get("starts_at", "")
                        if "T" in time_part:
                            hm = time_part.split("T")[1][:5]
                            calendar_lines.append(f"{hm} — {item['title']}")
                        else:
                            calendar_lines.append(item["title"])
            except Exception:
                pass

        if calendar_lines:
            cal_block = "Today's schedule: " + "; ".join(calendar_lines) + "."
            text = base_text.rstrip(".") + " " + cal_block
        else:
            text = base_text

        return {"text": text, "date": _date.today().isoformat()}

    @router.get("/sys/metrics")
    def sys_metrics(x_jarvis_session: str | None = Header(default=None)):
        require_identity_session(x_jarvis_session)
        try:
            with open("/proc/loadavg") as f:
                la1 = float(f.read().split()[0])
            cpu_count = len([l for l in open("/proc/cpuinfo") if l.startswith("processor")]) or 1
            cpu_pct = min(round(la1 / cpu_count * 100, 1), 100.0)
        except Exception:
            cpu_pct = 0.0

        try:
            mem: dict[str, int] = {}
            for line in open("/proc/meminfo"):
                parts = line.split()
                if parts[0].rstrip(":") in ("MemTotal", "MemAvailable"):
                    mem[parts[0].rstrip(":")] = int(parts[1])
            total_kb = mem.get("MemTotal", 1)
            avail_kb = mem.get("MemAvailable", total_kb)
            used_kb = total_kb - avail_kb
            ram_pct = round(used_kb / total_kb * 100, 1)
            ram_used_gb = round(used_kb / 1024 / 1024, 2)
            ram_total_gb = round(total_kb / 1024 / 1024, 2)
        except Exception:
            ram_pct, ram_used_gb, ram_total_gb = 0.0, 0.0, 0.0

        try:
            sv = _os.statvfs("/")
            disk_total = sv.f_frsize * sv.f_blocks
            disk_free = sv.f_frsize * sv.f_bavail
            disk_used = disk_total - disk_free
            disk_pct = round(disk_used / disk_total * 100, 1) if disk_total else 0.0
            disk_used_gb = round(disk_used / 1024**3, 1)
            disk_total_gb = round(disk_total / 1024**3, 1)
        except Exception:
            disk_pct, disk_used_gb, disk_total_gb = 0.0, 0.0, 0.0

        try:
            uptime_sec = float(open("/proc/uptime").read().split()[0])
            days, rem = divmod(int(uptime_sec), 86400)
            hours, rem = divmod(rem, 3600)
            mins = rem // 60
            uptime_str = (f"{days}d " if days else "") + f"{hours}h {mins}m"
        except Exception:
            uptime_str = "—"

        return {
            "cpu": {"pct": cpu_pct},
            "ram": {"pct": ram_pct, "used_gb": ram_used_gb, "total_gb": ram_total_gb},
            "disk": {"pct": disk_pct, "used_gb": disk_used_gb, "total_gb": disk_total_gb},
            "uptime": uptime_str,
            "ts": int(_time.time()),
        }

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
