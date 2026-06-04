import io
import json
import sys
import types
import unittest
from unittest.mock import patch

if "fastapi" not in sys.modules:
    fastapi = types.ModuleType("fastapi")
    class HTTPException(Exception):
        def __init__(self, status_code, detail):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail
    fastapi.HTTPException = HTTPException
    sys.modules["fastapi"] = fastapi

if "google" not in sys.modules:
    google = types.ModuleType("google")
    google.genai = types.SimpleNamespace(Client=object)
    sys.modules["google"] = google

if "openai" not in sys.modules:
    openai = types.ModuleType("openai")
    openai.OpenAI = object
    sys.modules["openai"] = openai

if "faster_whisper" not in sys.modules:
    faster_whisper = types.ModuleType("faster_whisper")
    faster_whisper.WhisperModel = object
    sys.modules["faster_whisper"] = faster_whisper

from jarvis.ai_clients import build_system_prompt, local_ai_chat_reply, local_ai_stub_reply


class _FakeHttpResponse:
    def __init__(self, payload: dict):
        self._payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class BuildSystemPromptTests(unittest.TestCase):
    def test_base_prompt_contains_jarvis(self):
        prompt = build_system_prompt()
        self.assertIn("J.A.R.V.I.S.", prompt)

    def test_user_name_included(self):
        prompt = build_system_prompt(user_name="Lukas")
        self.assertIn("Lukas", prompt)

    def test_location_injected(self):
        prompt = build_system_prompt(location="Munich")
        self.assertIn("Munich", prompt)
        self.assertIn("PERSONAL CONTEXT", prompt)

    def test_notes_injected(self):
        prompt = build_system_prompt(notes=["buy milk", "call doctor"])
        self.assertIn("buy milk", prompt)
        self.assertIn("call doctor", prompt)
        self.assertIn("PERSONAL CONTEXT", prompt)

    def test_notes_capped_at_ten(self):
        notes = [f"note{i}" for i in range(15)]
        prompt = build_system_prompt(notes=notes)
        self.assertNotIn("note10", prompt)
        self.assertIn("note9", prompt)

    def test_empty_notes_no_context_line(self):
        prompt = build_system_prompt(notes=[])
        self.assertNotIn("PERSONAL CONTEXT", prompt)

    def test_none_location_no_context_line(self):
        prompt = build_system_prompt(location=None)
        self.assertNotIn("PERSONAL CONTEXT", prompt)

    def test_voice_mode_adds_tts_instruction(self):
        prompt = build_system_prompt(voice_mode=True)
        self.assertIn("VOICE MODE", prompt)

    def test_no_voice_mode_no_tts_instruction(self):
        prompt = build_system_prompt(voice_mode=False)
        self.assertNotIn("VOICE MODE", prompt)

    def test_all_params_combined(self):
        prompt = build_system_prompt(user_name="Lukas", location="Berlin", notes=["remember X"], voice_mode=True)
        self.assertIn("Lukas", prompt)
        self.assertIn("Berlin", prompt)
        self.assertIn("remember X", prompt)
        self.assertIn("VOICE MODE", prompt)


class AiClientsTests(unittest.TestCase):
    def test_local_ai_requires_default_model(self):
        with patch.dict("os.environ", {"LOCAL_LLM_ENABLED": "1"}, clear=False):
            with patch("jarvis.ai_clients.os.getenv", side_effect=lambda name, default=None: {
                "LOCAL_LLM_ENABLED": "1",
                "LOCAL_LLM_DEFAULT_MODEL": "",
                "LOCAL_LLM_BASE_URL": "http://127.0.0.1:11434",
            }.get(name, default)):
                reply = local_ai_stub_reply("hello")
        self.assertIn("LOCAL_LLM_DEFAULT_MODEL is not set", reply)

    def test_local_ai_ollama_request_returns_text(self):
        def fake_urlopen(req, timeout=60):
            self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "llama3")
            self.assertEqual(payload["messages"][-1]["content"], "status report")
            return _FakeHttpResponse({"message": {"content": "Understood. All systems nominal."}})

        env = {
            "LOCAL_LLM_DEFAULT_MODEL": "llama3",
            "LOCAL_LLM_BASE_URL": "http://127.0.0.1:11434",
            "LOCAL_LLM_BACKEND": "ollama",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("jarvis.ai_clients.urllib.request.urlopen", side_effect=fake_urlopen):
                reply = local_ai_stub_reply("status report")
        self.assertEqual("Understood. All systems nominal.", reply)

    def test_local_ai_chat_reply_uses_message_history_for_ollama(self):
        def fake_urlopen(req, timeout=60):
            self.assertEqual(req.full_url, "http://127.0.0.1:11434/api/chat")
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["model"], "llama3")
            self.assertEqual(payload["messages"][0]["role"], "system")
            self.assertEqual(payload["messages"][-1]["content"], "latest request")
            return _FakeHttpResponse({"message": {"content": "Consider it done."}})

        env = {
            "LOCAL_LLM_DEFAULT_MODEL": "llama3",
            "LOCAL_LLM_BASE_URL": "http://127.0.0.1:11434",
            "LOCAL_LLM_BACKEND": "ollama",
        }
        with patch.dict("os.environ", env, clear=False):
            with patch("jarvis.ai_clients.urllib.request.urlopen", side_effect=fake_urlopen):
                reply = local_ai_chat_reply(
                    [
                        {"role": "user", "content": "earlier context"},
                        {"role": "assistant", "content": "previous answer"},
                        {"role": "user", "content": "latest request"},
                    ],
                    "Custom system prompt",
                )
        self.assertEqual("Consider it done.", reply)


if __name__ == "__main__":
    unittest.main()
