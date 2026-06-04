import os
import tempfile
import unittest

from fastapi.testclient import TestClient

from jarvis.memory_store import MemoryStore
from jarvis.api_memory import build_memory_router
from fastapi import FastAPI


def _make_app(store: MemoryStore, *, user_id: str = "usr-test", require_ok: bool = True):
    app = FastAPI()

    def fake_require_session(token):
        if not require_ok:
            from fastapi import HTTPException
            raise HTTPException(401, "login required")
        return {"user": {"id": user_id, "username": "testuser", "role": "admin"}}

    deps = {
        "require_identity_session": fake_require_session,
        "memory_store": store,
    }
    app.include_router(build_memory_router(deps))
    return app


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmpdir.name, "memory.json")

    def tearDown(self):
        self.tmpdir.cleanup()

    def _store(self) -> MemoryStore:
        from pathlib import Path
        return MemoryStore(Path(self.path))

    def test_add_and_get_notes(self):
        store = self._store()
        note = store.add_note("u1", "buy milk")
        self.assertIn("id", note)
        self.assertEqual(note["text"], "buy milk")
        self.assertIsInstance(note["created_at"], int)
        notes = store.get_notes("u1")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "buy milk")

    def test_delete_note(self):
        store = self._store()
        note = store.add_note("u1", "test note")
        deleted = store.delete_note("u1", note["id"])
        self.assertTrue(deleted)
        self.assertEqual(store.get_notes("u1"), [])

    def test_delete_nonexistent_note_returns_false(self):
        store = self._store()
        self.assertFalse(store.delete_note("u1", "does-not-exist"))

    def test_aliases_set_and_get(self):
        store = self._store()
        entry = store.set_alias("u1", "city", "Berlin")
        self.assertEqual(entry["target"], "Berlin")
        aliases = store.get_aliases("u1")
        self.assertIn("city", aliases)
        self.assertEqual(aliases["city"]["target"], "Berlin")

    def test_delete_alias(self):
        store = self._store()
        store.set_alias("u1", "city", "Berlin")
        deleted = store.delete_alias("u1", "city")
        self.assertTrue(deleted)
        self.assertNotIn("city", store.get_aliases("u1"))

    def test_delete_nonexistent_alias_returns_false(self):
        store = self._store()
        self.assertFalse(store.delete_alias("u1", "missing"))

    def test_clear_user(self):
        store = self._store()
        store.add_note("u1", "a note")
        store.set_alias("u1", "k", "v")
        store.clear_user("u1")
        self.assertEqual(store.get_notes("u1"), [])
        self.assertEqual(store.get_aliases("u1"), {})

    def test_persists_across_reload(self):
        store = self._store()
        note = store.add_note("u1", "persisted note")
        store.set_alias("u1", "mykey", "myval")

        store2 = self._store()
        notes = store2.get_notes("u1")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["id"], note["id"])
        aliases = store2.get_aliases("u1")
        self.assertEqual(aliases["mykey"]["target"], "myval")

    def test_atomic_write_no_tmp_left(self):
        store = self._store()
        store.add_note("u1", "atomic test")
        tmp = self.path + ".tmp"
        self.assertFalse(os.path.exists(tmp), ".tmp file should be cleaned up after write")

    def test_users_isolated(self):
        store = self._store()
        store.add_note("u1", "user 1 note")
        store.add_note("u2", "user 2 note")
        self.assertEqual(len(store.get_notes("u1")), 1)
        self.assertEqual(len(store.get_notes("u2")), 1)
        self.assertEqual(store.get_notes("u1")[0]["text"], "user 1 note")


class MemoryApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        from pathlib import Path
        self.store = MemoryStore(Path(os.path.join(self.tmpdir.name, "memory.json")))
        self.app = _make_app(self.store)
        self.client = TestClient(self.app)
        self.headers = {"x-jarvis-session": "fake-session"}

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_list_notes_empty(self):
        r = self.client.get("/memory/notes", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_create_note(self):
        r = self.client.post("/memory/notes", json={"text": "hello world"}, headers=self.headers)
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["text"], "hello world")
        self.assertIn("id", data)
        self.assertIsInstance(data["created_at"], int)

    def test_create_note_empty_text_rejected(self):
        r = self.client.post("/memory/notes", json={"text": "  "}, headers=self.headers)
        self.assertEqual(r.status_code, 422)

    def test_list_notes_after_create(self):
        self.client.post("/memory/notes", json={"text": "note one"}, headers=self.headers)
        r = self.client.get("/memory/notes", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        notes = r.json()
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["text"], "note one")

    def test_delete_note(self):
        create_r = self.client.post("/memory/notes", json={"text": "to delete"}, headers=self.headers)
        note_id = create_r.json()["id"]
        del_r = self.client.delete(f"/memory/notes/{note_id}", headers=self.headers)
        self.assertEqual(del_r.status_code, 204)
        r = self.client.get("/memory/notes", headers=self.headers)
        self.assertEqual(r.json(), [])

    def test_delete_nonexistent_note_returns_404(self):
        r = self.client.delete("/memory/notes/no-such-id", headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_list_aliases_empty(self):
        r = self.client.get("/memory/aliases", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_create_alias(self):
        r = self.client.post("/memory/aliases", json={"alias": "city", "target": "Berlin"}, headers=self.headers)
        self.assertEqual(r.status_code, 201)
        data = r.json()
        self.assertEqual(data["alias"], "city")
        self.assertEqual(data["target"], "Berlin")

    def test_create_alias_empty_fields_rejected(self):
        r = self.client.post("/memory/aliases", json={"alias": "", "target": "x"}, headers=self.headers)
        self.assertEqual(r.status_code, 422)

    def test_delete_alias(self):
        self.client.post("/memory/aliases", json={"alias": "lang", "target": "Python"}, headers=self.headers)
        del_r = self.client.delete("/memory/aliases/lang", headers=self.headers)
        self.assertEqual(del_r.status_code, 204)
        r = self.client.get("/memory/aliases", headers=self.headers)
        self.assertEqual(r.json(), [])

    def test_delete_nonexistent_alias_returns_404(self):
        r = self.client.delete("/memory/aliases/ghost", headers=self.headers)
        self.assertEqual(r.status_code, 404)

    def test_summary_endpoint(self):
        self.client.post("/memory/notes", json={"text": "a note"}, headers=self.headers)
        self.client.post("/memory/aliases", json={"alias": "key", "target": "val"}, headers=self.headers)
        r = self.client.get("/memory/summary", headers=self.headers)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["note_count"], 1)
        self.assertEqual(data["alias_count"], 1)

    def test_clear_all_without_confirm_rejected(self):
        r = self.client.delete("/memory/all", headers=self.headers)
        self.assertEqual(r.status_code, 422)

    def test_clear_all_with_confirm(self):
        self.client.post("/memory/notes", json={"text": "will be cleared"}, headers=self.headers)
        r = self.client.delete("/memory/all?confirm=true", headers=self.headers)
        self.assertEqual(r.status_code, 204)
        r2 = self.client.get("/memory/notes", headers=self.headers)
        self.assertEqual(r2.json(), [])

    def test_unauthenticated_returns_401(self):
        unauthed_app = _make_app(self.store, require_ok=False)
        unauthed_client = TestClient(unauthed_app, raise_server_exceptions=False)
        r = unauthed_client.get("/memory/notes", headers={"x-jarvis-session": "bad"})
        self.assertEqual(r.status_code, 401)


class MemorySkillTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        from pathlib import Path
        self.store = MemoryStore(Path(os.path.join(self.tmpdir.name, "memory.json")))
        self.user_id = "usr-skill-test"

    def tearDown(self):
        self.tmpdir.cleanup()

    def _skill(self, text: str):
        from jarvis.assistant_domain import try_skill
        from unittest.mock import Mock
        return try_skill(
            text,
            role="admin",
            token="tok",
            granted_permissions=None,
            emergency_stop_enabled=lambda: False,
            permission_check=lambda *_a: True,
            run_cmd=lambda *_a, **_k: "",
            disk_usage=lambda *_a: Mock(total=100, used=40, free=60),
            format_bytes=lambda v: f"{v}B",
            parse_meminfo=lambda: {},
            parse_ping=lambda _o: {},
            tail_lines=lambda t, **_k: t,
            ensure_service_allowed=lambda _s: None,
            proxmox_vm_status=lambda *_a: {},
            proxmox_lxc_status=lambda *_a: {},
            proxmox_vm_action=lambda *_a: {},
            proxmox_lxc_action=lambda *_a: {},
            user_prefs={},
            memory_store=self.store,
            user_id=self.user_id,
        )

    def test_remember_that_saves_note(self):
        result = self._skill("remember that the wifi password is secret123")
        self.assertIsNotNone(result)
        self.assertIn("Noted", result["reply"])
        notes = self.store.get_notes(self.user_id)
        self.assertEqual(len(notes), 1)
        self.assertIn("wifi password", notes[0]["text"])

    def test_note_that_saves_note(self):
        result = self._skill("note that the project deadline is friday")
        self.assertIsNotNone(result)
        notes = self.store.get_notes(self.user_id)
        self.assertEqual(len(notes), 1)

    def test_what_do_you_know_about_me(self):
        self.store.add_note(self.user_id, "favorite color is blue")
        self.store.set_alias(self.user_id, "city", "Munich")
        result = self._skill("what do you know about me")
        self.assertIsNotNone(result)
        self.assertIn("blue", result["reply"])
        self.assertIn("Munich", result["reply"])

    def test_what_do_you_know_empty(self):
        result = self._skill("what do you know about me")
        self.assertIsNotNone(result)
        self.assertIn("no notes", result["reply"].lower())

    def test_forget_removes_note(self):
        self.store.add_note(self.user_id, "buy milk at the store")
        result = self._skill("forget milk")
        self.assertIsNotNone(result)
        self.assertIn("1", result["reply"])
        self.assertEqual(self.store.get_notes(self.user_id), [])

    def test_remember_key_is_value_saves_alias(self):
        result = self._skill("remember city is Hamburg")
        self.assertIsNotNone(result)
        aliases = self.store.get_aliases(self.user_id)
        self.assertIn("city", aliases)
        # try_skill lowercases input, so stored value is lowercase
        self.assertEqual(aliases["city"]["target"], "hamburg")

    def test_my_notes_shows_notes(self):
        self.store.add_note(self.user_id, "test note content")
        result = self._skill("my notes")
        self.assertIsNotNone(result)
        self.assertIn("test note content", result["reply"])


if __name__ == "__main__":
    unittest.main()
