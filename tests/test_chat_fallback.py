import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4


class ChatFallbackTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(jarvisappv4.app)

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


if __name__ == "__main__":
    unittest.main()
