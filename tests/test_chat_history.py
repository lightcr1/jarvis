import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4


class ChatHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(self.tmpdir.name, "chat_history.json")
        os.environ["JARVIS_RAG_CACHE_PATH"] = os.path.join(self.tmpdir.name, "rag_cache.json")
        jarvisappv4.chat_history = jarvisappv4.ChatHistoryStore()
        jarvisappv4.rag_store = jarvisappv4.RagStore()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_session_created_and_messages_persist(self):
        res = self.client.post("/chat", json={"text": "health"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body.get("session_id"))

        sid = body["session_id"]
        detail = self.client.get(f"/chat/sessions/{sid}")
        self.assertEqual(detail.status_code, 200)
        session = detail.json()
        self.assertGreaterEqual(len(session.get("messages", [])), 2)

    def test_create_and_list_sessions(self):
        create = self.client.post("/chat/sessions", json={"title": "Deploy Chat"})
        self.assertEqual(create.status_code, 200)
        sid = create.json()["id"]

        listing = self.client.get("/chat/sessions")
        self.assertEqual(listing.status_code, 200)
        ids = [s["id"] for s in listing.json().get("sessions", [])]
        self.assertIn(sid, ids)



    def test_delete_session(self):
        create = self.client.post("/chat/sessions", json={"title": "Delete me"})
        self.assertEqual(create.status_code, 200)
        sid = create.json()["id"]

        delete = self.client.delete(f"/chat/sessions/{sid}")
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.json().get("ok"))

        detail = self.client.get(f"/chat/sessions/{sid}")
        self.assertEqual(detail.status_code, 404)

if __name__ == "__main__":
    unittest.main()
