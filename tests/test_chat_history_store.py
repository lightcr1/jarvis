import os
import tempfile
import unittest

from jarvis.runtime_state import ChatHistoryStore, JarvisStatusHub


class ChatHistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(self.tmpdir.name, "ch.json")
        self.store = ChatHistoryStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_CHAT_HISTORY_PATH", None)

    def test_create_session_returns_session(self):
        s = self.store.create_session("Test Chat")
        self.assertTrue(s["id"].startswith("chat-"))
        self.assertEqual("Test Chat", s["title"])
        self.assertEqual("guest:anonymous", s["owner_key"])
        self.assertEqual([], s["messages"])

    def test_create_session_blank_title_uses_default(self):
        s = self.store.create_session("")
        self.assertEqual("New chat", s["title"])

    def test_create_session_none_title_uses_default(self):
        s = self.store.create_session(None)
        self.assertEqual("New chat", s["title"])

    def test_create_session_isolates_by_owner(self):
        s1 = self.store.create_session("Chat A", owner_key="user:usr-1")
        s2 = self.store.create_session("Chat B", owner_key="user:usr-2")
        listed1 = self.store.list_sessions("user:usr-1")
        listed2 = self.store.list_sessions("user:usr-2")
        self.assertEqual(1, len(listed1))
        self.assertEqual(1, len(listed2))
        self.assertEqual(s1["id"], listed1[0]["id"])
        self.assertEqual(s2["id"], listed2[0]["id"])

    def test_get_session_returns_none_for_wrong_owner(self):
        s = self.store.create_session("Secret", owner_key="user:usr-1")
        self.assertIsNone(self.store.get_session(s["id"], owner_key="user:usr-2"))

    def test_get_session_returns_none_for_unknown_id(self):
        self.assertIsNone(self.store.get_session("chat-doesnotexist"))

    def test_append_message_adds_to_session(self):
        s = self.store.create_session()
        self.store.append_message(s["id"], "user", "hello")
        session = self.store.get_session(s["id"])
        self.assertEqual(1, len(session["messages"]))
        self.assertEqual("user", session["messages"][0]["role"])
        self.assertEqual("hello", session["messages"][0]["text"])

    def test_append_message_auto_titles_from_first_user_message(self):
        s = self.store.create_session()
        self.store.append_message(s["id"], "user", "What is the weather")
        session = self.store.get_session(s["id"])
        self.assertEqual("What is the weather", session["title"])

    def test_append_message_does_not_overwrite_custom_title(self):
        s = self.store.create_session("Custom Title")
        self.store.append_message(s["id"], "user", "hello")
        session = self.store.get_session(s["id"])
        self.assertEqual("Custom Title", session["title"])

    def test_ensure_session_returns_existing_for_same_owner(self):
        s = self.store.create_session("Existing", owner_key="user:usr-1")
        reused = self.store.ensure_session(s["id"], owner_key="user:usr-1")
        self.assertEqual(s["id"], reused["id"])

    def test_ensure_session_creates_new_for_different_owner(self):
        s = self.store.create_session("Existing", owner_key="user:usr-1")
        new = self.store.ensure_session(s["id"], owner_key="user:usr-2")
        self.assertNotEqual(s["id"], new["id"])

    def test_ensure_session_creates_new_for_none_session_id(self):
        new = self.store.ensure_session(None)
        self.assertTrue(new["id"].startswith("chat-"))

    def test_delete_session(self):
        s = self.store.create_session()
        result = self.store.delete_session(s["id"])
        self.assertTrue(result)
        self.assertIsNone(self.store.get_session(s["id"]))

    def test_delete_session_wrong_owner_returns_false(self):
        s = self.store.create_session(owner_key="user:usr-1")
        result = self.store.delete_session(s["id"], owner_key="user:usr-2")
        self.assertFalse(result)
        self.assertIsNotNone(self.store.get_session(s["id"], owner_key="user:usr-1"))

    def test_delete_nonexistent_session_returns_false(self):
        result = self.store.delete_session("chat-ghost-xyz")
        self.assertFalse(result)

    def test_rename_session(self):
        s = self.store.create_session("Old Title")
        renamed = self.store.rename_session(s["id"], "New Title")
        self.assertIsNotNone(renamed)
        self.assertEqual("New Title", renamed["title"])
        self.assertEqual("New Title", self.store.get_session(s["id"])["title"])

    def test_rename_session_truncates_at_80_chars(self):
        s = self.store.create_session()
        long_title = "A" * 100
        renamed = self.store.rename_session(s["id"], long_title)
        self.assertLessEqual(len(renamed["title"]), 80)

    def test_rename_session_blank_uses_default(self):
        s = self.store.create_session("Old")
        renamed = self.store.rename_session(s["id"], "")
        self.assertEqual("New chat", renamed["title"])

    def test_rename_session_wrong_owner_returns_none(self):
        s = self.store.create_session(owner_key="user:usr-1")
        result = self.store.rename_session(s["id"], "New", owner_key="user:usr-2")
        self.assertIsNone(result)

    def test_list_sessions_sorted_by_updated_at_desc(self):
        s1 = self.store.create_session("First")
        s2 = self.store.create_session("Second")
        # Force s2 to have a newer updated_at by directly setting it
        self.store.data["sessions"][s1["id"]]["updated_at"] = 1000
        self.store.data["sessions"][s2["id"]]["updated_at"] = 2000
        sessions = self.store.list_sessions()
        self.assertEqual(s2["id"], sessions[0]["id"])

    def test_list_sessions_includes_message_count(self):
        s = self.store.create_session()
        self.store.append_message(s["id"], "user", "test")
        self.store.append_message(s["id"], "assistant", "reply")
        sessions = self.store.list_sessions()
        self.assertEqual(2, sessions[0]["message_count"])

    def test_pending_ha_action_set_and_get(self):
        s = self.store.create_session()
        action = {"entity_id": "light.living_room", "service": "turn_on"}
        self.store.set_pending_home_assistant_action(s["id"], action)
        got = self.store.get_pending_home_assistant_action(s["id"])
        self.assertEqual(action, got)

    def test_clear_pending_ha_action(self):
        s = self.store.create_session()
        self.store.set_pending_home_assistant_action(s["id"], {"service": "turn_on"})
        self.store.clear_pending_home_assistant_action(s["id"])
        self.assertIsNone(self.store.get_pending_home_assistant_action(s["id"]))

    def test_pending_ha_action_none_for_unknown_session(self):
        result = self.store.get_pending_home_assistant_action("chat-ghost")
        self.assertIsNone(result)

    def test_persists_across_reload(self):
        s = self.store.create_session("Persist Test")
        self.store.append_message(s["id"], "user", "hello")
        store2 = ChatHistoryStore()
        session = store2.get_session(s["id"])
        self.assertIsNotNone(session)
        self.assertEqual(1, len(session["messages"]))


class JarvisStatusHubTests(unittest.TestCase):
    def test_initial_state_is_idle(self):
        hub = JarvisStatusHub()
        snap = hub.snapshot()
        self.assertEqual("idle", snap["state"])
        self.assertEqual(0, snap["active"])

    def test_begin_recording_changes_state(self):
        hub = JarvisStatusHub()
        token = hub.begin("recording", source="voice")
        snap = hub.snapshot()
        self.assertEqual("recording", snap["state"])
        self.assertEqual(1, snap["active"])
        hub.end(token)

    def test_end_removes_state(self):
        hub = JarvisStatusHub()
        token = hub.begin("processing")
        hub.end(token)
        self.assertEqual("idle", hub.snapshot()["state"])

    def test_priority_recording_over_processing(self):
        hub = JarvisStatusHub()
        t1 = hub.begin("processing")
        t2 = hub.begin("recording")
        self.assertEqual("recording", hub.snapshot()["state"])
        hub.end(t1)
        hub.end(t2)

    def test_end_none_is_safe(self):
        hub = JarvisStatusHub()
        hub.end(None)  # should not raise

    def test_version_increments_on_begin_and_end(self):
        hub = JarvisStatusHub()
        v0 = hub.snapshot()["version"]
        token = hub.begin("processing")
        v1 = hub.snapshot()["version"]
        hub.end(token)
        v2 = hub.snapshot()["version"]
        self.assertGreater(v1, v0)
        self.assertGreater(v2, v1)

    def test_counts_map_reflects_active_states(self):
        hub = JarvisStatusHub()
        t1 = hub.begin("processing")
        t2 = hub.begin("processing")
        snap = hub.snapshot()
        self.assertEqual(2, snap["counts"]["processing"])
        hub.end(t1)
        hub.end(t2)


if __name__ == "__main__":
    unittest.main()
