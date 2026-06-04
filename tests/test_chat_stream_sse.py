"""Integration tests for the /chat/stream SSE endpoint."""
import json
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4


def _collect_sse(response) -> list[dict]:
    """Read all SSE `data:` payloads from a streaming httpx response."""
    events = []
    buf = ""
    for chunk in response.iter_bytes():
        buf += chunk.decode("utf-8", errors="replace")
        while "\n\n" in buf:
            block, buf = buf.split("\n\n", 1)
            for line in block.splitlines():
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
    return events


class ChatStreamSSETests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(self.tmpdir.name, "ch.json")
        self.client = TestClient(jarvisappv4.app, raise_server_exceptions=False)

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_CHAT_HISTORY_PATH", None)

    def _stream_events(self, text: str, session_id: str | None = None) -> list[dict]:
        body: dict = {"text": text, "source": "web"}
        if session_id:
            body["session_id"] = session_id
        with self.client.stream("POST", "/chat/stream", json=body) as r:
            self.assertEqual(200, r.status_code)
            return _collect_sse(r)

    def test_stream_returns_200_and_content_type(self):
        with self.client.stream("POST", "/chat/stream", json={"text": "hello", "source": "web"}) as r:
            self.assertEqual(200, r.status_code)
            ct = r.headers.get("content-type", "")
            self.assertIn("text/event-stream", ct)
            r.read()  # drain

    def test_stream_emits_done_event(self):
        events = self._stream_events("hello")
        types = [e.get("type") for e in events]
        self.assertIn("done", types)

    def test_stream_done_event_contains_session_id(self):
        events = self._stream_events("hello")
        done = next((e for e in events if e.get("type") == "done"), None)
        self.assertIsNotNone(done)
        self.assertTrue((done.get("session_id") or "").startswith("chat-"))

    def test_stream_done_event_contains_reply(self):
        events = self._stream_events("ping")
        done = next((e for e in events if e.get("type") == "done"), None)
        self.assertIsNotNone(done)
        self.assertIsInstance(done.get("reply"), str)
        self.assertGreater(len(done["reply"]), 0)

    def test_stream_done_is_last_event(self):
        events = self._stream_events("hello")
        if events:
            self.assertEqual("done", events[-1].get("type"))

    def test_stream_with_session_id_reuses_session(self):
        events1 = self._stream_events("first message")
        done1 = next(e for e in events1 if e.get("type") == "done")
        sid = done1["session_id"]

        events2 = self._stream_events("second message", session_id=sid)
        done2 = next(e for e in events2 if e.get("type") == "done")
        self.assertEqual(sid, done2["session_id"])

    def test_stream_empty_text_returns_done_or_error(self):
        events = self._stream_events("")
        types = [e.get("type") for e in events]
        self.assertTrue(
            "done" in types or "error" in types,
            f"Expected done or error, got: {types}",
        )

    def test_stream_skill_reply_is_non_empty(self):
        events = self._stream_events("jarvis version")
        done = next((e for e in events if e.get("type") == "done"), None)
        self.assertIsNotNone(done)
        self.assertGreater(len(done.get("reply", "")), 0)


if __name__ == "__main__":
    unittest.main()
