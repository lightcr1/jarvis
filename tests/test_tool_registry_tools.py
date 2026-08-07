from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import unittest

from fastapi import HTTPException

from jarvis.admin_settings_store import AdminSettingsStore
from jarvis.audit_log_store import AuditLogStore
from jarvis.authz import resolve_effective_permissions
from jarvis.calendar.service import CalendarService
from jarvis.calendar.store import CalendarEventStore
from jarvis.email.service import EmailService
from jarvis.email.store import EmailDraftStore, EmailMessageStore
from jarvis.files.service import FileService
from jarvis.files.store import FileStore
from jarvis.home_assistant.client import HomeAssistantClient
from jarvis.home_assistant.service import HomeAssistantService
from jarvis.home_assistant.store import HomeAssistantStore
from jarvis.integration_credentials import IntegrationCredentialStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.memory_store import MemoryStore
from jarvis.permission_store import PermissionStore
from jarvis.secret_crypto import generate_master_key
from jarvis.tasks.service import TaskService
from jarvis.tasks.store import TaskStore
from jarvis.tool_registry import ToolExecutionContext
from jarvis.tool_registry_tools import build_pilot_tool_registry
from jarvis.user_limits_store import UserLimitsStore
from jarvis.user_store import UserStore


class _FakeCalDavClient:
    def __init__(self):
        self.events: list[dict] = []

    def list_events(self, start, end):
        return list(self.events)

    def put_event(self, event: dict, *, href: str | None = None) -> str | None:
        self.events.append(dict(event))
        return href or f"https://caldav.example/cal/{event['uid']}.ics"

    def delete_event(self, uid: str, *, href: str | None = None) -> bool:
        return True

    def test_connection(self) -> bool:
        return True


class _FakeImapSmtpClient:
    def __init__(self):
        self.inbox = [{"uid": "1", "folder": "INBOX", "subject": "Welcome", "sender": "a@example.com", "date": 1000, "read": False}]
        self.sent_messages: list[dict] = []

    def fetch_recent_messages(self, folder="INBOX", limit=20):
        return [m for m in self.inbox if m["folder"] == folder][:limit]

    def fetch_message_body(self, uid, folder="INBOX"):
        return "body"

    def mark_read(self, uid, folder="INBOX"):
        return True

    def send_message(self, to, subject, body, in_reply_to=None):
        self.sent_messages.append({"to": to, "subject": subject, "body": body})
        return True

    def test_connection(self) -> bool:
        return True


class _BytesReader:
    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        want = size if size and size > 0 else 64
        chunk = self._data[self._pos:self._pos + want]
        self._pos += len(chunk)
        return chunk


def _run(coro):
    return asyncio.run(coro)


class PilotToolsTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_FILES_STORE_PATH"] = os.path.join(base, "files_metadata.json")
        os.environ["JARVIS_USER_FILES_PATH"] = os.path.join(base, "user_files")
        os.environ["JARVIS_USER_LIMITS_STORE_PATH"] = os.path.join(base, "user_limits.json")
        os.environ["JARVIS_ADMIN_SETTINGS_PATH"] = os.path.join(base, "admin_settings.json")
        os.environ["JARVIS_MEMORY_PATH"] = os.path.join(base, "memory.json")
        os.environ["JARVIS_HOME_ASSISTANT_STORE_PATH"] = os.path.join(base, "home_assistant.json")
        os.environ["JARVIS_TASKS_STORE_PATH"] = os.path.join(base, "tasks.json")
        os.environ["JARVIS_CALENDAR_STORE_PATH"] = os.path.join(base, "calendar.json")
        os.environ["JARVIS_EMAIL_STORE_PATH"] = os.path.join(base, "email_messages.json")
        os.environ["JARVIS_EMAIL_DRAFTS_STORE_PATH"] = os.path.join(base, "email_drafts.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")
        os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")

        self.audit_log_store = AuditLogStore()
        self.user_store = UserStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.file_store = FileStore()
        self.user_limits_store = UserLimitsStore()
        self.admin_settings_store = AdminSettingsStore()
        self.file_service = FileService(
            store=self.file_store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            user_limits_store=self.user_limits_store,
            admin_settings_store=self.admin_settings_store,
            audit_log=None,
        )
        self.memory_store = MemoryStore()
        self.ha_store = HomeAssistantStore()
        self.ha_service = HomeAssistantService(
            store=self.ha_store,
            client=HomeAssistantClient(),
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=None,
        )
        self.task_store = TaskStore()
        self.task_service = TaskService(
            store=self.task_store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=None,
        )
        self.calendar_store = CalendarEventStore()
        self.credential_store = IntegrationCredentialStore()
        self.fake_caldav = _FakeCalDavClient()
        self.calendar_service = CalendarService(
            store=self.calendar_store,
            credential_store=self.credential_store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=None,
            client_factory=lambda creds: self.fake_caldav,
        )
        self.email_message_store = EmailMessageStore()
        self.email_draft_store = EmailDraftStore()
        self.fake_imap = _FakeImapSmtpClient()
        self.email_service = EmailService(
            message_store=self.email_message_store,
            draft_store=self.email_draft_store,
            credential_store=self.credential_store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=None,
            client_factory=lambda creds: self.fake_imap,
        )
        self.registry = build_pilot_tool_registry()

    def tearDown(self):
        for key in (
            "JARVIS_USER_STORE_PATH", "JARVIS_MEMBERSHIP_STORE_PATH", "JARVIS_PERMISSION_STORE_PATH",
            "JARVIS_FILES_STORE_PATH", "JARVIS_USER_FILES_PATH", "JARVIS_USER_LIMITS_STORE_PATH",
            "JARVIS_ADMIN_SETTINGS_PATH", "JARVIS_MEMORY_PATH", "JARVIS_HOME_ASSISTANT_STORE_PATH",
            "JARVIS_TASKS_STORE_PATH", "JARVIS_CALENDAR_STORE_PATH", "JARVIS_EMAIL_STORE_PATH",
            "JARVIS_EMAIL_DRAFTS_STORE_PATH", "JARVIS_SECRET_KEY", "JARVIS_INTEGRATION_CREDENTIALS_PATH",
            "JARVIS_AUDIT_LOG_PATH",
        ):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _tasks_user(self, username="taskuser"):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["tasks.read", "tasks.write"])
        return user

    def _calendar_user(self, username="caluser"):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["calendar.read", "calendar.write"])
        self.calendar_service.set_credentials({"url": "https://caldav.example/cal", "username": "u", "password": "p"}, user_id=user["id"], role=user["role"])
        return user

    def _email_user(self, username="emailuser"):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["email.read", "email.write"])
        self.email_service.set_credentials(
            {
                "imap_host": "imap.example.com", "imap_port": "993", "imap_username": "u", "imap_password": "p",
                "smtp_host": "smtp.example.com", "smtp_port": "465", "smtp_username": "u", "smtp_password": "p",
            },
            user_id=user["id"], role=user["role"],
        )
        return user

    def _rw_user(self, username="alice"):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["files.read", "files.write"])
        return user

    def _ha_user(self, username="haowner"):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(
            user["id"],
            ["home_assistant.access", "home_assistant.device_control", "home_assistant.security_device_control"],
        )
        return user

    def _upload(self, *, folder_id, filename, content: bytes, user):
        return _run(
            self.file_service.upload_file(
                folder_id=folder_id, filename=filename, reader=_BytesReader(content),
                content_type="text/plain", user_id=user["id"], role=user["role"],
            )
        )["file"]

    def _ctx(self, user, **deps) -> ToolExecutionContext:
        return ToolExecutionContext(user_id=user["id"], role=user["role"], deps=deps)

    def test_list_folder_returns_real_files_not_hallucinated(self):
        user = self._rw_user()
        folder = self.file_service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        self.file_service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self._upload(folder_id=folder["id"], filename="q1.txt", content=b"quarterly numbers", user=user)

        tool = self.registry.get("list_folder")
        result = tool.handler(self._ctx(user, file_service=self.file_service), {"folder_name": "Reports"})
        self.assertEqual("file_drive_list", result["data"]["route"])
        self.assertIn("q1.txt", result["reply"])

    def test_list_folder_denies_ungranted_folder(self):
        user = self._rw_user()
        self.file_service.create_folder({"name": "Private"}, user_id=user["id"], role=user["role"])

        tool = self.registry.get("list_folder")
        result = tool.handler(self._ctx(user, file_service=self.file_service), {"folder_name": "Private"})
        self.assertEqual("not_granted", result["data"]["error"])

    def test_read_file_returns_content(self):
        user = self._rw_user()
        folder = self.file_service.create_folder({"name": "Reports"}, user_id=user["id"], role=user["role"])["folder"]
        self.file_service.grant_jarvis_folder_access(folder["id"], user_id=user["id"], role=user["role"])
        self._upload(folder_id=folder["id"], filename="notes.txt", content=b"hello from the file drive", user=user)

        tool = self.registry.get("read_file")
        result = tool.handler(self._ctx(user, file_service=self.file_service), {"folder_name": "Reports", "filename": "notes.txt"})
        self.assertEqual("file_drive_read", result["data"]["route"])
        self.assertIn("hello from the file drive", result["reply"])

    def test_save_memory_note_persists(self):
        user = self._rw_user()
        tool = self.registry.get("save_memory_note")
        result = tool.handler(self._ctx(user, memory_store=self.memory_store), {"text": "prefers dark mode"})
        self.assertEqual("memory_note_saved", result["data"]["route"])
        notes = self.memory_store.get_notes(user["id"])
        self.assertEqual(1, len(notes))
        self.assertEqual("prefers dark mode", notes[0]["text"])

    def test_save_memory_note_rejects_empty_text(self):
        user = self._rw_user()
        tool = self.registry.get("save_memory_note")
        result = tool.handler(self._ctx(user, memory_store=self.memory_store), {"text": "   "})
        self.assertEqual("empty_text", result["data"]["error"])
        self.assertEqual([], self.memory_store.get_notes(user["id"]))

    def test_proxmox_status_reports_unconfigured(self):
        user = self._rw_user()
        tool = self.registry.get("proxmox_status")
        result = tool.handler(self._ctx(user, proxmox_health=lambda: {"configured": False, "hosts": [], "summary": {}}), {})
        self.assertFalse(result["data"]["configured"])

    def test_proxmox_status_reports_summary(self):
        user = self._rw_user()
        tool = self.registry.get("proxmox_status")
        health = {"configured": True, "hosts": [], "summary": {"hosts": 1, "nodes": 2, "running": 4, "stopped": 1}}
        result = tool.handler(self._ctx(user, proxmox_health=lambda: health), {})
        self.assertIn("4 running", result["reply"])
        self.assertIn("1 stopped", result["reply"])

    def test_list_tasks_returns_real_tasks(self):
        user = self._tasks_user()
        self.task_service.create_task({"title": "Buy milk"}, user_id=user["id"], role=user["role"])
        tool = self.registry.get("list_tasks")
        result = tool.handler(self._ctx(user, task_service=self.task_service), {})
        self.assertEqual("task_list", result["data"]["route"])
        self.assertEqual(1, len(result["data"]["tasks"]))
        self.assertEqual("Buy milk", result["data"]["tasks"][0]["title"])

    def test_create_task_persists(self):
        user = self._tasks_user()
        tool = self.registry.get("create_task")
        result = tool.handler(self._ctx(user, task_service=self.task_service), {"title": "Call the dentist"})
        self.assertEqual("task_created", result["data"]["route"])
        tasks = self.task_service.list_tasks(user_id=user["id"], role=user["role"])["tasks"]
        self.assertEqual(1, len(tasks))
        self.assertEqual("Call the dentist", tasks[0]["title"])

    def test_create_task_rejects_missing_title(self):
        user = self._tasks_user()
        tool = self.registry.get("create_task")
        result = tool.handler(self._ctx(user, task_service=self.task_service), {})
        self.assertEqual("missing_title", result["data"]["error"])

    def test_complete_task_marks_done(self):
        user = self._tasks_user()
        task = self.task_service.create_task({"title": "Water plants"}, user_id=user["id"], role=user["role"])["task"]
        tool = self.registry.get("complete_task")
        result = tool.handler(self._ctx(user, task_service=self.task_service), {"task_id": task["id"]})
        self.assertEqual("task_completed", result["data"]["route"])
        self.assertEqual("done", result["data"]["task"]["status"])

    def test_list_calendar_events_returns_real_events(self):
        user = self._calendar_user()
        self.calendar_service.create_event({"title": "Standup", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        tool = self.registry.get("list_calendar_events")
        result = tool.handler(self._ctx(user, calendar_service=self.calendar_service), {})
        self.assertEqual("calendar_event_list", result["data"]["route"])
        self.assertEqual(1, len(result["data"]["events"]))

    def test_create_calendar_event_succeeds(self):
        user = self._calendar_user()
        tool = self.registry.get("create_calendar_event")
        result = tool.handler(self._ctx(user, calendar_service=self.calendar_service), {"title": "Dentist", "start": 1000, "end": 2000})
        self.assertEqual("calendar_event_created", result["data"]["route"])
        self.assertIn("Dentist", result["reply"])

    def test_create_calendar_event_reports_conflict(self):
        user = self._calendar_user()
        self.calendar_service.create_event({"title": "Existing", "start": 1000, "end": 5000}, user_id=user["id"], role=user["role"])
        tool = self.registry.get("create_calendar_event")
        result = tool.handler(self._ctx(user, calendar_service=self.calendar_service), {"title": "New thing", "start": 2000, "end": 3000})
        self.assertEqual("calendar_conflict", result["data"]["route"])
        self.assertIn("Existing", result["reply"])

    def test_create_calendar_event_rejects_missing_args(self):
        user = self._calendar_user()
        tool = self.registry.get("create_calendar_event")
        result = tool.handler(self._ctx(user, calendar_service=self.calendar_service), {"title": "No times"})
        self.assertEqual("missing_args", result["data"]["error"])

    def test_list_emails_returns_real_messages(self):
        user = self._email_user()
        self.email_service.sync_inbox(user_id=user["id"], role=user["role"])
        tool = self.registry.get("list_emails")
        result = tool.handler(self._ctx(user, email_service=self.email_service), {})
        self.assertEqual("email_list", result["data"]["route"])
        self.assertEqual(1, len(result["data"]["messages"]))

    def test_create_email_draft_persists(self):
        user = self._email_user()
        tool = self.registry.get("create_email_draft")
        result = tool.handler(self._ctx(user, email_service=self.email_service), {"to": "bob@example.com", "body": "Hi Bob"})
        self.assertEqual("email_draft_created", result["data"]["route"])
        drafts = self.email_service.list_drafts(user_id=user["id"], role=user["role"])["drafts"]
        self.assertEqual(1, len(drafts))

    def test_create_email_draft_rejects_missing_args(self):
        user = self._email_user()
        tool = self.registry.get("create_email_draft")
        result = tool.handler(self._ctx(user, email_service=self.email_service), {"to": "bob@example.com"})
        self.assertEqual("missing_args", result["data"]["error"])

    def test_send_email_draft_sends_without_second_confirmation(self):
        user = self._email_user()
        draft = self.email_service.create_draft({"to": "bob@example.com", "body": "Hi Bob"}, user_id=user["id"], role=user["role"])["draft"]
        tool = self.registry.get("send_email_draft")
        result = tool.handler(self._ctx(user, email_service=self.email_service), {"draft_id": draft["id"]})
        self.assertEqual("email_sent", result["data"]["route"])
        self.assertEqual(1, len(self.fake_imap.sent_messages))

    def test_proxmox_vm_action_executes(self):
        user = self._rw_user()
        tool = self.registry.get("proxmox_vm_action")
        calls = []
        fake_action = lambda host_id, node, vmid, action: calls.append((host_id, node, vmid, action)) or {"data": "UPID:task-1"}
        result = tool.handler(
            self._ctx(user, proxmox_vm_action=fake_action),
            {"host_id": "h1", "node": "pve", "vmid": "100", "action": "restart"},
        )
        self.assertEqual("proxmox_vm_action", result["data"]["route"])
        self.assertEqual([("h1", "pve", "100", "restart")], calls)

    def test_proxmox_vm_action_rejects_invalid_action(self):
        user = self._rw_user()
        tool = self.registry.get("proxmox_vm_action")
        result = tool.handler(self._ctx(user, proxmox_vm_action=lambda *a: {}), {"host_id": "h1", "node": "pve", "vmid": "100", "action": "delete"})
        self.assertEqual("missing_args", result["data"]["error"])

    def test_proxmox_vm_action_reports_host_not_found(self):
        user = self._rw_user()
        tool = self.registry.get("proxmox_vm_action")

        def raise_not_found(*_a):
            raise HTTPException(404, "Proxmox host not found")

        result = tool.handler(
            self._ctx(user, proxmox_vm_action=raise_not_found),
            {"host_id": "missing", "node": "pve", "vmid": "100", "action": "start"},
        )
        self.assertEqual("proxmox_error", result["data"]["error"])

    def test_proxmox_lxc_action_executes(self):
        user = self._rw_user()
        tool = self.registry.get("proxmox_lxc_action")
        calls = []
        fake_action = lambda host_id, node, vmid, action: calls.append((host_id, node, vmid, action)) or {"data": "UPID:task-2"}
        result = tool.handler(
            self._ctx(user, proxmox_lxc_action=fake_action),
            {"host_id": "h1", "node": "pve", "vmid": "200", "action": "stop"},
        )
        self.assertEqual("proxmox_lxc_action", result["data"]["route"])
        self.assertEqual([("h1", "pve", "200", "stop")], calls)

    def test_all_pilot_tools_registered(self):
        self.assertEqual(
            {
                "list_folder", "read_file", "save_memory_note", "proxmox_status", "restart_service", "list_devices", "control_device",
                "list_tasks", "create_task", "complete_task", "list_calendar_events", "create_calendar_event",
                "list_emails", "create_email_draft", "send_email_draft", "proxmox_vm_action", "proxmox_lxc_action",
                "get_login_history",
            },
            {t.name for t in self.registry.all()},
        )

    def test_restart_service_executes_allowed_service(self):
        user = self._rw_user()
        tool = self.registry.get("restart_service")
        calls = []

        def fake_run_cmd(cmd, timeout=8):
            calls.append(cmd)
            return "active"

        result = tool.handler(
            self._ctx(user, run_cmd=fake_run_cmd, ensure_service_allowed=lambda s: None),
            {"service": "nginx"},
        )
        self.assertEqual("service_restarted", result["data"]["route"])
        self.assertTrue(result["data"]["healthy"])
        self.assertEqual(2, len(calls))

    def test_restart_service_rejects_disallowed_service(self):
        user = self._rw_user()
        tool = self.registry.get("restart_service")

        def deny(service):
            raise HTTPException(403, f"Service not allowed: {service}")

        result = tool.handler(
            self._ctx(user, run_cmd=lambda *a, **kw: "", ensure_service_allowed=deny),
            {"service": "evil"},
        )
        self.assertEqual("service_not_allowed", result["data"]["error"])

    def test_restart_service_requires_service_name(self):
        user = self._rw_user()
        tool = self.registry.get("restart_service")
        result = tool.handler(
            self._ctx(user, run_cmd=lambda *a, **kw: "", ensure_service_allowed=lambda s: None), {},
        )
        self.assertEqual("missing_service", result["data"]["error"])

    def test_list_devices_returns_managed_entities(self):
        user = self._ha_user()
        self.ha_store.add_managed_entity({"entity_id": "light.kitchen", "label": "Kitchen Light", "kind": "light", "area": "Kitchen"})
        tool = self.registry.get("list_devices")
        result = tool.handler(self._ctx(user, home_assistant_service=self.ha_service), {})
        self.assertEqual("device_list", result["data"]["route"])
        self.assertEqual(1, len(result["data"]["entities"]))

    def test_list_devices_reports_not_configured_without_service(self):
        user = self._ha_user()
        tool = self.registry.get("list_devices")
        result = tool.handler(self._ctx(user, home_assistant_service=None), {})
        self.assertEqual("not_configured", result["data"]["error"])

    def test_control_device_executes_basic_action(self):
        user = self._ha_user()
        self.ha_store.add_managed_entity({"entity_id": "light.kitchen", "label": "Kitchen Light", "kind": "light", "area": "Kitchen"})
        tool = self.registry.get("control_device")
        result = tool.handler(
            self._ctx(user, home_assistant_service=self.ha_service),
            {"entity_id": "light.kitchen", "action": "turn_on"},
        )
        self.assertEqual("device_action", result["data"]["route"])
        self.assertTrue(result["data"]["executed"])
        self.assertIn("Done", result["reply"])

    def test_control_device_queues_security_sensitive_action(self):
        user = self._ha_user()
        self.ha_store.add_managed_entity({"entity_id": "lock.front_door", "label": "Front Door", "kind": "lock", "area": "Entry"})
        tool = self.registry.get("control_device")
        result = tool.handler(
            self._ctx(user, home_assistant_service=self.ha_service),
            {"entity_id": "lock.front_door", "action": "unlock"},
        )
        self.assertFalse(result["data"]["executed"])
        self.assertIn("queued", result["reply"])

    def test_control_device_rejects_missing_args(self):
        user = self._ha_user()
        tool = self.registry.get("control_device")
        result = tool.handler(self._ctx(user, home_assistant_service=self.ha_service), {"entity_id": "light.kitchen"})
        self.assertEqual("missing_args", result["data"]["error"])

    def test_control_device_reports_not_configured_without_service(self):
        user = self._ha_user()
        tool = self.registry.get("control_device")
        result = tool.handler(self._ctx(user, home_assistant_service=None), {"entity_id": "light.kitchen", "action": "turn_on"})
        self.assertEqual("not_configured", result["data"]["error"])

    def test_get_login_history_is_gated_by_audit_read(self):
        tool = self.registry.get("get_login_history")
        self.assertEqual("audit.read", tool.required_permission)

    def test_get_login_history_reports_no_activity(self):
        user = self._rw_user()
        tool = self.registry.get("get_login_history")
        result = tool.handler(self._ctx(user, audit_log=self.audit_log_store), {})
        self.assertEqual([], result["data"]["events"])
        self.assertIn("No login activity", result["reply"])

    def test_get_login_history_reports_successes_and_failures_no_anomalies(self):
        user = self._rw_user()
        self.audit_log_store.write("user_login_succeeded", {"user_id": "u1", "username": "alice", "role": "standard_user"})
        tool = self.registry.get("get_login_history")
        result = tool.handler(self._ctx(user, audit_log=self.audit_log_store), {})
        self.assertEqual(1, len(result["data"]["events"]))
        self.assertIn("alice", result["reply"])
        self.assertIn("No anomalies detected", result["reply"])

    def test_get_login_history_flags_failed_attempts(self):
        user = self._rw_user()
        self.audit_log_store.write("user_login_failed", {"username": "mallory", "reason": "invalid_credentials"})
        self.audit_log_store.write("user_login_succeeded", {"user_id": "u1", "username": "alice", "role": "standard_user"})
        tool = self.registry.get("get_login_history")
        result = tool.handler(self._ctx(user, audit_log=self.audit_log_store), {})
        self.assertEqual(2, len(result["data"]["events"]))
        self.assertIn("mallory", result["reply"])
        self.assertIn("1 failed attempt", result["reply"])

    def test_get_login_history_respects_hours_window(self):
        user = self._rw_user()
        old_ts = int(time.time()) - 100 * 3600
        self.audit_log_store.write("user_login_succeeded", {"user_id": "u1", "username": "old_login", "role": "standard_user"})
        # Force the just-written event outside the default 24h window by rewriting its timestamp directly.
        content = self.audit_log_store.path.read_text(encoding="utf-8")
        entry = json.loads(content.strip())
        entry["ts"] = old_ts
        self.audit_log_store.path.write_text(json.dumps(entry) + "\n", encoding="utf-8")

        tool = self.registry.get("get_login_history")
        result = tool.handler(self._ctx(user, audit_log=self.audit_log_store), {"hours": 24})
        self.assertEqual([], result["data"]["events"])

        result_wide = tool.handler(self._ctx(user, audit_log=self.audit_log_store), {"hours": 200})
        self.assertEqual(1, len(result_wide["data"]["events"]))


if __name__ == "__main__":
    unittest.main()
