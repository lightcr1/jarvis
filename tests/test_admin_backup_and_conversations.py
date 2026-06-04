"""Tests for /admin/backup/restore and /admin/users/{id}/conversations endpoints."""
import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4


class AdminBackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        jarvisappv4.audit_log = jarvisappv4.AuditLogStore()
        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4._tokens.clear()
        self.client = TestClient(jarvisappv4.app)

        login = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(200, login.status_code)
        body = login.json()
        self.admin_headers = {
            "Authorization": f"Bearer {body['token']}",
            "X-Jarvis-Role": "admin",
            "X-Jarvis-User-Id": body["user_id"],
        }

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_backup_restore_version_mismatch_returns_400(self):
        res = self.client.post(
            "/admin/backup/restore",
            json={"backup_version": 99},
            headers=self.admin_headers,
        )
        self.assertEqual(400, res.status_code)

    def test_backup_restore_restores_users(self):
        existing = jarvisappv4.user_store.list_users()
        fake_users = existing + [
            {"id": "usr-aaa", "username": "restored_user", "role": "standard_user", "enabled": True, "created_at": 0, "updated_at": 0},
        ]
        res = self.client.post(
            "/admin/backup/restore",
            json={"backup_version": 1, "users": fake_users},
            headers=self.admin_headers,
        )
        self.assertEqual(200, res.status_code)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertGreaterEqual(body["restored"]["users"], 1)
        usernames = [u["username"] for u in jarvisappv4.user_store.list_users()]
        self.assertIn("restored_user", usernames)

    def test_backup_restore_without_admin_returns_401(self):
        res = self.client.post(
            "/admin/backup/restore",
            json={"backup_version": 1},
        )
        self.assertIn(res.status_code, (401, 403))

    def test_backup_restore_accepts_partial_payload(self):
        res = self.client.post(
            "/admin/backup/restore",
            json={"backup_version": 1, "groups": []},
            headers=self.admin_headers,
        )
        self.assertEqual(200, res.status_code)
        self.assertTrue(res.json()["ok"])


class AdminConversationDeleteTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_AUDIT_LOG_PATH"] = os.path.join(base, "audit.log")
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = os.path.join(base, "ch.json")
        jarvisappv4.audit_log = jarvisappv4.AuditLogStore()
        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.chat_history = jarvisappv4.ChatHistoryStore()
        jarvisappv4._tokens.clear()
        self.client = TestClient(jarvisappv4.app)

        login = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
        body = login.json()
        self.admin_headers = {
            "Authorization": f"Bearer {body['token']}",
            "X-Jarvis-Role": "admin",
            "X-Jarvis-User-Id": body["user_id"],
        }
        self.admin_user_id = body["user_id"]

    def tearDown(self):
        self.tmpdir.cleanup()
        os.environ.pop("JARVIS_CHAT_HISTORY_PATH", None)

    def test_delete_conversations_for_unknown_user_returns_404(self):
        res = self.client.delete(
            "/admin/users/usr-doesnotexist/conversations",
            headers=self.admin_headers,
        )
        self.assertEqual(404, res.status_code)

    def test_delete_conversations_removes_sessions_for_user(self):
        uid = self.admin_user_id
        owner_key = f"user:{uid}"
        jarvisappv4.chat_history.create_session("Chat A", owner_key=owner_key)
        jarvisappv4.chat_history.create_session("Chat B", owner_key=owner_key)
        self.assertEqual(2, len(jarvisappv4.chat_history.list_sessions(owner_key)))

        res = self.client.delete(
            f"/admin/users/{uid}/conversations",
            headers=self.admin_headers,
        )
        self.assertEqual(200, res.status_code)
        body = res.json()
        self.assertTrue(body["ok"])
        self.assertEqual(2, body["deleted"])
        self.assertEqual(0, len(jarvisappv4.chat_history.list_sessions(owner_key)))

    def test_delete_conversations_without_admin_returns_401(self):
        res = self.client.delete(f"/admin/users/{self.admin_user_id}/conversations")
        self.assertIn(res.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()
