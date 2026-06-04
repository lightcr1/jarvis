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
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(self.tmpdir.name, "users.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(self.tmpdir.name, "prefs.json")
        jarvisappv4.chat_history = jarvisappv4.ChatHistoryStore()
        jarvisappv4.rag_store = jarvisappv4.RagStore()
        from jarvis.user_store import UserStore
        from jarvis.user_preferences_store import UserPreferencesStore
        jarvisappv4.user_store = UserStore()
        jarvisappv4.user_preferences_store = UserPreferencesStore()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()
        for key in [
            "JARVIS_CHAT_HISTORY_PATH", "JARVIS_RAG_CACHE_PATH", "JARVIS_MEMORY_PATH",
            "STT_PROVIDER", "JARVIS_USER_STORE_PATH", "JARVIS_USER_PREFERENCES_PATH",
        ]:
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

    def test_tts_voice_field_in_body_overrides_stored_preference(self):
        captured = {}
        def fake_synth(text, voice=None):
            captured["voice"] = voice
            return b"RIFFmockwav", "audio/wav"
        with patch("jarvisappv4.synthesize_tts", side_effect=fake_synth):
            res = self.client.post("/tts", json={"text": "Hello sir.", "voice": "en-GB-ThomasNeural"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(captured.get("voice"), "en-GB-ThomasNeural")

    def test_tts_empty_voice_field_uses_server_default(self):
        captured = {}
        def fake_synth(text, voice=None):
            captured["voice"] = voice
            return b"RIFFmockwav", "audio/wav"
        with patch("jarvisappv4.synthesize_tts", side_effect=fake_synth):
            res = self.client.post("/tts", json={"text": "Hello sir.", "voice": ""})
        self.assertEqual(res.status_code, 200)
        # No session → voice falls back to whatever synthesize_tts resolves (server env default)
        self.assertEqual(captured.get("voice"), "")

    def test_tts_voice_field_is_optional(self):
        with patch("jarvisappv4.synthesize_tts", return_value=(b"RIFFmockwav", "audio/wav")):
            res = self.client.post("/tts", json={"text": "Hello sir."})
        self.assertEqual(res.status_code, 200)

    def _seed_user_session(self, username: str, tts_voice: str) -> tuple[str, str]:
        import jarvisappv4 as app
        import time
        user = app.user_store.create_user(username, role="standard_user", enabled=True)
        user_id = user["id"]
        app.user_preferences_store.update(user_id, {"tts_voice": tts_voice})
        token = f"test-tok-{username}"
        app._identity_tokens[token] = {"user_id": user_id, "role": "standard_user", "exp": time.time() + 3600}
        return token, user_id

    def _cleanup_user_session(self, token: str, user_id: str) -> None:
        import jarvisappv4 as app
        app._identity_tokens.pop(token, None)
        app.user_preferences_store.delete(user_id)
        app.user_store.delete_user(user_id)

    def test_tts_voice_preference_used_when_session_present(self):
        token, user_id = self._seed_user_session("testvoice-pref", "en-GB-ElliotNeural")
        captured = {}
        def fake_synth(text, voice=None):
            captured["voice"] = voice
            return b"RIFFmockwav", "audio/wav"
        try:
            with patch("jarvisappv4.synthesize_tts", side_effect=fake_synth):
                res = self.client.post(
                    "/tts",
                    json={"text": "Testing voice preference."},
                    headers={"X-Jarvis-Session": token},
                )
            self.assertEqual(res.status_code, 200)
            self.assertEqual(captured.get("voice"), "en-GB-ElliotNeural")
        finally:
            self._cleanup_user_session(token, user_id)

    def test_tts_body_voice_overrides_stored_preference(self):
        token, user_id = self._seed_user_session("testvoice-override", "en-GB-ElliotNeural")
        captured = {}
        def fake_synth(text, voice=None):
            captured["voice"] = voice
            return b"RIFFmockwav", "audio/wav"
        try:
            with patch("jarvisappv4.synthesize_tts", side_effect=fake_synth):
                res = self.client.post(
                    "/tts",
                    json={"text": "Testing override.", "voice": "en-US-GuyNeural"},
                    headers={"X-Jarvis-Session": token},
                )
            self.assertEqual(res.status_code, 200)
            # Body voice should win over stored preference
            self.assertEqual(captured.get("voice"), "en-US-GuyNeural")
        finally:
            self._cleanup_user_session(token, user_id)


if __name__ == "__main__":
    unittest.main()
