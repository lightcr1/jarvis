import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4


class ChatFallbackTests(unittest.TestCase):
    def setUp(self):
        jarvisappv4._tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def test_revoked_token_cannot_authorize_sensitive_chat_skill(self):
        with patch.dict(os.environ, {"JARVIS_PASSPHRASE": "test-pass"}, clear=False):
            unlock = self.client.post("/unlock", json={"passphrase": "test-pass"})
        self.assertEqual(unlock.status_code, 200)
        token = unlock.json()["token"]

        revoke = self.client.post("/unlock/revoke", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(revoke.status_code, 200)

        # X-Jarvis-Role header is ignored without an identity session — role defaults to guest_restricted
        res = self.client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}", "X-Jarvis-Role": "admin"},
            json={"text": "service restart local nginx"},
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        # guest_restricted cannot execute write actions regardless of headers
        self.assertEqual(body.get("reply"), "Permission denied.")

    def test_cloud_error_returns_context_reply(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False), patch("jarvisappv4.get_provider", return_value="gemini"), patch(
            "jarvisappv4.get_gemini", side_effect=RuntimeError("no api")
        ):
            res = self.client.post("/chat", json={"text": "warum geht web gui nicht"})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("Quick check path", body["reply"])
        self.assertEqual(body["data"]["route"], "offline_assistant")

    def test_known_skill_bypasses_cloud(self):
        with patch("jarvisappv4.get_provider", return_value="gemini"), patch(
            "jarvisappv4.get_gemini", side_effect=RuntimeError("no api")
        ):
            res = self.client.post("/chat", json={"text": "health"})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("healthy", body["reply"].lower())




    def test_voice_mode_without_env_is_not_blocked_by_wakeword(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("JARVIS_WAKEWORD_ENABLED", None)
            res = self.client.post("/chat", json={"text": "health", "source": "voice"})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("healthy", body["reply"].lower())

    def test_voice_mode_requires_wakeword_when_enabled(self):
        with patch.dict(os.environ, {"JARVIS_WAKEWORD_ENABLED": "1", "JARVIS_WAKEWORD_PHRASE": "hey jarvis"}, clear=False):
            res = self.client.post("/chat", json={"text": "status jarvis", "source": "voice"})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("Awaiting wake word", body["reply"])

    def test_voice_mode_accepts_command_with_wakeword(self):
        with patch.dict(os.environ, {"JARVIS_WAKEWORD_ENABLED": "1", "JARVIS_WAKEWORD_PHRASE": "hey jarvis"}, clear=False):
            res = self.client.post("/chat", json={"text": "hey jarvis status jarvis", "source": "voice"})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertIn("jarvis", body["reply"].lower())

if __name__ == "__main__":
    unittest.main()
