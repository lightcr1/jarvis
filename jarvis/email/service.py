from __future__ import annotations

import os
import time
import uuid
from typing import Callable

from .client import ImapSmtpClient

REQUIRED_CREDENTIAL_FIELDS = (
    "imap_host", "imap_port", "imap_username", "imap_password",
    "smtp_host", "smtp_port", "smtp_username", "smtp_password",
)
INTEGRATION_NAME = "email"


def _emergency_stop_active() -> bool:
    return (os.getenv("JARVIS_EMERGENCY_STOP") or "0").strip().lower() in {"1", "true", "yes", "on"}


def _validate_credential_fields(fields: dict) -> dict[str, str]:
    missing = [f for f in REQUIRED_CREDENTIAL_FIELDS if not str(fields.get(f) or "").strip()]
    if missing:
        raise ValueError(f"missing required field(s): {', '.join(missing)}")
    return {k: str(fields[k]).strip() for k in REQUIRED_CREDENTIAL_FIELDS}


class EmailAccessError(PermissionError):
    pass


def summarize_email_body(body: str, *, get_provider=None, get_gemini=None, get_openai=None) -> str:
    """Pure LLM glue, reused by both the /email summarize endpoint and the "summarize
    email from X" chat skill — mirrors assistant_domain.py's `_generate_task_steps`.
    """
    text = (body or "").strip()
    if not text:
        return "(empty message)"
    if not get_provider:
        return text[:280] + ("..." if len(text) > 280 else "")
    prompt = f"Summarize this email in 2-3 short sentences, plain text, no preamble:\n\n{text[:4000]}"
    try:
        provider = get_provider()
        if provider == "gemini" and os.getenv("GEMINI_API_KEY") and get_gemini:
            client = get_gemini()
            model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
            resp = client.models.generate_content(model=model, contents=[{"role": "user", "parts": [{"text": prompt}]}])
            return (getattr(resp, "text", "") or "").strip() or text[:280]
        if os.getenv("OPENAI_API_KEY") and get_openai:
            client = get_openai()
            model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": "You are J.A.R.V.I.S from Iron Man."}, {"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=180,
            )
            return (resp.choices[0].message.content or "").strip() or text[:280]
    except Exception:
        pass
    return text[:280] + ("..." if len(text) > 280 else "")


def draft_reply_body(instruction: str, original_body: str, *, get_provider=None, get_gemini=None, get_openai=None) -> str:
    if not get_provider:
        return instruction.strip()
    prompt = (
        "Draft a short, professional email reply body (no subject line, no salutation "
        "boilerplate beyond a simple greeting/sign-off) based on this instruction and the "
        f"original message it replies to.\n\nInstruction: {instruction}\n\n"
        f"Original message:\n{(original_body or '')[:3000]}"
    )
    try:
        provider = get_provider()
        if provider == "gemini" and os.getenv("GEMINI_API_KEY") and get_gemini:
            client = get_gemini()
            model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
            resp = client.models.generate_content(model=model, contents=[{"role": "user", "parts": [{"text": prompt}]}])
            return (getattr(resp, "text", "") or "").strip() or instruction.strip()
        if os.getenv("OPENAI_API_KEY") and get_openai:
            client = get_openai()
            model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": "You are J.A.R.V.I.S from Iron Man, drafting an email on your principal's behalf."}, {"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=300,
            )
            return (resp.choices[0].message.content or "").strip() or instruction.strip()
    except Exception:
        pass
    return instruction.strip()


class EmailService:
    def __init__(
        self,
        *,
        message_store,
        draft_store,
        credential_store,
        user_store,
        membership_store,
        permission_store,
        resolve_effective_permissions,
        normalize_role,
        audit_log=None,
        client_factory: Callable[[dict], ImapSmtpClient] | None = None,
    ) -> None:
        self.message_store = message_store
        self.draft_store = draft_store
        self.credential_store = credential_store
        self.user_store = user_store
        self.membership_store = membership_store
        self.permission_store = permission_store
        self.resolve_effective_permissions = resolve_effective_permissions
        self.normalize_role = normalize_role
        self.audit_log = audit_log
        self.client_factory = client_factory or (lambda creds: ImapSmtpClient(
            creds["imap_host"], creds["imap_port"], creds["imap_username"], creds["imap_password"],
            creds["smtp_host"], creds["smtp_port"], creds["smtp_username"], creds["smtp_password"],
        ))

    def _write_audit(self, event: str, *, actor_user_id: str | None, actor_role: str | None, payload: dict | None = None) -> None:
        if not self.audit_log:
            return
        body = {"actor_user_id": actor_user_id, "actor_role": self.normalize_role(actor_role), **(payload or {})}
        try:
            self.audit_log.write(event, body)
        except Exception:
            return

    def _effective_permissions(self, user_id: str | None, role: str | None) -> set[str]:
        return set(self.resolve_effective_permissions(self.normalize_role(role), user_id, self.membership_store, self.permission_store))

    def require_access(self, *, user_id: str | None, role: str | None, required_permission: str) -> dict[str, object]:
        normalized_role = self.normalize_role(role)
        effective = self._effective_permissions(user_id, role)
        if normalized_role != "admin" and required_permission not in effective:
            raise EmailAccessError(f"missing permission: {required_permission}")
        return {"role": normalized_role, "effective_permissions": sorted(effective)}

    def _owned_message(self, message_id: str, *, user_id: str | None, role: str | None) -> dict:
        message = self.message_store.get_message(message_id)
        if not message:
            raise LookupError("message not found")
        if message.get("user_id") != user_id and self.normalize_role(role) != "admin":
            raise LookupError("message not found")
        return message

    def _owned_draft(self, draft_id: str, *, user_id: str | None, role: str | None) -> dict:
        draft = self.draft_store.get_draft(draft_id)
        if not draft:
            raise LookupError("draft not found")
        if draft.get("user_id") != user_id and self.normalize_role(role) != "admin":
            raise LookupError("draft not found")
        return draft

    def set_credentials(self, fields: dict[str, str], *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        clean = _validate_credential_fields(fields)
        record = self.credential_store.set_credentials(user_id, INTEGRATION_NAME, clean)
        self._write_audit("email_credentials_set", actor_user_id=user_id, actor_role=role)
        return {"policy": policy, "credentials": record}

    def credentials_status(self, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        return {"policy": policy, "status": self.credential_store.status(user_id, INTEGRATION_NAME)}

    def delete_credentials(self, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        deleted = self.credential_store.delete_credentials(user_id, INTEGRATION_NAME)
        self._write_audit("email_credentials_deleted", actor_user_id=user_id, actor_role=role)
        return {"policy": policy, "deleted": deleted}

    def _client_for(self, user_id: str | None, account_id: str | None = None) -> tuple[ImapSmtpClient | None, str | None]:
        resolved = account_id or self.credential_store.primary_account_id(user_id or "", INTEGRATION_NAME)
        if not resolved:
            return None, None
        creds = self.credential_store.get_credentials(user_id or "", INTEGRATION_NAME, resolved)
        if not creds:
            return None, resolved
        return self.client_factory(creds), resolved

    def sync_inbox(self, *, user_id: str | None, role: str | None, account_id: str | None = None, folder: str = "INBOX", limit: int = 20) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        client, resolved_account = self._client_for(user_id, account_id)
        if client is None:
            raise LookupError("email not configured")
        fetched = client.fetch_recent_messages(folder, limit)
        messages = self.message_store.upsert_messages(user_id or "", folder, fetched, account_id=resolved_account)
        self._write_audit("email_synced", actor_user_id=user_id, actor_role=role, payload={"count": len(messages), "account_id": resolved_account})
        return {"policy": policy, "synced_count": len(messages), "account_id": resolved_account}

    def list_messages(self, *, user_id: str | None, role: str | None, folder: str | None = None, unread_only: bool = False, account_id: str | None = None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        resolved = account_id or self.credential_store.primary_account_id(user_id or "", INTEGRATION_NAME)
        return {"policy": policy, "messages": self.message_store.list_messages(user_id or "", folder, unread_only, account_id=resolved)}

    def get_message(self, message_id: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        return {"policy": policy, "message": self._owned_message(message_id, user_id=user_id, role=role)}

    def fetch_body(self, message_id: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        message = self._owned_message(message_id, user_id=user_id, role=role)
        client, _ = self._client_for(message.get("user_id"), message.get("account_id"))
        if client is None:
            raise LookupError("email not configured")
        body = client.fetch_message_body(message["uid"], message.get("folder", "INBOX"))
        if body is None:
            raise RuntimeError("failed to fetch message body")
        return {"policy": policy, "message": message, "body": body}

    def mark_read(self, message_id: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        message = self._owned_message(message_id, user_id=user_id, role=role)
        client, _ = self._client_for(message.get("user_id"), message.get("account_id"))
        if client is not None:
            client.mark_read(message["uid"], message.get("folder", "INBOX"))
        updated = self.message_store.set_read(message_id, True)
        return {"policy": policy, "message": updated}

    def set_summary(self, message_id: str, summary: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        self._owned_message(message_id, user_id=user_id, role=role)
        updated = self.message_store.set_summary(message_id, summary)
        return {"policy": policy, "message": updated}

    def create_draft(self, payload: dict, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        to = str(payload.get("to") or "").strip()
        subject = str(payload.get("subject") or "").strip()
        body = str(payload.get("body") or "").strip()
        if not to or not body:
            raise ValueError("draft requires 'to' and 'body'")
        account_id = payload.get("account_id") or self.credential_store.primary_account_id(user_id or "", INTEGRATION_NAME)
        now = int(time.time())
        draft = self.draft_store.add_draft({
            "user_id": user_id,
            "account_id": account_id,
            "to": to,
            "subject": subject or "(no subject)",
            "body": body,
            "in_reply_to_message_id": payload.get("in_reply_to_message_id"),
            "status": "pending_approval",
            "created_at": now,
            "updated_at": now,
        })
        self._write_audit("email_draft_created", actor_user_id=user_id, actor_role=role, payload={"draft_id": draft["id"]})
        return {"policy": policy, "draft": draft}

    def list_drafts(self, *, user_id: str | None, role: str | None, status: str | None = None, account_id: str | None = None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        resolved = account_id or self.credential_store.primary_account_id(user_id or "", INTEGRATION_NAME)
        return {"policy": policy, "drafts": self.draft_store.list_drafts(user_id or "", status, account_id=resolved)}

    def discard_draft(self, draft_id: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        draft = self._owned_draft(draft_id, user_id=user_id, role=role)
        if draft.get("status") != "pending_approval":
            raise ValueError("draft is not pending approval")
        updated = self.draft_store.update_draft(draft_id, {"status": "discarded", "updated_at": int(time.time())})
        self._write_audit("email_draft_discarded", actor_user_id=user_id, actor_role=role, payload={"draft_id": draft_id})
        return {"policy": policy, "draft": updated}

    @staticmethod
    def _approval_snapshot(draft: dict) -> dict:
        return {key: draft.get(key) for key in (
            "id", "user_id", "account_id", "to", "subject", "body", "in_reply_to_message_id",
        )}

    def approval_snapshot(self, draft_id: str, *, user_id: str | None, role: str | None) -> dict:
        self.require_access(user_id=user_id, role=role, required_permission="email.write")
        draft = self._owned_draft(draft_id, user_id=user_id, role=role)
        if draft.get("status") != "pending_approval":
            raise ValueError("draft is not pending approval")
        return self._approval_snapshot(draft)

    def send_draft(self, draft_id: str, *, user_id: str | None, role: str | None,
                   confirm: bool = False, approved_snapshot: dict | None = None) -> dict:
        if _emergency_stop_active():
            raise PermissionError("emergency stop is active — write actions are blocked")
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        draft = self._owned_draft(draft_id, user_id=user_id, role=role)
        if draft.get("status") != "pending_approval":
            raise ValueError("draft is not pending approval")
        if not confirm:
            return {"policy": policy, "draft": draft, "status": "confirmation_required"}
        if approved_snapshot is not None and self._approval_snapshot(draft) != approved_snapshot:
            raise PermissionError("draft changed since approval")
        client, _ = self._client_for(draft.get("user_id"), draft.get("account_id"))
        if client is None:
            raise LookupError("email not configured")
        sent = client.send_message(draft["to"], draft["subject"], draft["body"], in_reply_to=draft.get("in_reply_to_message_id"))
        if not sent:
            raise RuntimeError("failed to send message")
        updated = self.draft_store.update_draft(draft_id, {"status": "sent", "updated_at": int(time.time()), "sent_at": int(time.time())})
        self._write_audit("email_draft_sent", actor_user_id=user_id, actor_role=role, payload={"draft_id": draft_id})
        return {"policy": policy, "draft": updated, "status": "sent"}

    def list_accounts(self, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.read")
        return {"policy": policy, "accounts": self.credential_store.list_accounts(user_id, INTEGRATION_NAME)}

    def add_account(self, fields: dict[str, str], label: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        clean_label = (label or "").strip()
        if not clean_label:
            raise ValueError("label is required")
        clean = _validate_credential_fields(fields)
        account_id = uuid.uuid4().hex[:12]
        record = self.credential_store.set_credentials(user_id, INTEGRATION_NAME, clean, account_id=account_id, label=clean_label)
        self._write_audit("email_account_added", actor_user_id=user_id, actor_role=role, payload={"account_id": account_id})
        return {"policy": policy, "account": record}

    def update_account(self, account_id: str, fields: dict[str, str], label: str | None, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        if not self.credential_store.has_credentials(user_id or "", INTEGRATION_NAME, account_id):
            raise LookupError("account not found")
        clean = _validate_credential_fields(fields)
        clean_label = label.strip() if label else None
        record = self.credential_store.set_credentials(user_id, INTEGRATION_NAME, clean, account_id=account_id, label=clean_label)
        self._write_audit("email_account_updated", actor_user_id=user_id, actor_role=role, payload={"account_id": account_id})
        return {"policy": policy, "account": record}

    def delete_account(self, account_id: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        was_primary = self.credential_store.primary_account_id(user_id or "", INTEGRATION_NAME) == account_id
        deleted = self.credential_store.delete_credentials(user_id or "", INTEGRATION_NAME, account_id)
        if deleted and was_primary:
            remaining = self.credential_store.list_accounts(user_id or "", INTEGRATION_NAME)
            if remaining:
                self.credential_store.set_primary_account(user_id or "", INTEGRATION_NAME, remaining[0]["account_id"])
        self._write_audit("email_account_deleted", actor_user_id=user_id, actor_role=role, payload={"account_id": account_id})
        return {"policy": policy, "deleted": deleted}

    def set_primary_account(self, account_id: str, *, user_id: str | None, role: str | None) -> dict:
        policy = self.require_access(user_id=user_id, role=role, required_permission="email.write")
        if not self.credential_store.set_primary_account(user_id or "", INTEGRATION_NAME, account_id):
            raise LookupError("account not found")
        self._write_audit("email_account_primary_set", actor_user_id=user_id, actor_role=role, payload={"account_id": account_id})
        return {"policy": policy, "primary_account_id": account_id}
