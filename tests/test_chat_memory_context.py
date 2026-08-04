from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.llm_utils import trim_to_budget
from jarvis.providers.base import ChatResult


class _FakePlainProvider:
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
    "JARVIS_MEMORY_PATH", "JARVIS_RAG_CACHE_PATH",
]


class ChatMemoryContextTests(unittest.TestCase):
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
        fake = _FakePlainProvider(responses)
        return patch("jarvis.providers.get_provider_instance", return_value=fake), fake

    def test_saved_memory_note_appears_in_system_prompt(self):
        session_token = self._create_user_with_permissions("memctxuser", ["assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}
        user_id = self.client.get("/auth/me", headers=headers).json()["user"]["id"]

        jarvisappv4.memory_store.add_note(user_id, "prefers dry, concise answers")

        responses = [ChatResult(text="Understood, sir.", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai")]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post("/chat", headers=headers, json={"text": "Tell me something interesting about space"})

        self.assertEqual(200, res.status_code)
        self.assertEqual(1, len(fake.calls))
        self.assertIn("prefers dry, concise answers", fake.calls[0]["system_prompt"])

    def test_no_saved_notes_omits_notes_section(self):
        session_token = self._create_user_with_permissions("nonotesuser", ["assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}

        responses = [ChatResult(text="Understood, sir.", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai")]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post("/chat", headers=headers, json={"text": "Tell me something interesting about space"})

        self.assertEqual(200, res.status_code)
        self.assertNotIn("personal notes", fake.calls[0]["system_prompt"].lower())

    def test_notes_scoped_per_user(self):
        token_a = self._create_user_with_permissions("memuser_a", ["assistant.chat"])
        token_b = self._create_user_with_permissions("memuser_b", ["assistant.chat"])
        user_a_id = self.client.get("/auth/me", headers={"X-Jarvis-Session": token_a}).json()["user"]["id"]
        jarvisappv4.memory_store.add_note(user_a_id, "owns a vintage synthesizer collection")

        responses = [ChatResult(text="Understood, sir.", input_tokens=10, output_tokens=5, model="gpt-4o-mini", provider="openai")]
        patcher, fake = self._patched_provider(responses)
        with patcher:
            res = self.client.post("/chat", headers={"X-Jarvis-Session": token_b}, json={"text": "Tell me something interesting about space"})

        self.assertEqual(200, res.status_code)
        self.assertNotIn("vintage synthesizer", fake.calls[0]["system_prompt"])

    def test_long_history_is_trimmed_to_budget(self):
        session_token = self._create_user_with_permissions("trimuser", ["assistant.chat"])
        headers = {"X-Jarvis-Session": session_token}

        long_reply = "y" * 2000
        responses = [
            ChatResult(text=long_reply, input_tokens=10, output_tokens=500, model="gpt-4o-mini", provider="openai")
            for _ in range(16)
        ]
        patcher, fake = self._patched_provider(responses)
        session_id = None
        with patcher:
            for i in range(16):
                payload = {"text": f"tell me something long, turn {i}"}
                if session_id:
                    payload["session_id"] = session_id
                res = self.client.post("/chat", headers=headers, json=payload)
                self.assertEqual(200, res.status_code)
                session_id = res.json()["session_id"]

        last_messages = fake.calls[-1]["messages"]
        total_token_units = sum(len(m.get("content") or "") for m in last_messages) // 4
        self.assertLessEqual(total_token_units, 4000)
        self.assertLess(len(last_messages), 20)


class TrimToBudgetUnitTests(unittest.TestCase):
    def test_drops_oldest_until_under_budget(self):
        messages = [{"role": "user" if i % 2 == 0 else "assistant", "content": "z" * 400} for i in range(20)]
        trimmed = trim_to_budget(messages, budget=1000)
        total = sum(len(m["content"]) for m in trimmed) // 4
        self.assertLessEqual(total, 1000)
        self.assertLess(len(trimmed), 20)

    def test_keeps_at_least_two_messages(self):
        messages = [{"role": "user", "content": "z" * 100000}, {"role": "assistant", "content": "z" * 100000}]
        trimmed = trim_to_budget(messages, budget=10)
        self.assertEqual(2, len(trimmed))


if __name__ == "__main__":
    unittest.main()
