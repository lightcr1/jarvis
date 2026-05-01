import os
import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from fastapi.testclient import TestClient

import jarvisappv4


class HomeAssistantApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_HOME_ASSISTANT_STORE_PATH"] = os.path.join(base, "home_assistant.json")
        os.environ.pop("JARVIS_HOME_ASSISTANT_CALENDAR_FILE", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_INBOX_FILE", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_CALENDAR_URL", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_CALENDAR_TOKEN", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_TOKEN", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_CALENDAR_SEED", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_INBOX_URL", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_INBOX_TOKEN", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_INBOX_WRITE_TOKEN", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_INBOX_SEED", None)
        os.environ.pop("JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS", None)

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()
        jarvisappv4.home_assistant_store = jarvisappv4.HomeAssistantStore()
        jarvisappv4.home_assistant_client = jarvisappv4.HomeAssistantClient()
        jarvisappv4.home_assistant_service = jarvisappv4.HomeAssistantService(
            store=jarvisappv4.home_assistant_store,
            client=jarvisappv4.home_assistant_client,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
        )
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_first_admin_can_access_home_assistant_overview(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        self.assertEqual(200, login.status_code)
        session_token = login.json()["session_token"]

        overview = self.client.get("/home-assistant/overview", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, overview.status_code)
        self.assertTrue(overview.json()["policy"]["access_granted"])
        self.assertEqual(admin["user_id"], overview.json()["policy"]["first_admin_user_id"])

    def test_standard_user_needs_explicit_home_assistant_permissions(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "alice", "role": "standard_user", "enabled": True, "password": "alice-pass"},
        )
        self.assertEqual(200, created.status_code)
        user_id = created.json()["id"]

        login = self.client.post("/auth/login", json={"username": "alice", "password": "alice-pass"})
        session_token = login.json()["session_token"]

        denied = self.client.get("/home-assistant/overview", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)

        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access", "home_assistant.device_discovery"]},
        )
        allowed = self.client.get("/home-assistant/overview", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, allowed.status_code)

        created_candidate = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.15",
                "label": "Kitchen Light",
                "suggested_type": "light",
                "suggested_area": "kitchen",
            },
        )
        self.assertEqual(200, created_candidate.status_code)

    def test_approval_and_low_risk_shopping_list_routes(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "ops", "role": "standard_user", "enabled": True, "password": "ops-pass"},
        )
        user_id = created.json()["id"]

        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={
                "permissions": [
                    "home_assistant.access",
                    "home_assistant.device_discovery",
                    "home_assistant.integration_management",
                ]
            },
        )

        login = self.client.post("/auth/login", json={"username": "ops", "password": "ops-pass"})
        session_token = login.json()["session_token"]

        created_candidate = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.21",
                "label": "Office Lamp",
                "suggested_type": "light",
                "suggested_area": "office",
            },
        )
        candidate_id = created_candidate.json()["candidate"]["id"]

        approved = self.client.post(
            f"/home-assistant/discovery/candidates/{candidate_id}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "office", "kind": "light"},
        )
        self.assertEqual(200, approved.status_code)
        self.assertEqual("approved", approved.json()["candidate"]["approval_status"])

        entities = self.client.get("/home-assistant/entities", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, entities.status_code)
        self.assertEqual(1, len(entities.json()["entities"]))

        shopping = self.client.post(
            "/home-assistant/shopping-list/items",
            headers={"X-Jarvis-Session": session_token},
            json={"title": "Tomatoes"},
        )
        self.assertEqual(200, shopping.status_code)

        shopping_list = self.client.get("/home-assistant/shopping-list", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, shopping_list.status_code)
        self.assertEqual("Tomatoes", shopping_list.json()["items"][0]["title"])

        calendar = self.client.post(
            "/home-assistant/calendar/items",
            headers={"X-Jarvis-Session": session_token},
            json={"title": "HVAC check", "starts_at": "2026-03-18T09:00:00Z"},
        )
        self.assertEqual(200, calendar.status_code)

        calendar_items = self.client.get("/home-assistant/calendar", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, calendar_items.status_code)
        self.assertEqual("HVAC check", calendar_items.json()["items"][0]["title"])

        inbox = self.client.post(
            "/home-assistant/inbox/items",
            headers={"X-Jarvis-Session": session_token},
            json={"subject": "Camera alert", "from_label": "Security", "summary": "Motion at entry"},
        )
        self.assertEqual(200, inbox.status_code)

        inbox_items = self.client.get("/home-assistant/inbox", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, inbox_items.status_code)
        self.assertEqual("Camera alert", inbox_items.json()["items"][0]["subject"])

        updated_calendar = self.client.post(
            f"/home-assistant/calendar/items/{calendar.json()['item']['id']}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "mark_done"},
        )
        self.assertEqual(200, updated_calendar.status_code)
        self.assertEqual("completed", updated_calendar.json()["item"]["status"])

        updated_inbox = self.client.post(
            f"/home-assistant/inbox/items/{inbox.json()['item']['id']}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "mark_read"},
        )
        self.assertEqual(200, updated_inbox.status_code)
        self.assertEqual("read", updated_inbox.json()["item"]["status"])

    def test_home_assistant_live_websocket_streams_snapshots(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "viewer", "role": "standard_user", "enabled": True, "password": "viewer-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access", "home_assistant.device_discovery", "home_assistant.integration_management"]},
        )
        session_token = self.client.post("/auth/login", json={"username": "viewer", "password": "viewer-pass"}).json()["session_token"]

        candidate = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.33",
                "label": "Desk Lamp",
                "suggested_type": "light",
                "suggested_area": "office",
            },
        ).json()["candidate"]["id"]
        self.client.post(
            f"/home-assistant/discovery/candidates/{candidate}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"entity_id": "light.office_desk", "area": "office", "kind": "light"},
        )
        jarvisappv4.home_assistant_client.fetch_states = lambda: [
            {
                "entity_id": "light.office_desk",
                "state": "on",
                "attributes": {"brightness": 180},
            }
        ]

        with self.client.websocket_connect(f"/ws/home-assistant?session={session_token}") as websocket:
            payload = websocket.receive_json()

        self.assertEqual("snapshot", payload["type"])
        self.assertEqual("on", payload["entities"][0]["state"])
        self.assertEqual("office", payload["areas"][0]["area"])
        self.assertEqual(1, payload["sync"]["synced_count"])

        jarvisappv4.home_assistant_client.fetch_calendar_items = lambda: [
            {"id": "cal-seed-1", "title": "Filter replacement", "starts_at": "2026-03-20T10:00:00Z", "source": "seed"}
        ]
        jarvisappv4.home_assistant_client.fetch_inbox_items = lambda: [
            {"id": "inbox-seed-1", "subject": "Water leak alert", "from_label": "Home", "summary": "Utility room sensor", "source": "seed"}
        ]

        calendar_sync = self.client.post("/home-assistant/sync/calendar", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, calendar_sync.status_code)
        self.assertEqual(1, calendar_sync.json()["sync"]["synced_count"])

        inbox_sync = self.client.post("/home-assistant/sync/inbox", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, inbox_sync.status_code)
        self.assertEqual(1, inbox_sync.json()["sync"]["synced_count"])

    def test_calendar_and_inbox_file_providers_show_up_in_overview(self):
        import json

        calendar_path = os.path.join(self.tmpdir.name, "calendar_provider.json")
        inbox_path = os.path.join(self.tmpdir.name, "inbox_provider.json")
        with open(calendar_path, "w", encoding="utf-8") as handle:
            json.dump([{"id": "cal-provider-1", "title": "Provider event", "starts_at": "2026-03-22T10:00:00Z"}], handle)
        with open(inbox_path, "w", encoding="utf-8") as handle:
            json.dump([{"id": "inbox-provider-1", "subject": "Provider message", "from_label": "Ops"}], handle)

        os.environ["JARVIS_HOME_ASSISTANT_CALENDAR_FILE"] = calendar_path
        os.environ["JARVIS_HOME_ASSISTANT_INBOX_FILE"] = inbox_path
        jarvisappv4.home_assistant_client = jarvisappv4.HomeAssistantClient()
        jarvisappv4.home_assistant_service = jarvisappv4.HomeAssistantService(
            store=jarvisappv4.home_assistant_store,
            client=jarvisappv4.home_assistant_client,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
        )

        self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        session_token = login.json()["session_token"]
        overview = self.client.get("/home-assistant/overview", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, overview.status_code)
        self.assertEqual("file", overview.json()["integration"]["calendar_provider"])
        self.assertEqual("file", overview.json()["integration"]["inbox_provider"])

    def test_calendar_and_inbox_http_providers_show_up_in_overview(self):
        import json

        calendar_payload = [{"id": "cal-http-1", "title": "Provider HTTP event", "starts_at": "2026-03-24T10:00:00Z"}]
        inbox_payload = [{"id": "inbox-http-1", "subject": "Provider HTTP message", "from_label": "Ops"}]

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path == "/calendar":
                    payload = calendar_payload
                elif self.path == "/inbox":
                    payload = inbox_payload
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
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
            os.environ["JARVIS_HOME_ASSISTANT_CALENDAR_URL"] = f"http://127.0.0.1:{server.server_port}/calendar"
            os.environ["JARVIS_HOME_ASSISTANT_INBOX_URL"] = f"http://127.0.0.1:{server.server_port}/inbox"
            jarvisappv4.home_assistant_client = jarvisappv4.HomeAssistantClient()
            jarvisappv4.home_assistant_service = jarvisappv4.HomeAssistantService(
                store=jarvisappv4.home_assistant_store,
                client=jarvisappv4.home_assistant_client,
                user_store=jarvisappv4.user_store,
                membership_store=jarvisappv4.membership_store,
                permission_store=jarvisappv4.permission_store,
                resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
                normalize_role=jarvisappv4.normalize_role,
            )

            self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
            login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
            session_token = login.json()["session_token"]
            overview = self.client.get("/home-assistant/overview", headers={"X-Jarvis-Session": session_token})
            self.assertEqual(200, overview.status_code)
            self.assertEqual("http", overview.json()["integration"]["calendar_provider"])
            self.assertEqual("http", overview.json()["integration"]["inbox_provider"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_calendar_and_inbox_write_back_flags_show_up_in_overview(self):
        os.environ["JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL"] = "https://calendar.example/api/items"
        os.environ["JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL"] = "https://inbox.example/api/items"
        jarvisappv4.home_assistant_client = jarvisappv4.HomeAssistantClient()
        jarvisappv4.home_assistant_service = jarvisappv4.HomeAssistantService(
            store=jarvisappv4.home_assistant_store,
            client=jarvisappv4.home_assistant_client,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
        )

        self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        session_token = login.json()["session_token"]
        overview = self.client.get("/home-assistant/overview", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, overview.status_code)
        self.assertTrue(overview.json()["integration"]["calendar_write_enabled"])
        self.assertTrue(overview.json()["integration"]["inbox_write_enabled"])

    def test_calendar_and_inbox_action_write_back_updates_metadata(self):
        import json

        writes: list[tuple[str, dict]] = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                content_length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(content_length).decode("utf-8") if content_length else "{}"
                payload = json.loads(raw)
                writes.append((self.path, payload))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"accepted": True, "mode": payload.get("mode", "create")}).encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            os.environ["JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL"] = f"http://127.0.0.1:{server.server_port}/calendar-write"
            os.environ["JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL"] = f"http://127.0.0.1:{server.server_port}/inbox-write"
            jarvisappv4.home_assistant_client = jarvisappv4.HomeAssistantClient()
            jarvisappv4.home_assistant_service = jarvisappv4.HomeAssistantService(
                store=jarvisappv4.home_assistant_store,
                client=jarvisappv4.home_assistant_client,
                user_store=jarvisappv4.user_store,
                membership_store=jarvisappv4.membership_store,
                permission_store=jarvisappv4.permission_store,
                resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
                normalize_role=jarvisappv4.normalize_role,
            )

            self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
            login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
            session_token = login.json()["session_token"]

            calendar = self.client.post(
                "/home-assistant/calendar/items",
                headers={"X-Jarvis-Session": session_token},
                json={"title": "Write-back event", "starts_at": "2026-03-27T10:00:00Z"},
            ).json()["item"]
            inbox = self.client.post(
                "/home-assistant/inbox/items",
                headers={"X-Jarvis-Session": session_token},
                json={"subject": "Write-back inbox", "from_label": "Remote"},
            ).json()["item"]

            writes.clear()
            calendar_action = self.client.post(
                f"/home-assistant/calendar/items/{calendar['id']}/actions",
                headers={"X-Jarvis-Session": session_token},
                json={"action": "mark_done"},
            )
            inbox_action = self.client.post(
                f"/home-assistant/inbox/items/{inbox['id']}/actions",
                headers={"X-Jarvis-Session": session_token},
                json={"action": "archive"},
            )

            self.assertEqual(200, calendar_action.status_code)
            self.assertEqual("synced", calendar_action.json()["item"]["metadata"]["provider_write"])
            self.assertEqual(200, inbox_action.status_code)
            self.assertEqual("synced", inbox_action.json()["item"]["metadata"]["provider_write"])
            self.assertEqual(2, len(writes))
            self.assertEqual("update", writes[0][1]["mode"])
            self.assertEqual("update", writes[1][1]["mode"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_retry_provider_writes_playbook_is_executable_via_api(self):
        self.client.post("/admin/login", json={"username": "admin", "password": "admin123"})
        login = self.client.post("/auth/login", json={"username": "admin", "password": "admin123"})
        session_token = login.json()["session_token"]

        jarvisappv4.home_assistant_store.add_calendar_item(
            {
                "id": "cal-api-retry-1",
                "title": "API retry event",
                "starts_at": "2026-03-30T10:00:00Z",
                "status": "scheduled",
                "source": "jarvis",
                "created_at": 1,
                "metadata": {"provider_write": "deferred", "provider_operation": "create"},
            }
        )
        jarvisappv4.home_assistant_store.add_inbox_item(
            {
                "id": "inbox-api-retry-1",
                "subject": "API retry inbox",
                "from_label": "Ops",
                "status": "unread",
                "received_at": 1,
                "source": "jarvis",
                "metadata": {"provider_write": "deferred", "provider_operation": "create"},
            }
        )
        jarvisappv4.home_assistant_client.create_calendar_item = lambda item: {"accepted": True, "id": item["id"]}
        jarvisappv4.home_assistant_client.create_inbox_item = lambda item: {"accepted": True, "id": item["id"]}

        executed = self.client.post(
            "/home-assistant/recovery-playbooks/retry_provider_writes/execute",
            headers={"X-Jarvis-Session": session_token},
        )
        self.assertEqual(200, executed.status_code)
        self.assertEqual(2, executed.json()["result"]["retried_total"])

    def test_control_requests_enforce_basic_and_security_flows(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "control", "role": "standard_user", "enabled": True, "password": "control-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={
                "permissions": [
                    "home_assistant.access",
                    "home_assistant.integration_management",
                    "home_assistant.device_discovery",
                    "home_assistant.device_control",
                    "home_assistant.security_device_control",
                    "home_assistant.remote_control",
                ]
            },
        )

        login = self.client.post("/auth/login", json={"username": "control", "password": "control-pass"})
        session_token = login.json()["session_token"]

        light_candidate = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.41",
                "label": "Desk Light",
                "suggested_type": "light",
                "suggested_area": "office",
            },
        ).json()["candidate"]["id"]
        light_entity = self.client.post(
            f"/home-assistant/discovery/candidates/{light_candidate}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "office", "kind": "light"},
        ).json()["entity"]["entity_id"]

        light_action = self.client.post(
            f"/home-assistant/entities/{light_entity}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "turn_on", "value": "on"},
        )
        self.assertEqual(200, light_action.status_code)
        self.assertTrue(light_action.json()["executed"])

        lock_candidate = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.42",
                "label": "Front Door",
                "suggested_type": "lock",
                "suggested_area": "entry",
            },
        ).json()["candidate"]["id"]
        lock_entity = self.client.post(
            f"/home-assistant/discovery/candidates/{lock_candidate}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "entry", "kind": "lock"},
        ).json()["entity"]["entity_id"]

        security_action = self.client.post(
            f"/home-assistant/entities/{lock_entity}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "unlock", "value": "unlocked", "remote": True},
        )
        self.assertEqual(200, security_action.status_code)
        self.assertFalse(security_action.json()["executed"])

        request_id = security_action.json()["request"]["id"]
        requests = self.client.get("/home-assistant/control-requests", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, requests.status_code)
        self.assertEqual(2, len(requests.json()["requests"]))

        confirm = self.client.post(
            f"/home-assistant/control-requests/{request_id}/confirm",
            headers={"X-Jarvis-Session": session_token},
            json={"confirmed": True},
        )
        self.assertEqual(200, confirm.status_code)
        self.assertTrue(confirm.json()["executed"])

        health = self.client.get("/home-assistant/health", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, health.status_code)
        self.assertIn("health", health.json())

    def test_entity_sync_endpoint_updates_local_entity_state(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "syncuser", "role": "standard_user", "enabled": True, "password": "sync-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access", "home_assistant.integration_management", "home_assistant.device_discovery"]},
        )

        login = self.client.post("/auth/login", json={"username": "syncuser", "password": "sync-pass"})
        session_token = login.json()["session_token"]

        candidate_id = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.51",
                "label": "Ceiling Light",
                "suggested_type": "light",
                "suggested_area": "office",
            },
        ).json()["candidate"]["id"]
        entity_id = self.client.post(
            f"/home-assistant/discovery/candidates/{candidate_id}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "office", "kind": "light", "entity_id": "light.office_ceiling"},
        ).json()["entity"]["entity_id"]

        jarvisappv4.home_assistant_client.fetch_states = lambda: [
            {"entity_id": entity_id, "state": "on", "attributes": {"friendly_name": "Ceiling Light"}}
        ]
        synced = self.client.post("/home-assistant/sync/entities", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, synced.status_code)
        self.assertEqual(1, synced.json()["sync"]["synced_count"])
        self.assertEqual("on", synced.json()["entities"][0]["state"])

    def test_remote_action_without_remote_control_permission_is_denied(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "noremote", "role": "standard_user", "enabled": True, "password": "remote-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={
                "permissions": [
                    "home_assistant.access",
                    "home_assistant.integration_management",
                    "home_assistant.device_discovery",
                    "home_assistant.security_device_control",
                ]
            },
        )
        login = self.client.post("/auth/login", json={"username": "noremote", "password": "remote-pass"})
        session_token = login.json()["session_token"]
        candidate_id = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.61",
                "label": "Garage Lock",
                "suggested_type": "lock",
                "suggested_area": "garage",
            },
        ).json()["candidate"]["id"]
        entity_id = self.client.post(
            f"/home-assistant/discovery/candidates/{candidate_id}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "garage", "kind": "lock", "entity_id": "lock.garage"},
        ).json()["entity"]["entity_id"]

        denied = self.client.post(
            f"/home-assistant/entities/{entity_id}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "unlock", "value": "unlocked", "remote": True},
        )
        self.assertEqual(403, denied.status_code)

    def test_device_profiles_and_area_summary_endpoints(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "areas", "role": "standard_user", "enabled": True, "password": "areas-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access", "home_assistant.integration_management", "home_assistant.device_discovery"]},
        )
        login = self.client.post("/auth/login", json={"username": "areas", "password": "areas-pass"})
        session_token = login.json()["session_token"]
        candidate_id = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.71",
                "label": "Kitchen Light",
                "suggested_type": "light",
                "suggested_area": "kitchen",
            },
        ).json()["candidate"]["id"]
        self.client.post(
            f"/home-assistant/discovery/candidates/{candidate_id}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "kitchen", "kind": "light", "entity_id": "light.kitchen"},
        )
        profiles = self.client.get("/home-assistant/device-profiles", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, profiles.status_code)
        self.assertIn("light", profiles.json()["profiles"])
        areas = self.client.get("/home-assistant/areas", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, areas.status_code)
        self.assertEqual("kitchen", areas.json()["areas"][0]["area"])

    def test_automation_endpoints_require_automation_management(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "auto", "role": "standard_user", "enabled": True, "password": "auto-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access"]},
        )
        login = self.client.post("/auth/login", json={"username": "auto", "password": "auto-pass"})
        session_token = login.json()["session_token"]

        denied = self.client.post(
            "/home-assistant/automations",
            headers={"X-Jarvis-Session": session_token},
            json={"name": "Evening lights", "target_area": "living_room"},
        )
        self.assertEqual(403, denied.status_code)

        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access", "home_assistant.automation_management"]},
        )
        created_rule = self.client.post(
            "/home-assistant/automations",
            headers={"X-Jarvis-Session": session_token},
            json={
                "name": "Evening lights",
                "target_area": "living_room",
                "trigger": "18:00",
                "action_summary": "Turn on living room lights",
            },
        )
        self.assertEqual(200, created_rule.status_code)
        rule_id = created_rule.json()["automation"]["id"]

        listed = self.client.get("/home-assistant/automations", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, listed.status_code)
        self.assertEqual(1, len(listed.json()["automations"]))

        toggled = self.client.post(
            f"/home-assistant/automations/{rule_id}/toggle",
            headers={"X-Jarvis-Session": session_token},
            json={"enabled": False},
        )
        self.assertEqual(200, toggled.status_code)
        self.assertFalse(toggled.json()["automation"]["enabled"])

    def test_recovery_playbook_endpoints_respect_permissions(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "recovery", "role": "standard_user", "enabled": True, "password": "recovery-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"permissions": ["home_assistant.access", "home_assistant.automation_management"]},
        )
        login = self.client.post("/auth/login", json={"username": "recovery", "password": "recovery-pass"})
        session_token = login.json()["session_token"]

        self.client.post(
            "/home-assistant/automations",
            headers={"X-Jarvis-Session": session_token},
            json={
                "name": "Desk automation",
                "target_area": "office",
                "trigger": "manual",
                "action_summary": "Turn desk lamp on",
            },
        )

        playbooks = self.client.get("/home-assistant/recovery-playbooks", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, playbooks.status_code)
        self.assertGreaterEqual(len(playbooks.json()["playbooks"]), 2)

        executed = self.client.post(
            "/home-assistant/recovery-playbooks/disable_automations/execute",
            headers={"X-Jarvis-Session": session_token},
        )
        self.assertEqual(200, executed.status_code)
        self.assertEqual(1, executed.json()["result"]["disabled_count"])

    def test_system_target_endpoints_require_preapproved_actions(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "systems", "role": "standard_user", "enabled": True, "password": "systems-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={
                "permissions": [
                    "home_assistant.access",
                    "home_assistant.integration_management",
                    "home_assistant.system_control",
                    "home_assistant.remote_control",
                ]
            },
        )
        login = self.client.post("/auth/login", json={"username": "systems", "password": "systems-pass"})
        session_token = login.json()["session_token"]

        target = self.client.post(
            "/home-assistant/system-targets",
            headers={"X-Jarvis-Session": session_token},
            json={"label": "Office PC", "target_kind": "pc", "host": "10.0.0.90", "allowed_actions": ["wake", "restart"]},
        )
        self.assertEqual(200, target.status_code)
        target_id = target.json()["target"]["id"]

        profiles = self.client.get("/home-assistant/system-target-profiles", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, profiles.status_code)
        self.assertIn("pc", profiles.json()["profiles"])

        action = self.client.post(
            f"/home-assistant/system-targets/{target_id}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "restart", "remote": True},
        )
        self.assertEqual(200, action.status_code)
        self.assertFalse(action.json()["executed"])

        request_id = action.json()["request"]["id"]
        confirm = self.client.post(
            f"/home-assistant/control-requests/{request_id}/confirm",
            headers={"X-Jarvis-Session": session_token},
            json={"confirmed": True},
        )
        self.assertEqual(200, confirm.status_code)
        self.assertTrue(confirm.json()["executed"])

        denied = self.client.post(
            f"/home-assistant/system-targets/{target_id}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "shutdown", "remote": True},
        )
        self.assertEqual(400, denied.status_code)

    def test_security_posture_and_expired_confirmations_are_exposed(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "secure", "role": "standard_user", "enabled": True, "password": "secure-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={
                "permissions": [
                    "home_assistant.access",
                    "home_assistant.integration_management",
                    "home_assistant.device_discovery",
                    "home_assistant.security_device_control",
                    "home_assistant.remote_control",
                ]
            },
        )
        login = self.client.post("/auth/login", json={"username": "secure", "password": "secure-pass"})
        session_token = login.json()["session_token"]

        candidate_id = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.91",
                "label": "Back Door",
                "suggested_type": "lock",
                "suggested_area": "garden",
            },
        ).json()["candidate"]["id"]
        entity_id = self.client.post(
            f"/home-assistant/discovery/candidates/{candidate_id}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "garden", "kind": "lock", "entity_id": "lock.backdoor"},
        ).json()["entity"]["entity_id"]
        action = self.client.post(
            f"/home-assistant/entities/{entity_id}/actions",
            headers={"X-Jarvis-Session": session_token},
            json={"action": "unlock", "value": "unlocked", "remote": True},
        )
        request_id = action.json()["request"]["id"]
        jarvisappv4.home_assistant_store.update_control_request(
            request_id,
            {"created_at": int(time.time()) - (jarvisappv4.home_assistant_service.confirmation_ttl_sec + 5)},
        )

        posture = self.client.get("/home-assistant/security-posture", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(200, posture.status_code)
        self.assertGreaterEqual(posture.json()["security"]["expired_confirmations"], 1)

        confirm = self.client.post(
            f"/home-assistant/control-requests/{request_id}/confirm",
            headers={"X-Jarvis-Session": session_token},
            json={"confirmed": True},
        )
        self.assertEqual(400, confirm.status_code)

    def test_remote_network_policy_blocks_remote_action_outside_allowed_cidrs(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        created = self.client.post(
            "/admin/users",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={"username": "netguard", "role": "standard_user", "enabled": True, "password": "netguard-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={
                "Authorization": f"Bearer {admin['token']}",
                "X-Jarvis-Role": "admin",
                "X-Jarvis-User-Id": admin["user_id"],
            },
            json={
                "permissions": [
                    "home_assistant.access",
                    "home_assistant.integration_management",
                    "home_assistant.device_discovery",
                    "home_assistant.security_device_control",
                    "home_assistant.remote_control",
                ]
            },
        )
        os.environ["JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS"] = "10.0.0.0/24"
        jarvisappv4.home_assistant_service = jarvisappv4.HomeAssistantService(
            store=jarvisappv4.home_assistant_store,
            client=jarvisappv4.home_assistant_client,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
        )
        login = self.client.post("/auth/login", json={"username": "netguard", "password": "netguard-pass"})
        session_token = login.json()["session_token"]

        candidate_id = self.client.post(
            "/home-assistant/discovery/candidates",
            headers={"X-Jarvis-Session": session_token},
            json={
                "ip_address": "10.0.0.93",
                "label": "Side Gate",
                "suggested_type": "lock",
                "suggested_area": "garden",
            },
        ).json()["candidate"]["id"]
        entity_id = self.client.post(
            f"/home-assistant/discovery/candidates/{candidate_id}/approve",
            headers={"X-Jarvis-Session": session_token},
            json={"area": "garden", "kind": "lock", "entity_id": "lock.sidegate"},
        ).json()["entity"]["entity_id"]

        denied = self.client.post(
            f"/home-assistant/entities/{entity_id}/actions",
            headers={"X-Jarvis-Session": session_token, "X-Forwarded-For": "172.16.10.5"},
            json={"action": "unlock", "value": "unlocked", "remote": True},
        )
        self.assertEqual(403, denied.status_code)

        posture = self.client.get("/home-assistant/security-posture", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(["10.0.0.0/24"], posture.json()["security"]["remote_allowed_cidrs"])


if __name__ == "__main__":
    unittest.main()
