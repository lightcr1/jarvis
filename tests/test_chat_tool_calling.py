from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.providers.base import ChatResult, ToolCall


class _FakeToolProvider:
    name = "openai"
    supports_streaming = True

    def __init__(self, responses: list[ChatResult]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0)

    def estimate_cost(self, **kwargs) -> float:
        return 0.0

    def validate_api_key(self, api_key: str):
        return True, "ok"


_ENV_PATHS = [
    "JARVIS_USER_STORE_PATH", "JARVIS_MEMBERSHIP_STORE_PATH", "JARVIS_PERMISSION_STORE_PATH",
    "JARVIS_ADMIN_PASSWORD_STORE_PATH", "JARVIS_USER_PREFERENCES_PATH", "JARVIS_FILES_STORE_PATH",
    "JARVIS_USER_FILES_PATH", "JARVIS_USER_LIMITS_STORE_PATH", "JARVIS_ADMIN_SETTINGS_PATH",
    "JARVIS_MEMORY_PATH", "JARVIS_RAG_CACHE_PATH", "JARVIS_TASKS_STORE_PATH",
    "JARVIS_AGENT_GRANTS_PATH",
]


class ChatToolCallingTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        for name in _ENV_PATHS:
            os.environ[name] = os.path.join(base, name.lower() + ".json")
        os.environ["OPENAI_API_KEY"] = "test-dummy-key"
        os.environ.pop("OPENROUTER_API_KEY", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.user_limits_store = jarvisappv4.UserLimitsStore()
        jarvisappv4.admin_settings_store = jarvisappv4.AdminSettingsStore()
        jarvisappv4.file_store = jarvisappv4.FileStore()
        jarvisappv4.memory_store = jarvisappv4.MemoryStore()
        jarvisappv4.rag_store = jarvisappv4.RagStore()
        jarvisappv4.agent_grant_store = jarvisappv4.AgentGrantStore()
        jarvisappv4.file_service = jarvisappv4.FileService(
            store=jarvisappv4.file_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            user_limits_store=jarvisappv4.user_limits_store,
            admin_settings_store=jarvisappv4.admin_settings_store,
            audit_log=jarvisappv4.audit_log,
        )
        jarvisappv4.task_store = jarvisappv4.TaskStore()
        jarvisappv4.task_service = jarvisappv4.TaskService(
            store=jarvisappv4.task_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            share_store=jarvisappv4.task_share_store,
            group_store=jarvisappv4.group_store,
            audit_log=jarvisappv4.audit_log,
        )
        jarvisappv4._identity_tokens.clear()
        jarvisappv4._tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        for name in _ENV_PATHS:
            os.environ.pop(name, None)
        os.environ.pop("OPENAI_API_KEY", None)
        self.tmpdir.cleanup()

    def _create_user_with_permissions(self, username: str, permissions: list[str]) -> str:
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        headers = {"Authorization": f"Bearer {admin['token']}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin["user_id"]}
        created = self.client.post("/admin/users", headers=headers, json={
            "username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass",
        })
        user_id = created.json()["id"]
        self.client.put(f"/admin/permissions/users/{user_id}", headers=headers, json={"permissions": permissions})
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        return login.json()["session_token"]

    def _patched_provider(self, responses: list[ChatResult]):
        fake = _FakeToolProvider(responses)
        return patch("jarvis.providers.get_provider_instance", return_value=fake), fake

    def test_explicit_owner_chat_idea_is_queued_but_guest_cannot_submit(self):
        jarvisappv4.ensure_default_admin_seeded()
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(200, login.status_code)
        headers = {"X-Jarvis-Session": login.json()["session_token"]}
        response = self.client.post("/chat", headers=headers, json={"text": "Business-Idee: Lokale Marktanalyse"})
        self.assertEqual(200, response.status_code)
        self.assertEqual(1, len(jarvisappv4.agent_grant_store.list_ideas()))
        self.assertIn("Idee notiert", response.json()["reply"])
        guest = self.client.post("/chat", json={"text": "Business-Idee: Gastidee"})
        self.assertEqual(200, guest.status_code)
        self.assertEqual(1, len(jarvisappv4.agent_grant_store.list_ideas()))
        streamed = self.client.post("/chat/stream", headers=headers, json={"text": "Projektidee: Neues Repo prüfen"})
        self.assertEqual(200, streamed.status_code)
        self.assertIn("Idee notiert", streamed.text)
        self.assertEqual(2, len(jarvisappv4.agent_grant_store.list_ideas()))

    def test_list_folder_tool_returns_real_files_not_hallucinated(self):
        session_token = self._create_user_with_permissions("filesuser", ["files.read", "files.write", "assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}
        me = self.client.get("/auth/me", headers=headers).json()
        user_id = me["user"]["id"]

        folder = self.client.post("/files/folders", headers=headers, json={"name": "Reports"}).json()["folder"]
        self.client.put(f"/files/folders/{folder['id']}/jarvis-access", headers=headers, json={"granted": True})
        self.client.post(
            "/files/upload", headers=headers,
            files={"file": ("q1.txt", b"quarterly numbers", "text/plain")},
            data={"folder_id": folder["id"]},
        )

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="list_folder", arguments={"folder_name": "Reports"})]),
            ChatResult(text="Your Reports folder has q1.txt in it, sir.", input_tokens=15, output_tokens=8, model="gpt-4o-mini", provider="openai"),
        ]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post(
                "/chat", headers=headers,
                json={"text": "Could you peek inside my Reports folder and let me know what's there"},
            )

        self.assertEqual(200, res.status_code)
        body = res.json()
        self.assertIn("q1.txt", body["reply"])
        self.assertNotIn("readme.txt", body["reply"])
        self.assertEqual(2, len(fake.calls))

    def test_list_folder_tool_denies_ungranted_folder(self):
        session_token = self._create_user_with_permissions("filesuser2", ["files.read", "assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}
        self.client.post("/files/folders", headers=headers, json={"name": "Private"})

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="list_folder", arguments={"folder_name": "Private"})]),
            ChatResult(text="I don't have access to that folder, sir.", input_tokens=15, output_tokens=8, model="gpt-4o-mini", provider="openai"),
        ]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post(
                "/chat", headers=headers,
                json={"text": "Could you peek inside my Private folder and let me know what's there"},
            )

        self.assertEqual(200, res.status_code)
        self.assertEqual(2, len(fake.calls))
        first_call_tools = fake.calls[0].get("tools") or []
        self.assertTrue(any(t.get("function", {}).get("name") == "list_folder" for t in first_call_tools))

    def test_save_memory_note_tool_persists_note(self):
        session_token = self._create_user_with_permissions("memuser", ["assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}
        user_id = self.client.get("/auth/me", headers=headers).json()["user"]["id"]

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="save_memory_note", arguments={"text": "prefers working late at night"})]),
            ChatResult(text='Noted, sir: "prefers working late at night"', input_tokens=15, output_tokens=8, model="gpt-4o-mini", provider="openai"),
        ]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post(
                "/chat", headers=headers,
                json={"text": "Just so you know, I get most of my best work done late at night"},
            )

        self.assertEqual(200, res.status_code)
        notes = jarvisappv4.memory_store.get_notes(user_id)
        self.assertEqual(1, len(notes))
        self.assertEqual("prefers working late at night", notes[0]["text"])

    def test_chat_updates_user_last_seen(self):
        # Powers the alert engine's presence_idle_minutes signal source — a chat
        # message is the simplest available proxy for "the user is around."
        session_token = self._create_user_with_permissions("presenceuser", ["assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}
        user_id = self.client.get("/auth/me", headers=headers).json()["user"]["id"]
        self.assertIsNone(jarvisappv4.user_store.get_user(user_id).get("last_seen_at"))

        responses = [ChatResult(text="Hi.", input_tokens=5, output_tokens=2, model="gpt-4o-mini", provider="openai")]
        patcher, _fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post("/chat", headers=headers, json={"text": "hello there"})

        self.assertEqual(200, res.status_code)
        self.assertIsNotNone(jarvisappv4.user_store.get_user(user_id).get("last_seen_at"))

    def test_write_tool_requires_confirmation_then_executes(self):
        session_token = self._create_user_with_permissions("restartuser", ["assistant.chat", "actions.write.execute"])
        headers = {"X-Jarvis-Session": session_token}

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="restart_service", arguments={"service": "nginx"})]),
        ]
        patcher, fake = self._patched_provider(responses)
        fake_run_cmd_calls: list = []

        def fake_run_cmd(cmd, timeout=8):
            fake_run_cmd_calls.append(cmd)
            return "active"

        with patcher, patch("jarvisappv4.run_cmd", fake_run_cmd):
            res1 = self.client.post("/chat", headers=headers, json={"text": "nginx seems to be acting up, can you sort it out for me"})
            self.assertEqual(200, res1.status_code)
            body1 = res1.json()
            self.assertEqual("tool_confirmation_required", body1["data"]["route"])
            self.assertEqual(1, len(fake.calls))
            self.assertEqual(0, len(fake_run_cmd_calls))

            res2 = self.client.post("/chat", headers=headers, json={"text": "yes", "session_id": body1["session_id"]})
            self.assertEqual(200, res2.status_code)
            body2 = res2.json()
            self.assertEqual("service_restarted", body2["data"]["route"])
            self.assertEqual(1, len(fake.calls))
            self.assertTrue(fake_run_cmd_calls)

    def test_write_tool_confirmation_ignored_by_unrelated_reply(self):
        session_token = self._create_user_with_permissions("restartuser2", ["assistant.chat", "actions.write.execute"])
        headers = {"X-Jarvis-Session": session_token}

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="restart_service", arguments={"service": "nginx"})]),
            ChatResult(text="Sure, here's a fact about space.", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai"),
        ]
        patcher, fake = self._patched_provider(responses)

        with patcher, patch("jarvisappv4.run_cmd", lambda cmd, timeout=8: "active"):
            res1 = self.client.post("/chat", headers=headers, json={"text": "nginx seems to be acting up, can you sort it out for me"})
            body1 = res1.json()
            self.assertEqual("tool_confirmation_required", body1["data"]["route"])

            res2 = self.client.post(
                "/chat", headers=headers,
                json={"text": "actually, tell me something about space instead", "session_id": body1["session_id"]},
            )
            self.assertEqual(200, res2.status_code)
            self.assertEqual(2, len(fake.calls))
            self.assertNotEqual("service_restarted", res2.json()["data"].get("route"))

    def test_create_task_tool_requires_confirmation_then_executes(self):
        session_token = self._create_user_with_permissions("taskuser", ["assistant.chat", "tasks.write", "tasks.read"])
        headers = {"X-Jarvis-Session": session_token}
        user_id = self.client.get("/auth/me", headers=headers).json()["user"]["id"]

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="create_task", arguments={"title": "Water the plants"})]),
        ]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res1 = self.client.post("/chat", headers=headers, json={"text": "add water the plants to my tasks"})
            self.assertEqual(200, res1.status_code)
            body1 = res1.json()
            self.assertEqual("tool_confirmation_required", body1["data"]["route"])
            self.assertEqual(0, len(jarvisappv4.task_service.list_tasks(user_id=user_id, role="standard_user")["tasks"]))

            res2 = self.client.post("/chat", headers=headers, json={"text": "yes", "session_id": body1["session_id"]})
            self.assertEqual(200, res2.status_code)
            body2 = res2.json()
            self.assertEqual("task_created", body2["data"]["route"])
            tasks = jarvisappv4.task_service.list_tasks(user_id=user_id, role="standard_user")["tasks"]
            self.assertEqual(1, len(tasks))
            self.assertEqual("Water the plants", tasks[0]["title"])

    def test_proxmox_status_tool_denied_for_user_without_permission(self):
        session_token = self._create_user_with_permissions("noproxmox", ["assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}

        responses = [
            ChatResult(text="", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai",
                       tool_calls=[ToolCall(id="call-1", name="proxmox_status", arguments={})]),
            ChatResult(text="I couldn't check that for you.", input_tokens=15, output_tokens=8, model="gpt-4o-mini", provider="openai"),
        ]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post(
                "/chat", headers=headers,
                json={"text": "Give me a quick rundown of how the Proxmox cluster is doing right now please"},
            )

        self.assertEqual(200, res.status_code)
        first_call_tools = fake.calls[0].get("tools") or []
        self.assertFalse(any(t.get("function", {}).get("name") == "proxmox_status" for t in first_call_tools))


if __name__ == "__main__":
    unittest.main()
