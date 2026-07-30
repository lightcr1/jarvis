import json
import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from fastapi.testclient import TestClient

import jarvisappv4


class ProxmoxApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["PROXMOX_HOSTS_FILE"] = os.path.join(base, "proxmox_hosts.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def _login_admin(self):
        return self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()

    def _create_standard_user(self, admin, username):
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        self.assertEqual(200, created.status_code)
        user_id = created.json()["id"]
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        self.assertEqual(200, login.status_code)
        return user_id, login.json()["session_token"]

    def _grant(self, admin, user_id, permissions):
        resp = self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": permissions},
        )
        self.assertEqual(200, resp.status_code)

    def test_hosts_list_requires_session(self):
        resp = self.client.get("/proxmox/hosts")
        self.assertEqual(401, resp.status_code)

    def test_admin_has_proxmox_access_without_explicit_grant(self):
        admin = self._login_admin()
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        session_token = login.json()["session_token"]

        resp = self.client.get("/proxmox/hosts", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, resp.status_code)
        health = self.client.get("/proxmox/health", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, health.status_code)

    def test_standard_user_denied_without_permission(self):
        admin = self._login_admin()
        _, session_token = self._create_standard_user(admin, "alice")

        denied = self.client.get("/proxmox/hosts", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)
        denied_health = self.client.get("/proxmox/health", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied_health.status_code)

    def test_access_permission_allows_read_but_not_manage(self):
        admin = self._login_admin()
        user_id, session_token = self._create_standard_user(admin, "bob")
        self._grant(admin, user_id, ["proxmox.access"])

        allowed = self.client.get("/proxmox/hosts", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, allowed.status_code)

        denied_add = self.client.post(
            "/proxmox/hosts",
            headers={"X-Jarvis-Session": session_token},
            json={"name": "pve-01", "base_url": "http://127.0.0.1:1", "api_token": "user@pve!id=secret-token"},
        )
        self.assertEqual(403, denied_add.status_code)

    def test_manage_permission_allows_adding_and_deleting_host(self):
        payload = {"data": {"version": "8.1"}}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(payload).encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            admin = self._login_admin()
            user_id, session_token = self._create_standard_user(admin, "carol")
            self._grant(admin, user_id, ["proxmox.access", "proxmox.manage"])

            created = self.client.post(
                "/proxmox/hosts",
                headers={"X-Jarvis-Session": session_token},
                json={
                    "name": "pve-01",
                    "base_url": f"http://127.0.0.1:{server.server_port}",
                    "api_token": "user@pve!id=secret-token",
                },
            )
            self.assertEqual(200, created.status_code)
            host_id = created.json()["id"]

            listed = self.client.get("/proxmox/hosts", headers={"X-Jarvis-Session": session_token})
            self.assertEqual(1, len(listed.json()))

            deleted = self.client.delete(f"/proxmox/hosts/{host_id}", headers={"X-Jarvis-Session": session_token})
            self.assertEqual(200, deleted.status_code)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
