from __future__ import annotations

import asyncio
import os
import tempfile
import unittest

from fastapi import HTTPException

from jarvis.admin_settings_store import AdminSettingsStore
from jarvis.authz import resolve_effective_permissions
from jarvis.files.service import FileService
from jarvis.files.store import FileStore
from jarvis.home_assistant.client import HomeAssistantClient
from jarvis.home_assistant.service import HomeAssistantService
from jarvis.home_assistant.store import HomeAssistantStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.memory_store import MemoryStore
from jarvis.permission_store import PermissionStore
from jarvis.tool_registry import ToolExecutionContext
from jarvis.tool_registry_tools import build_pilot_tool_registry
from jarvis.user_limits_store import UserLimitsStore
from jarvis.user_store import UserStore


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
        self.registry = build_pilot_tool_registry()

    def tearDown(self):
        for key in (
            "JARVIS_USER_STORE_PATH", "JARVIS_MEMBERSHIP_STORE_PATH", "JARVIS_PERMISSION_STORE_PATH",
            "JARVIS_FILES_STORE_PATH", "JARVIS_USER_FILES_PATH", "JARVIS_USER_LIMITS_STORE_PATH",
            "JARVIS_ADMIN_SETTINGS_PATH", "JARVIS_MEMORY_PATH", "JARVIS_HOME_ASSISTANT_STORE_PATH",
        ):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

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

    def test_all_pilot_tools_registered(self):
        self.assertEqual(
            {"list_folder", "read_file", "save_memory_note", "proxmox_status", "restart_service", "list_devices", "control_device"},
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


if __name__ == "__main__":
    unittest.main()
