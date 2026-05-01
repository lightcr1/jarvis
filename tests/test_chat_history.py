import os
import tempfile
import unittest
from unittest.mock import patch

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

    def test_root_serves_chat_page(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("<title>J.A.R.V.I.S.</title>", res.text)



    def test_delete_session(self):
        create = self.client.post("/chat/sessions", json={"title": "Delete me"})
        self.assertEqual(create.status_code, 200)
        sid = create.json()["id"]

        delete = self.client.delete(f"/chat/sessions/{sid}")
        self.assertEqual(delete.status_code, 200)
        self.assertTrue(delete.json().get("ok"))

        detail = self.client.get(f"/chat/sessions/{sid}")
        self.assertEqual(detail.status_code, 404)


    def test_rag_wiki_phrase_maps_to_rag_result(self):
        jarvisappv4.rag_store.data = {
            "sources": {
                "wikijs": [
                    {"title": "tasks", "text": "Tasks page: backlog and priorities", "url": "/tasks"}
                ],
                "github": [],
            },
            "updated_at": 1,
            "report": {},
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False), patch("jarvisappv4.rag_llm_answer", return_value="Understood. Tasks from wiki listed."):
            res = self.client.post("/chat", json={"text": "Lies die Wiki Seite Tasks, was steht darin"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body.get("data", {}).get("route"), "rag")
        self.assertIn("tasks", body.get("reply", "").lower())


    def test_non_rag_question_does_not_get_hijacked_by_rag(self):
        jarvisappv4.rag_store.data = {
            "sources": {
                "wikijs": [{"title": "Budget2025", "text": "Budget planning", "url": "/budget"}],
                "github": [],
            },
            "updated_at": 1,
            "report": {},
        }

        res = self.client.post("/chat", json={"text": "wie ist das wetter heute"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertNotEqual(body.get("data", {}).get("route"), "rag")

    def test_tasks_request_returns_wiki_task_list(self):
        jarvisappv4.rag_store.data = {
            "sources": {
                "wikijs": [
                    {"title": "Tasks", "text": "Task A offen | Task B in Arbeit", "url": "/tasks"},
                    {"title": "Taskboard", "text": "Task C review", "url": "/taskboard"},
                ],
                "github": [],
            },
            "updated_at": 1,
            "report": {},
        }

        with patch.dict(os.environ, {"OPENAI_API_KEY": "dummy"}, clear=False), patch("jarvisappv4.rag_llm_answer", return_value="Understood. Current tasks from wiki: 1) Task A 2) Task B"):
            res = self.client.post("/chat", json={"text": "Zeige die aktuellen Tasks aus der Taskliste"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body.get("data", {}).get("route"), "rag")
        self.assertIn("Current tasks", body.get("reply", ""))


    def test_tasks_request_without_cloud_returns_clear_requirement(self):
        os.environ.pop("OPENAI_API_KEY", None)
        os.environ.pop("GEMINI_API_KEY", None)
        jarvisappv4.rag_store.data = {
            "sources": {
                "wikijs": [
                    {"title": "Budget2025", "text": "Q1 cost down, Q2 invest AI", "url": "/budget2025"},
                ],
                "github": [],
            },
            "updated_at": 1,
            "report": {},
        }

        res = self.client.post("/chat", json={"text": "Lies die Wiki Seite Budget2025 vor und liste die Punkte"})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body.get("data", {}).get("error"), "cloud_llm_required")
        self.assertIn("cloud LLM", body.get("reply", ""))

    def test_rename_session(self):
        create = self.client.post("/chat/sessions", json={"title": "Original Title"})
        self.assertEqual(create.status_code, 200)
        sid = create.json()["id"]

        rename = self.client.patch(f"/chat/sessions/{sid}", json={"title": "Renamed Title"})
        self.assertEqual(rename.status_code, 200)
        self.assertEqual(rename.json()["title"], "Renamed Title")

        detail = self.client.get(f"/chat/sessions/{sid}")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["title"], "Renamed Title")

    def test_get_nonexistent_session_returns_404(self):
        res = self.client.get("/chat/sessions/does-not-exist-123")
        self.assertEqual(res.status_code, 404)

    def test_delete_nonexistent_session_returns_404(self):
        res = self.client.delete("/chat/sessions/ghost-session-abc")
        self.assertEqual(res.status_code, 404)

    def test_session_list_empty_initially(self):
        listing = self.client.get("/chat/sessions")
        self.assertEqual(listing.status_code, 200)
        body = listing.json()
        self.assertIn("sessions", body)
        self.assertEqual(body["sessions"], [])

    def test_chat_message_appends_to_existing_session(self):
        create = self.client.post("/chat/sessions", json={"title": "Persist Test"})
        sid = create.json()["id"]

        self.client.post("/chat", json={"text": "uptime", "session_id": sid})
        detail = self.client.get(f"/chat/sessions/{sid}")
        session = detail.json()
        self.assertGreaterEqual(len(session.get("messages", [])), 2)

    def test_session_title_from_chat_with_explicit_session(self):
        create = self.client.post("/chat/sessions", json={"title": "Test Session"})
        self.assertEqual(create.status_code, 200)
        sid = create.json()["id"]
        res = self.client.post("/chat", json={"text": "health", "session_id": sid})
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body.get("session_id"), sid)


if __name__ == "__main__":
    unittest.main()
