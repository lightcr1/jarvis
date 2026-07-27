import os
import tempfile
import unittest

from jarvis.runtime_state import ChatHistoryStore
from jarvis.api_auth_chat import _find_related_history


class FindRelatedHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(self.tmpdir.name, "ch.json")
        self.store = ChatHistoryStore()
        self.owner = "user:usr-1"

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_CHAT_HISTORY_PATH", None)

    def test_finds_hit_from_other_session(self):
        old = self.store.create_session("Old chat", owner_key=self.owner)
        self.store.append_message(old["id"], "user", "How do I migrate the database safely", owner_key=self.owner)
        current = self.store.create_session("New chat", owner_key=self.owner)

        results = _find_related_history(self.store, self.owner, current["id"], "any tips for the database migration", limit=3)

        self.assertEqual(1, len(results))
        self.assertIn("migrate the database", results[0])

    def test_excludes_hits_from_current_session(self):
        session = self.store.create_session("Chat", owner_key=self.owner)
        self.store.append_message(session["id"], "user", "tell me about database migration", owner_key=self.owner)

        results = _find_related_history(self.store, self.owner, session["id"], "database migration again", limit=3)

        self.assertEqual([], results)

    def test_short_message_yields_no_keywords(self):
        session = self.store.create_session("Chat", owner_key=self.owner)
        results = _find_related_history(self.store, self.owner, session["id"], "ok", limit=3)
        self.assertEqual([], results)

    def test_no_matches_returns_empty(self):
        session = self.store.create_session("Chat", owner_key=self.owner)
        results = _find_related_history(self.store, self.owner, session["id"], "completely unrelated topic here", limit=3)
        self.assertEqual([], results)

    def test_respects_limit(self):
        for i in range(5):
            s = self.store.create_session(f"Chat {i}", owner_key=self.owner)
            self.store.append_message(s["id"], "user", f"discussing proxmox cluster setup number {i}", owner_key=self.owner)
        current = self.store.create_session("Current", owner_key=self.owner)

        results = _find_related_history(self.store, self.owner, current["id"], "proxmox cluster question", limit=2)

        self.assertLessEqual(len(results), 2)

    def test_isolated_by_owner_key(self):
        other = self.store.create_session("Other user chat", owner_key="user:usr-2")
        self.store.append_message(other["id"], "user", "database migration notes", owner_key="user:usr-2")
        current = self.store.create_session("Current", owner_key=self.owner)

        results = _find_related_history(self.store, self.owner, current["id"], "database migration", limit=3)

        self.assertEqual([], results)


if __name__ == "__main__":
    unittest.main()
