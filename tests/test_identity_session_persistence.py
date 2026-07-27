import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.audit_log_store import AuditLogStore
from jarvis.user_store import UserStore
from jarvis.admin_password_store import AdminPasswordStore
from jarvis.user_preferences_store import UserPreferencesStore
from jarvis.runtime_helpers import load_identity_tokens


class IdentitySessionPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(self.tmpdir.name, "users.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(self.tmpdir.name, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(self.tmpdir.name, "prefs.json")

        jarvisappv4.audit_log = AuditLogStore()
        jarvisappv4.user_store = UserStore()
        jarvisappv4.admin_password_store = AdminPasswordStore()
        jarvisappv4.user_preferences_store = UserPreferencesStore()
        jarvisappv4._identity_tokens.clear()
        jarvisappv4._tokens.clear()

        self._orig_path = jarvisappv4._IDENTITY_SESSIONS_PATH
        self.sessions_path = os.path.join(self.tmpdir.name, "identity_sessions.json")
        jarvisappv4._IDENTITY_SESSIONS_PATH = self.sessions_path
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        jarvisappv4._IDENTITY_SESSIONS_PATH = self._orig_path
        jarvisappv4._identity_tokens.clear()
        jarvisappv4._tokens.clear()
        self.tmpdir.cleanup()
        for key in ("JARVIS_USER_STORE_PATH", "JARVIS_ADMIN_PASSWORD_STORE_PATH", "JARVIS_USER_PREFERENCES_PATH"):
            os.environ.pop(key, None)

    def _create_admin(self, username="admin1", password="secret123"):
        user = jarvisappv4.user_store.create_user(username, role="admin", enabled=True)
        jarvisappv4.admin_password_store.set_password(user["id"], password)
        return user

    def _login(self, username="admin1", password="secret123"):
        res = self.client.post("/auth/login", json={"username": username, "password": password})
        self.assertEqual(200, res.status_code)
        return res.json()["session_token"]

    def _admin_bearer(self, username="admin1", password="secret123"):
        res = self.client.post("/admin/login", json={"username": username, "password": password})
        self.assertEqual(200, res.status_code)
        return res.json()["token"]

    def test_login_persists_session_to_disk(self):
        self._create_admin()
        token = self._login()

        on_disk = load_identity_tokens(self.sessions_path)
        self.assertIn(token, on_disk)

    def test_session_survives_simulated_restart(self):
        self._create_admin()
        token = self._login()

        reloaded = load_identity_tokens(self.sessions_path)
        jarvisappv4._identity_tokens.clear()
        jarvisappv4._identity_tokens.update(reloaded)

        res = self.client.get("/auth/me", headers={"X-Jarvis-Session": token})
        self.assertEqual(200, res.status_code)

    def test_logout_removes_session_from_disk(self):
        self._create_admin()
        token = self._login()

        self.client.post("/auth/logout", headers={"X-Jarvis-Session": token})

        on_disk = load_identity_tokens(self.sessions_path)
        self.assertNotIn(token, on_disk)

    def test_logout_without_session_header_does_not_error(self):
        self._create_admin()
        self._login()

        res = self.client.post("/auth/logout")
        self.assertEqual(200, res.status_code)

    def test_admin_revoke_sessions_removes_from_disk(self):
        admin = self._create_admin()
        token = self._login()
        bearer = self._admin_bearer()

        res = self.client.delete(
            f"/admin/sessions/{admin['id']}",
            headers={"Authorization": f"Bearer {bearer}", "X-Jarvis-User-Id": admin["id"], "X-Jarvis-Role": "admin"},
        )
        self.assertEqual(200, res.status_code)
        self.assertGreaterEqual(res.json()["revoked"], 1)

        on_disk = load_identity_tokens(self.sessions_path)
        self.assertNotIn(token, on_disk)


if __name__ == "__main__":
    unittest.main()
