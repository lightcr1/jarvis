import os
import tempfile
import unittest

from jarvis.admin_password_store import AdminPasswordStore


class AdminPasswordStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(self.tmpdir.name, "pw.json")
        self.store = AdminPasswordStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_ADMIN_PASSWORD_STORE_PATH", None)

    # ── has_password ─────────────────────────────────────────────────────────

    def test_has_password_false_for_new_store(self):
        self.assertFalse(self.store.has_password("user:usr-1"))

    def test_has_password_true_after_set(self):
        self.store.set_password("user:usr-1", "secret")
        self.assertTrue(self.store.has_password("user:usr-1"))

    def test_has_password_false_for_other_user(self):
        self.store.set_password("user:usr-1", "secret")
        self.assertFalse(self.store.has_password("user:usr-2"))

    # ── set_password / verify_password ───────────────────────────────────────

    def test_correct_password_verifies(self):
        self.store.set_password("user:usr-1", "correct-horse")
        self.assertTrue(self.store.verify_password("user:usr-1", "correct-horse"))

    def test_wrong_password_fails(self):
        self.store.set_password("user:usr-1", "correct-horse")
        self.assertFalse(self.store.verify_password("user:usr-1", "wrong-password"))

    def test_empty_password_can_be_set_and_verified(self):
        self.store.set_password("user:usr-1", "")
        self.assertTrue(self.store.verify_password("user:usr-1", ""))
        self.assertFalse(self.store.verify_password("user:usr-1", "nonempty"))

    def test_verify_unknown_user_returns_false(self):
        self.assertFalse(self.store.verify_password("user:ghost", "anything"))

    def test_set_password_overwrites_old_hash(self):
        self.store.set_password("user:usr-1", "old-pass")
        self.store.set_password("user:usr-1", "new-pass")
        self.assertTrue(self.store.verify_password("user:usr-1", "new-pass"))
        self.assertFalse(self.store.verify_password("user:usr-1", "old-pass"))

    def test_different_users_independent(self):
        self.store.set_password("user:a", "pass-a")
        self.store.set_password("user:b", "pass-b")
        self.assertTrue(self.store.verify_password("user:a", "pass-a"))
        self.assertTrue(self.store.verify_password("user:b", "pass-b"))
        self.assertFalse(self.store.verify_password("user:a", "pass-b"))
        self.assertFalse(self.store.verify_password("user:b", "pass-a"))

    def test_stored_record_has_expected_fields(self):
        self.store.set_password("user:usr-1", "test")
        record = self.store.data["credentials"]["user:usr-1"]
        self.assertIn("salt", record)
        self.assertIn("hash", record)
        self.assertIn("rounds", record)
        self.assertIn("updated_at", record)

    def test_rounds_stored_correctly(self):
        self.store.set_password("user:usr-1", "test", rounds=1000)
        self.assertEqual(1000, self.store.data["credentials"]["user:usr-1"]["rounds"])

    def test_custom_rounds_still_verifies(self):
        self.store.set_password("user:usr-1", "test", rounds=1000)
        self.assertTrue(self.store.verify_password("user:usr-1", "test"))

    # ── delete_password ───────────────────────────────────────────────────────

    def test_delete_existing_password_returns_true(self):
        self.store.set_password("user:usr-1", "pass")
        self.assertTrue(self.store.delete_password("user:usr-1"))

    def test_delete_removes_credential(self):
        self.store.set_password("user:usr-1", "pass")
        self.store.delete_password("user:usr-1")
        self.assertFalse(self.store.has_password("user:usr-1"))

    def test_delete_nonexistent_returns_false(self):
        self.assertFalse(self.store.delete_password("user:ghost"))

    def test_delete_does_not_affect_other_users(self):
        self.store.set_password("user:a", "pass-a")
        self.store.set_password("user:b", "pass-b")
        self.store.delete_password("user:a")
        self.assertTrue(self.store.has_password("user:b"))

    def test_verify_after_delete_returns_false(self):
        self.store.set_password("user:usr-1", "pass")
        self.store.delete_password("user:usr-1")
        self.assertFalse(self.store.verify_password("user:usr-1", "pass"))

    # ── persistence ──────────────────────────────────────────────────────────

    def test_persists_across_reload(self):
        self.store.set_password("user:usr-1", "persistent-pass")
        store2 = AdminPasswordStore()
        self.assertTrue(store2.has_password("user:usr-1"))
        self.assertTrue(store2.verify_password("user:usr-1", "persistent-pass"))

    def test_delete_persists_across_reload(self):
        self.store.set_password("user:usr-1", "pass")
        self.store.delete_password("user:usr-1")
        store2 = AdminPasswordStore()
        self.assertFalse(store2.has_password("user:usr-1"))

    def test_corrupt_file_loads_empty(self):
        path = self.store.path
        path.write_text("not-valid-json", encoding="utf-8")
        store2 = AdminPasswordStore()
        self.assertEqual({}, store2.data.get("credentials", {}))

    def test_salt_is_random_per_set(self):
        self.store.set_password("user:usr-1", "same-pass")
        salt1 = self.store.data["credentials"]["user:usr-1"]["salt"]
        self.store.set_password("user:usr-1", "same-pass")
        salt2 = self.store.data["credentials"]["user:usr-1"]["salt"]
        self.assertNotEqual(salt1, salt2)


if __name__ == "__main__":
    unittest.main()
