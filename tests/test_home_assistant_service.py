import tempfile
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from jarvis.authz import resolve_effective_permissions
from jarvis.group_store import GroupStore
from jarvis.home_assistant.client import HomeAssistantClient
from jarvis.home_assistant.discovery import build_discovery_candidate
from jarvis.home_assistant.service import HomeAssistantAccessError, HomeAssistantService
from jarvis.home_assistant.store import HomeAssistantStore
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import PermissionStore
from jarvis.user_store import UserStore


class _AuditLogProbe:
    def __init__(self):
        self.events = []

    def write(self, event: str, payload: dict):
        self.events.append({"event": event, **payload})


class HomeAssistantServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        import os

        os.environ["JARVIS_USER_STORE_PATH"] = f"{self.tmpdir.name}/users.json"
        os.environ["JARVIS_GROUP_STORE_PATH"] = f"{self.tmpdir.name}/groups.json"
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = f"{self.tmpdir.name}/memberships.json"
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = f"{self.tmpdir.name}/permissions.json"
        os.environ["JARVIS_HOME_ASSISTANT_STORE_PATH"] = f"{self.tmpdir.name}/home_assistant.json"
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
        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = HomeAssistantStore()
        self.client = HomeAssistantClient()
        self.audit_probe = _AuditLogProbe()
        self.service = HomeAssistantService(
            store=self.store,
            client=self.client,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=lambda role: role or "guest_restricted",
            audit_log=self.audit_probe,
        )

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_first_admin_receives_access_without_explicit_permission(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        policy = self.service.policy_snapshot(user_id=admin["id"], role=admin["role"])
        self.assertTrue(policy["access_granted"])
        self.assertEqual("first_global_admin", policy["access_reason"])

    def test_non_admin_requires_explicit_permission(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("alice", role="standard_user", enabled=True)
        with self.assertRaises(HomeAssistantAccessError):
            self.service.require_access(user_id=user["id"], role=user["role"])

        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        policy = self.service.require_access(user_id=user["id"], role=user["role"])
        self.assertTrue(policy["access_granted"])
        self.assertEqual("explicit_permission", policy["access_reason"])

    def test_discovery_candidate_requires_discovery_permission(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("alice", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        with self.assertRaises(HomeAssistantAccessError):
            self.service.list_discovery_candidates(user_id=user["id"], role=user["role"])

        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access", "home_assistant.device_discovery"])
        candidate = build_discovery_candidate(
            source="manual",
            ip_address="10.0.0.12",
            label="New Lamp",
            suggested_type="light",
            suggested_area="office",
        )
        response = self.service.create_discovery_candidate(candidate, user_id=user["id"], role=user["role"])
        self.assertEqual("New Lamp", response["candidate"]["label"])

    def test_group_based_permissions_unlock_review_and_approval_flows(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("bob", role="standard_user", enabled=True)
        group = self.group_store.create_group("home-ops")
        self.membership_store.add_membership(user["id"], group["id"])
        self.permission_store.set_group_permissions(
            group["id"],
            [
                "home_assistant.access",
                "home_assistant.device_discovery",
                "home_assistant.integration_management",
            ],
        )

        candidate = build_discovery_candidate(
            source="manual",
            ip_address="10.0.0.33",
            label="Hall Sensor",
            suggested_type="sensor",
            suggested_area="hallway",
        )
        created = self.service.create_discovery_candidate(candidate, user_id=user["id"], role=user["role"])
        approved = self.service.approve_discovery_candidate(
            created["candidate"]["id"],
            {"area": "hallway", "kind": "sensor"},
            user_id=user["id"],
            role=user["role"],
        )
        self.assertEqual("approved", approved["candidate"]["approval_status"])
        self.assertEqual("managed", approved["entity"]["onboarding_status"])

    def test_shopping_list_is_low_risk_but_still_requires_access(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("charlie", role="standard_user", enabled=True)

        with self.assertRaises(HomeAssistantAccessError):
            self.service.add_shopping_list_item({"title": "Tomatoes"}, user_id=user["id"], role=user["role"])

        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        created = self.service.add_shopping_list_item({"title": "Tomatoes"}, user_id=user["id"], role=user["role"])
        listed = self.service.list_shopping_list_items(user_id=user["id"], role=user["role"])
        self.assertEqual("Tomatoes", created["item"]["title"])
        self.assertEqual(1, len(listed["items"]))

    def test_calendar_and_inbox_are_low_risk_but_access_scoped(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("karen", role="standard_user", enabled=True)

        with self.assertRaises(HomeAssistantAccessError):
            self.service.add_calendar_item({"title": "Dinner", "starts_at": "2026-03-18T18:00:00Z"}, user_id=user["id"], role=user["role"])

        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        calendar = self.service.add_calendar_item(
            {"title": "Dinner", "starts_at": "2026-03-18T18:00:00Z", "ends_at": "2026-03-18T19:00:00Z"},
            user_id=user["id"],
            role=user["role"],
        )
        inbox = self.service.add_inbox_item(
            {"subject": "Package update", "from_label": "Store", "summary": "Delivery tomorrow"},
            user_id=user["id"],
            role=user["role"],
        )
        listed_calendar = self.service.list_calendar_items(user_id=user["id"], role=user["role"])
        listed_inbox = self.service.list_inbox_items(user_id=user["id"], role=user["role"])
        self.assertEqual("Dinner", calendar["item"]["title"])
        self.assertEqual("Package update", inbox["item"]["subject"])
        self.assertEqual(1, len(listed_calendar["items"]))
        self.assertEqual(1, len(listed_inbox["items"]))

    def test_calendar_and_inbox_sync_use_client_boundary(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("lisa", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        self.client.fetch_calendar_items = lambda: [
            {
                "id": "cal-1",
                "title": "Morning check",
                "starts_at": "2026-03-19T08:00:00Z",
                "source": "seed",
            }
        ]
        self.client.fetch_inbox_items = lambda: [
            {
                "id": "mail-1",
                "subject": "Door alert",
                "from_label": "Security",
                "summary": "Front door opened",
                "source": "seed",
            }
        ]

        calendar_sync = self.service.sync_calendar_items(user_id=user["id"], role=user["role"])
        inbox_sync = self.service.sync_inbox_items(user_id=user["id"], role=user["role"])
        self.assertEqual(1, calendar_sync["sync"]["synced_count"])
        self.assertEqual("Morning check", calendar_sync["items"][0]["title"])
        self.assertEqual(1, inbox_sync["sync"]["synced_count"])
        self.assertEqual("Door alert", inbox_sync["items"][0]["subject"])

    def test_calendar_and_inbox_actions_are_low_risk_and_audited(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("maya", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])

        calendar = self.service.add_calendar_item(
            {"title": "Garden check", "starts_at": "2026-03-22T09:00:00Z"},
            user_id=user["id"],
            role=user["role"],
        )["item"]
        inbox = self.service.add_inbox_item(
            {"subject": "Pump alert", "from_label": "Basement"},
            user_id=user["id"],
            role=user["role"],
        )["item"]

        updated_calendar = self.service.act_on_calendar_item(
            calendar["id"],
            {"action": "mark_done"},
            user_id=user["id"],
            role=user["role"],
        )
        updated_inbox = self.service.act_on_inbox_item(
            inbox["id"],
            {"action": "archive"},
            user_id=user["id"],
            role=user["role"],
        )

        self.assertEqual("completed", updated_calendar["item"]["status"])
        self.assertEqual("archived", updated_inbox["item"]["status"])
        events = [item["event"] for item in self.audit_probe.events]
        self.assertIn("ha_calendar_item_updated", events)
        self.assertIn("ha_inbox_item_updated", events)

    def test_calendar_and_inbox_client_can_load_from_file_provider(self):
        import json
        import os

        calendar_path = os.path.join(self.tmpdir.name, "calendar.json")
        inbox_path = os.path.join(self.tmpdir.name, "inbox.json")
        with open(calendar_path, "w", encoding="utf-8") as handle:
            json.dump([{"id": "cal-file-1", "title": "Generator test", "starts_at": "2026-03-21T07:00:00Z"}], handle)
        with open(inbox_path, "w", encoding="utf-8") as handle:
            json.dump([{"id": "inbox-file-1", "subject": "Power alert", "from_label": "UPS"}], handle)

        os.environ["JARVIS_HOME_ASSISTANT_CALENDAR_FILE"] = calendar_path
        os.environ["JARVIS_HOME_ASSISTANT_INBOX_FILE"] = inbox_path
        client = HomeAssistantClient()

        self.assertEqual("file", client.config_summary()["calendar_provider"])
        self.assertEqual("file", client.config_summary()["inbox_provider"])
        self.assertEqual("Generator test", client.fetch_calendar_items()[0]["title"])
        self.assertEqual("Power alert", client.fetch_inbox_items()[0]["subject"])

    def test_calendar_and_inbox_client_can_load_from_http_provider(self):
        import json
        import os

        calendar_payload = [{"id": "cal-http-1", "title": "HTTP event", "starts_at": "2026-03-23T10:00:00Z"}]
        inbox_payload = [{"id": "inbox-http-1", "subject": "HTTP inbox", "from_label": "Remote"}]

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
            client = HomeAssistantClient()
            self.assertEqual("http", client.config_summary()["calendar_provider"])
            self.assertEqual("http", client.config_summary()["inbox_provider"])
            self.assertEqual("HTTP event", client.fetch_calendar_items()[0]["title"])
            self.assertEqual("HTTP inbox", client.fetch_inbox_items()[0]["subject"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_calendar_and_inbox_write_back_can_sync_to_http_provider(self):
        import json
        import os

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
                self.wfile.write(json.dumps({"accepted": True, "path": self.path}).encode("utf-8"))

            def log_message(self, format, *args):  # noqa: A003
                return

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            os.environ["JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL"] = f"http://127.0.0.1:{server.server_port}/calendar-write"
            os.environ["JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL"] = f"http://127.0.0.1:{server.server_port}/inbox-write"
            client = HomeAssistantClient()
            service = HomeAssistantService(
                store=self.store,
                client=client,
                user_store=self.user_store,
                membership_store=self.membership_store,
                permission_store=self.permission_store,
                resolve_effective_permissions=resolve_effective_permissions,
                normalize_role=lambda role: role or "guest_restricted",
                audit_log=self.audit_probe,
            )
            self.user_store.create_user("owner", role="admin", enabled=True)
            user = self.user_store.create_user("nina", role="standard_user", enabled=True)
            self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])

            calendar = service.add_calendar_item(
                {"title": "Provider write event", "starts_at": "2026-03-25T10:00:00Z"},
                user_id=user["id"],
                role=user["role"],
            )
            inbox = service.add_inbox_item(
                {"subject": "Provider write inbox", "from_label": "Remote"},
                user_id=user["id"],
                role=user["role"],
            )

            self.assertEqual("synced", calendar["item"]["metadata"]["provider_write"])
            self.assertEqual("synced", inbox["item"]["metadata"]["provider_write"])
            self.assertEqual(2, len(writes))
            self.assertEqual("/calendar-write", writes[0][0])
            self.assertEqual("/inbox-write", writes[1][0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_calendar_and_inbox_actions_can_write_back_to_http_provider(self):
        import json
        import os

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
            client = HomeAssistantClient()
            service = HomeAssistantService(
                store=self.store,
                client=client,
                user_store=self.user_store,
                membership_store=self.membership_store,
                permission_store=self.permission_store,
                resolve_effective_permissions=resolve_effective_permissions,
                normalize_role=lambda role: role or "guest_restricted",
                audit_log=self.audit_probe,
            )
            self.user_store.create_user("owner", role="admin", enabled=True)
            user = self.user_store.create_user("olivia", role="standard_user", enabled=True)
            self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])

            calendar = service.add_calendar_item(
                {"title": "Action sync event", "starts_at": "2026-03-26T10:00:00Z"},
                user_id=user["id"],
                role=user["role"],
            )["item"]
            inbox = service.add_inbox_item(
                {"subject": "Action sync inbox", "from_label": "Remote"},
                user_id=user["id"],
                role=user["role"],
            )["item"]

            writes.clear()
            updated_calendar = service.act_on_calendar_item(
                calendar["id"],
                {"action": "reschedule_plus_1d"},
                user_id=user["id"],
                role=user["role"],
            )
            updated_inbox = service.act_on_inbox_item(
                inbox["id"],
                {"action": "mark_read"},
                user_id=user["id"],
                role=user["role"],
            )

            self.assertEqual("synced", updated_calendar["item"]["metadata"]["provider_write"])
            self.assertEqual("reschedule_plus_1d", updated_calendar["item"]["metadata"]["provider_last_action"])
            self.assertEqual("synced", updated_inbox["item"]["metadata"]["provider_write"])
            self.assertEqual("mark_read", updated_inbox["item"]["metadata"]["provider_last_action"])
            self.assertEqual(2, len(writes))
            self.assertEqual("update", writes[0][1]["mode"])
            self.assertEqual("update", writes[1][1]["mode"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_basic_device_action_executes_for_device_control_permission(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("dana", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access", "home_assistant.device_control"])
        self.store.add_managed_entity(
            {
                "entity_id": "entity.light.office",
                "label": "Office Light",
                "kind": "light",
                "area": "office",
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "medium",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )

        response = self.service.request_entity_action(
            "entity.light.office",
            {"action": "turn_on", "value": "on"},
            user_id=user["id"],
            role=user["role"],
        )
        self.assertTrue(response["executed"])
        self.assertEqual("executed", response["request"]["status"])

    def test_security_device_action_requires_confirmation_and_security_permission(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("erin", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(
            user["id"],
            ["home_assistant.access", "home_assistant.security_device_control", "home_assistant.remote_control"],
        )
        self.store.add_managed_entity(
            {
                "entity_id": "entity.lock.frontdoor",
                "label": "Front Door",
                "kind": "lock",
                "area": "entry",
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "high",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )

        request = self.service.request_entity_action(
            "entity.lock.frontdoor",
            {"action": "unlock", "value": "unlocked", "remote": True},
            user_id=user["id"],
            role=user["role"],
        )
        self.assertFalse(request["executed"])
        self.assertEqual("pending_confirmation", request["request"]["status"])

        confirmed = self.service.confirm_control_request(
            request["request"]["id"],
            {"confirmed": True},
            user_id=user["id"],
            role=user["role"],
        )
        self.assertTrue(confirmed["executed"])
        self.assertEqual("executed", confirmed["request"]["status"])

    def test_remote_action_requires_remote_control_capability(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("grace", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access", "home_assistant.security_device_control"])
        self.store.add_managed_entity(
            {
                "entity_id": "lock.side",
                "label": "Side Door",
                "kind": "lock",
                "area": "garage",
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "high",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )
        with self.assertRaises(HomeAssistantAccessError):
            self.service.request_entity_action(
                "lock.side",
                {"action": "unlock", "value": "unlocked", "remote": True},
                user_id=user["id"],
                role=user["role"],
            )

    def test_system_targets_require_preapproved_actions_and_confirmation(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("mike", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(
            user["id"],
            [
                "home_assistant.access",
                "home_assistant.integration_management",
                "home_assistant.system_control",
                "home_assistant.remote_control",
            ],
        )
        created = self.service.create_system_target(
            {"label": "Lab PC", "target_kind": "pc", "host": "10.0.0.88", "allowed_actions": ["wake", "restart"]},
            user_id=user["id"],
            role=user["role"],
        )
        request = self.service.request_system_target_action(
            created["target"]["id"],
            {"action": "restart", "remote": True},
            user_id=user["id"],
            role=user["role"],
        )
        self.assertFalse(request["executed"])
        self.assertEqual("pending_confirmation", request["request"]["status"])

        confirmed = self.service.confirm_control_request(
            request["request"]["id"],
            {"confirmed": True},
            user_id=user["id"],
            role=user["role"],
        )
        self.assertTrue(confirmed["executed"])
        self.assertEqual("last_action:restart", confirmed["target"]["status"])

        with self.assertRaises(ValueError):
            self.service.request_system_target_action(
                created["target"]["id"],
                {"action": "shutdown", "remote": True},
                user_id=user["id"],
                role=user["role"],
            )

    def test_expired_confirmation_requests_are_not_executable(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("nina", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(
            user["id"],
            ["home_assistant.access", "home_assistant.security_device_control", "home_assistant.remote_control"],
        )
        self.store.add_managed_entity(
            {
                "entity_id": "entity.lock.rear",
                "label": "Rear Door",
                "kind": "lock",
                "area": "garden",
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "high",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )
        request = self.service.request_entity_action(
            "entity.lock.rear",
            {"action": "unlock", "value": "unlocked", "remote": True},
            user_id=user["id"],
            role=user["role"],
        )
        self.store.update_control_request(
            request["request"]["id"],
            {"created_at": int(time.time()) - (self.service.confirmation_ttl_sec + 5)},
        )

        queue = self.service.list_control_requests(user_id=user["id"], role=user["role"])
        self.assertEqual("expired", queue["requests"][0]["status"])
        with self.assertRaises(ValueError):
            self.service.confirm_control_request(
                request["request"]["id"],
                {"confirmed": True},
                user_id=user["id"],
                role=user["role"],
            )

    def test_remote_network_policy_can_deny_remote_actions(self):
        import os

        os.environ["JARVIS_HOME_ASSISTANT_REMOTE_ALLOWED_CIDRS"] = "10.0.0.0/24"
        self.client = HomeAssistantClient()
        self.service = HomeAssistantService(
            store=self.store,
            client=self.client,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=lambda role: role or "guest_restricted",
        )
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("oliver", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(
            user["id"],
            ["home_assistant.access", "home_assistant.security_device_control", "home_assistant.remote_control"],
        )
        self.store.add_managed_entity(
            {
                "entity_id": "entity.lock.gate",
                "label": "Gate",
                "kind": "lock",
                "area": "entry",
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "high",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )
        with self.assertRaises(HomeAssistantAccessError):
            self.service.request_entity_action(
                "entity.lock.gate",
                {"action": "unlock", "value": "unlocked", "remote": True},
                user_id=user["id"],
                role=user["role"],
                client_ip="172.16.1.15",
            )

    def test_home_assistant_actions_write_audit_events_when_audit_log_present(self):
        audit = _AuditLogProbe()
        self.service.audit_log = audit
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("paul", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(
            user["id"],
            ["home_assistant.access", "home_assistant.device_discovery", "home_assistant.integration_management"],
        )
        created = self.service.create_discovery_candidate(
            {"ip_address": "10.0.0.44", "label": "Desk Lamp", "suggested_type": "light", "suggested_area": "office"},
            user_id=user["id"],
            role=user["role"],
        )
        self.service.approve_discovery_candidate(
            created["candidate"]["id"],
            {"area": "office", "kind": "light"},
            user_id=user["id"],
            role=user["role"],
        )
        event_names = [item["event"] for item in audit.events]
        self.assertIn("ha_discovery_candidate_created", event_names)
        self.assertIn("ha_discovery_candidate_approved", event_names)

    def test_entity_sync_updates_local_state_from_client_boundary(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("frank", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        self.store.add_managed_entity(
            {
                "entity_id": "light.office",
                "label": "Office Light",
                "kind": "light",
                "area": "office",
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "medium",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )
        self.client.fetch_states = lambda: [
            {
                "entity_id": "light.office",
                "state": "on",
                "attributes": {"friendly_name": "Office Light"},
            }
        ]

        synced = self.service.sync_managed_entities(user_id=user["id"], role=user["role"])
        self.assertEqual(1, synced["sync"]["synced_count"])
        self.assertEqual("on", synced["entities"][0]["state"])

    def test_health_status_reports_pending_and_unavailable_items(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("harry", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        self.store.add_managed_entity(
            {
                "entity_id": "sensor.office",
                "label": "Office Sensor",
                "kind": "sensor",
                "area": "office",
                "available": False,
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "medium",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )
        self.store.add_control_request({"id": "req-1", "status": "pending_confirmation"})
        self.store.add_calendar_item(
            {
                "id": "cal-deferred-1",
                "title": "Deferred provider write",
                "starts_at": "2026-03-28T10:00:00Z",
                "status": "scheduled",
                "source": "jarvis",
                "created_at": 1,
                "metadata": {"provider_write": "deferred", "provider_operation": "create"},
            }
        )
        health = self.service.health_status(user_id=user["id"], role=user["role"])
        self.assertEqual(1, health["health"]["unavailable_entities"])
        self.assertEqual(1, health["health"]["pending_confirmations"])
        self.assertEqual(1, health["health"]["deferred_provider_writes"])

    def test_device_profiles_and_area_summary_are_available(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("ivy", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        self.store.add_managed_entity(
            {
                "entity_id": "light.kitchen",
                "label": "Kitchen Light",
                "kind": "light",
                "area": "kitchen",
                "available": True,
                "control_mode": "approval_required",
                "integration_source": "home_assistant",
                "risk_level": "medium",
                "approval_status": "approved",
                "onboarding_status": "managed",
                "metadata": {},
            }
        )
        profiles = self.service.device_profiles(user_id=user["id"], role=user["role"])
        areas = self.service.area_summary(user_id=user["id"], role=user["role"])
        self.assertIn("light", profiles["profiles"])
        self.assertEqual("kitchen", areas["areas"][0]["area"])

    def test_automation_management_requires_explicit_capability(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("jane", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        with self.assertRaises(HomeAssistantAccessError):
            self.service.create_automation_rule(
                {"name": "Night lights", "target_area": "hallway"},
                user_id=user["id"],
                role=user["role"],
            )

        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access", "home_assistant.automation_management"])
        created = self.service.create_automation_rule(
            {"name": "Night lights", "target_area": "hallway", "action_summary": "Turn hallway lights on at 20:00"},
            user_id=user["id"],
            role=user["role"],
        )
        toggled = self.service.toggle_automation_rule(
            created["automation"]["id"],
            {"enabled": False},
            user_id=user["id"],
            role=user["role"],
        )
        listed = self.service.list_automation_rules(user_id=user["id"], role=user["role"])
        self.assertEqual("Night lights", created["automation"]["name"])
        self.assertFalse(toggled["automation"]["enabled"])
        self.assertEqual(1, len(listed["automations"]))

    def test_recovery_playbooks_are_permission_scoped_and_executable(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("kate", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access", "home_assistant.automation_management"])
        self.store.add_automation_rule(
            {
                "id": "auto-1",
                "name": "Hallway Night",
                "enabled": True,
                "target_area": "hallway",
                "trigger": "21:00",
                "action_summary": "Turn hallway lights on",
                "review_state": "approved",
                "risk_level": "medium",
                "created_at": 1,
                "updated_at": 1,
            }
        )
        playbooks = self.service.list_recovery_playbooks(user_id=user["id"], role=user["role"])
        playbook_ids = {item["id"] for item in playbooks["playbooks"]}
        self.assertIn("sync_entities", playbook_ids)
        self.assertIn("disable_automations", playbook_ids)

        executed = self.service.execute_recovery_playbook("disable_automations", user_id=user["id"], role=user["role"])
        self.assertEqual(1, executed["result"]["disabled_count"])
        self.assertFalse(self.store.get_automation_rule("auto-1")["enabled"])

    def test_retry_provider_writes_playbook_retries_deferred_items(self):
        self.user_store.create_user("owner", role="admin", enabled=True)
        user = self.user_store.create_user("peter", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["home_assistant.access"])
        self.store.add_calendar_item(
            {
                "id": "cal-retry-1",
                "title": "Retry event",
                "starts_at": "2026-03-29T10:00:00Z",
                "status": "scheduled",
                "source": "jarvis",
                "created_at": 1,
                "metadata": {"provider_write": "deferred", "provider_operation": "create"},
            }
        )
        self.store.add_inbox_item(
            {
                "id": "inbox-retry-1",
                "subject": "Retry inbox",
                "from_label": "Ops",
                "status": "unread",
                "received_at": 1,
                "source": "jarvis",
                "metadata": {"provider_write": "deferred", "provider_operation": "create"},
            }
        )
        self.client.create_calendar_item = lambda item: {"accepted": True, "id": item["id"]}
        self.client.create_inbox_item = lambda item: {"accepted": True, "id": item["id"]}

        executed = self.service.execute_recovery_playbook("retry_provider_writes", user_id=user["id"], role=user["role"])
        self.assertEqual(2, executed["result"]["retried_total"])
        self.assertEqual("synced", self.store.get_calendar_item("cal-retry-1")["metadata"]["provider_write"])
        self.assertEqual("synced", self.store.get_inbox_item("inbox-retry-1")["metadata"]["provider_write"])


if __name__ == "__main__":
    unittest.main()
