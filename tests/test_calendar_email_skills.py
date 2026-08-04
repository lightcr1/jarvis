"""Chat-skill level tests for calendar/email natural-language routing in
try_skill() (V2 Phase 5). Uses lightweight fake service stand-ins rather than the
full permission-gated CalendarService/EmailService — those are covered in
test_calendar.py / test_email.py. This file only exercises regex parsing, reply
text, and data routing.
"""
from __future__ import annotations

from unittest.mock import Mock

from jarvis.assistant_domain import try_skill


class FakeCalendarService:
    def __init__(self):
        self.events: list[dict] = []
        self.created_payloads: list[dict] = []
        self.configured = True

    def list_events(self, *, user_id, role, start=None, end=None):
        return {"events": [e for e in self.events if (start is None or e["end"] >= start) and (end is None or e["start"] <= end)]}

    def create_event(self, payload, *, user_id, role, force=False):
        self.created_payloads.append(payload)
        if not self.configured:
            raise LookupError("calendar not configured")
        conflicts = [e for e in self.events if e["start"] < payload["end"] and e["end"] > payload["start"]]
        if conflicts and not force:
            return {"created": False, "conflicts": conflicts}
        event = {"id": f"cal-{len(self.events) + 1}", **payload}
        self.events.append(event)
        return {"created": True, "event": event, "conflicts": conflicts}


class FakeEmailService:
    def __init__(self):
        self.messages: list[dict] = []
        self.drafts: list[dict] = []
        self.configured = True
        self._next_draft_id = 1

    def sync_inbox(self, *, user_id, role, limit=20):
        if not self.configured:
            raise LookupError("email not configured")
        return {"synced_count": len(self.messages)}

    def list_messages(self, *, user_id, role, folder=None, unread_only=False):
        items = self.messages
        if unread_only:
            items = [m for m in items if not m.get("read")]
        return {"messages": items}

    def fetch_body(self, message_id, *, user_id, role):
        message = next(m for m in self.messages if m["id"] == message_id)
        return {"body": message.get("body", ""), "message": message}

    def create_draft(self, payload, *, user_id, role):
        draft = {"id": f"draft-{self._next_draft_id}", "status": "pending_approval", **payload}
        self._next_draft_id += 1
        self.drafts.append(draft)
        return {"draft": draft}

    def list_drafts(self, *, user_id, role, status=None):
        items = self.drafts
        if status:
            items = [d for d in items if d["status"] == status]
        return {"drafts": items}

    def send_draft(self, draft_id, *, user_id, role, confirm=False):
        draft = next(d for d in self.drafts if d["id"] == draft_id)
        if not confirm:
            return {"draft": draft, "status": "confirmation_required"}
        draft["status"] = "sent"
        return {"draft": draft, "status": "sent"}

    def discard_draft(self, draft_id, *, user_id, role):
        draft = next(d for d in self.drafts if d["id"] == draft_id)
        draft["status"] = "discarded"
        return {"draft": draft}


def _run_skill(text: str, *, calendar_service=None, email_service=None, get_provider=None):
    return try_skill(
        text,
        role="standard_user",
        token=None,
        granted_permissions=["calendar.read", "calendar.write", "email.read", "email.write"],
        emergency_stop_enabled=lambda: False,
        permission_check=lambda *_a, **_k: True,
        run_cmd=lambda *_a, **_k: "active",
        disk_usage=lambda *_a: Mock(total=100, used=40, free=60),
        format_bytes=lambda v: f"{v}B",
        parse_meminfo=lambda: {"MemTotal": 8_000_000_000, "MemAvailable": 4_000_000_000},
        parse_ping=lambda _o: {"packet_loss": "0%"},
        tail_lines=lambda t, max_lines=6: t,
        ensure_service_allowed=lambda _s: None,
        proxmox_vm_status=lambda *_a: {"data": {"status": "running"}},
        proxmox_lxc_status=lambda *_a: {"data": {"status": "running"}},
        proxmox_vm_action=lambda *_a: {"data": "UPID:task-1"},
        proxmox_lxc_action=lambda *_a: {"data": "UPID:task-2"},
        user_id="u1",
        calendar_service=calendar_service,
        email_service=email_service,
        get_provider=get_provider,
    )


def test_calendar_today_no_events():
    cal = FakeCalendarService()
    result = _run_skill("calendar today", calendar_service=cal)
    assert result["data"]["route"] == "calendar_agenda"
    assert result["data"]["events"] == []


def test_calendar_this_week_with_events():
    cal = FakeCalendarService()
    import time
    now = int(time.time())
    cal.events.append({"id": "cal-1", "title": "Kickoff", "start": now, "end": now + 3600})
    result = _run_skill("what's on my calendar this week", calendar_service=cal)
    assert result["data"]["route"] == "calendar_agenda"
    assert len(result["data"]["events"]) == 1


def test_block_hours_creates_event():
    cal = FakeCalendarService()
    result = _run_skill("block 2 hours thursday afternoon for API design work", calendar_service=cal)
    assert result["data"]["route"] == "calendar_event_created"
    assert result["data"]["event"]["title"] == "API design work"
    assert len(cal.events) == 1


def test_block_hours_reports_conflict_without_double_booking():
    cal = FakeCalendarService()
    from datetime import datetime, timedelta
    # "block ... today" with no daypart defaults to 09:00-10:00 local time in
    # _handle_calendar_block. Span the whole local day (not just "now onward")
    # so the conflict is deterministic regardless of the wall-clock time the
    # test happens to run at — a "now to now+999999s" window used to miss the
    # 09:00 slot whenever the suite ran after ~10am local time.
    day_start = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    cal.events.append({"id": "cal-1", "title": "Existing", "start": int(day_start.timestamp()), "end": int(day_end.timestamp())})
    result = _run_skill("block 1 hour today for New thing", calendar_service=cal)
    assert result["data"]["route"] == "calendar_conflict"
    assert len(cal.events) == 1  # not double-booked


def test_block_hours_not_configured():
    cal = FakeCalendarService()
    cal.configured = False
    result = _run_skill("block 1 hour tomorrow for Standup", calendar_service=cal)
    assert result["data"]["error"] == "not_configured"


def test_calendar_service_absent_falls_through():
    assert _run_skill("calendar today", calendar_service=None) is None


def test_check_email_unread():
    email = FakeEmailService()
    email.messages = [{"id": "m1", "sender": "Alice <a@x.com>", "subject": "Hi", "read": False}]
    result = _run_skill("check email", email_service=email)
    assert result["data"]["route"] == "email_check"
    assert len(result["data"]["unread"]) == 1


def test_check_email_not_configured():
    email = FakeEmailService()
    email.configured = False
    result = _run_skill("check my email", email_service=email)
    assert result["data"]["error"] == "not_configured"


def test_reply_to_creates_draft_without_llm():
    email = FakeEmailService()
    email.messages = [{"id": "m1", "sender": "Alice <a@x.com>", "subject": "Project update", "read": True, "body": "Here's the update."}]
    result = _run_skill("reply to Alice and tell them thanks, will review today", email_service=email)
    assert result["data"]["route"] == "email_draft_created"
    assert len(email.drafts) == 1
    assert email.drafts[0]["to"] == "a@x.com"
    assert "thanks, will review today" in email.drafts[0]["body"]


def test_reply_to_message_not_found():
    email = FakeEmailService()
    result = _run_skill("reply to Bob and tell them see you soon", email_service=email)
    assert result["data"]["error"] == "message_not_found"


def test_send_it_sends_pending_draft():
    email = FakeEmailService()
    email.drafts.append({"id": "draft-1", "to": "x@y.com", "subject": "Hi", "body": "Body", "status": "pending_approval"})
    result = _run_skill("send it", email_service=email)
    assert result["data"]["route"] == "email_draft_sent"
    assert email.drafts[0]["status"] == "sent"


def test_send_it_no_pending_draft():
    email = FakeEmailService()
    result = _run_skill("send it", email_service=email)
    assert result["data"]["error"] == "no_pending_draft"


def test_discard_draft():
    email = FakeEmailService()
    email.drafts.append({"id": "draft-1", "to": "x@y.com", "subject": "Hi", "body": "Body", "status": "pending_approval"})
    result = _run_skill("discard draft", email_service=email)
    assert result["data"]["route"] == "email_draft_discarded"
    assert email.drafts[0]["status"] == "discarded"
