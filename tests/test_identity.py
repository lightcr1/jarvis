import os
import tempfile
import unittest

from identity import get_active_user_or_raise
from user_store import UserStore


class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(self.tmpdir.name, "users.json")
        self.users = UserStore()

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_USER_STORE_PATH", None)

    def test_none_user_id_returns_none(self):
        self.assertIsNone(get_active_user_or_raise(self.users, None))

    def test_missing_user_raises_lookup(self):
        with self.assertRaises(LookupError):
            get_active_user_or_raise(self.users, "usr-missing")

    def test_disabled_user_raises_permission_error(self):
        u = self.users.create_user("disabled", enabled=False)
        with self.assertRaises(PermissionError):
            get_active_user_or_raise(self.users, u["id"])

    def test_enabled_user_returns_user(self):
        u = self.users.create_user("enabled", enabled=True)
        got = get_active_user_or_raise(self.users, u["id"])
        self.assertEqual(got["id"], u["id"])


if __name__ == "__main__":
    unittest.main()
