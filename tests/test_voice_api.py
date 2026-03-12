import io
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import jarvisappv4


class VoiceApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(self.tmpdir.name, "chat_history.json")
        os.environ["JARVIS_RAG_CACHE_PATH"] = os.path.join(self.tmpdir.name, "rag_cache.json")
        os.environ["JARVIS_MEMORY_PATH"] = os.path.join(self.tmpdir.name, "memory.json")
        jarvisappv4.chat_history = jarvisappv4.ChatHistoryStore()
        jarvisappv4.rag_store = jarvisappv4.RagStore()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in ["JARVIS_CHAT_HISTORY_PATH", "JARVIS_RAG_CACHE_PATH", "JARVIS_MEMORY_PATH", "STT_PROVIDER"]:
            os.environ.pop(key, None)

    def test_stt_local_returns_transcript(self):
        os.environ["STT_PROVIDER"] = "local"
        with patch("jarvisappv4.subprocess.run"), patch("jarvisappv4.transcribe_local", return_value="status jarvis"):
            res = self.client.post("/stt", files={"file": ("sample.wav", b"audio-bytes", "audio/wav")})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["text"], "status jarvis")

    def test_stt_gemini_rate_limit_returns_retry_response(self):
        os.environ["STT_PROVIDER"] = "gemini"
        with patch("jarvisappv4.subprocess.run"), patch(
            "jarvisappv4.transcribe_gemini", side_effect=RuntimeError("429 RESOURCE_EXHAUSTED")
        ):
            res = self.client.post("/stt", files={"file": ("sample.wav", b"audio-bytes", "audio/wav")})
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.headers.get("Retry-After"), "40")

    def test_stt_empty_audio_rejected(self):
        os.environ["STT_PROVIDER"] = "local"
        res = self.client.post("/stt", files={"file": ("sample.wav", b"", "audio/wav")})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Empty audio", res.text)

    def test_tts_returns_wav_payload(self):
        with patch("jarvisappv4.synthesize_tts", return_value=b"RIFFmockwav"):
            res = self.client.post("/tts", json={"text": "status jarvis"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("content-type"), "audio/wav")
        self.assertEqual(res.content, b"RIFFmockwav")

    def test_tts_requires_text(self):
        res = self.client.post("/tts", json={"text": "   "})
        self.assertEqual(res.status_code, 400)
        self.assertIn("Missing text", res.text)


if __name__ == "__main__":
    unittest.main()
