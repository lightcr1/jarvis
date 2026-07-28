import os
import tempfile
import unittest

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.authz import resolve_effective_permissions
from jarvis.calendar.service import CalendarAccessError, CalendarService
from jarvis.calendar.store import CalendarEventStore
from jarvis.group_store import GroupStore
from jarvis.integration_credentials import IntegrationCredentialStore
from jarvis.jarvis_engine import normalize_role
from jarvis.membership_store import MembershipStore
from jarvis.permission_store import KNOWN_PERMISSIONS
from jarvis.permission_store import PermissionStore
from jarvis.secret_crypto import generate_master_key
from jarvis.user_store import UserStore


class _AuditLogProbe:
    def __init__(self):
        self.events = []

    def write(self, event: str, payload: dict):
        self.events.append({"event": event, **payload})


class FakeCalDavClient:
    def __init__(self):
        self.events: list[dict] = []
        self.deleted: list[str] = []
        self.put_calls: list[dict] = []
        self.fail_put = False
        self.connected = True

    def list_events(self, start, end):
        return list(self.events)

    def put_event(self, event: dict) -> bool:
        self.put_calls.append(event)
        if self.fail_put:
            return False
        self.events.append({**event, "start": event["start"], "end": event["end"]})
        return True

    def delete_event(self, uid: str) -> bool:
        self.deleted.append(uid)
        return True

    def test_connection(self) -> bool:
        return self.connected


class CalendarStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        os.environ["JARVIS_CALENDAR_STORE_PATH"] = os.path.join(self.tmpdir.name, "calendar.json")
        self.store = CalendarEventStore()

    def tearDown(self):
        os.environ.pop("JARVIS_CALENDAR_STORE_PATH", None)
        self.tmpdir.cleanup()

    def test_known_permissions_include_calendar_tuple(self):
        self.assertIn("calendar.read", KNOWN_PERMISSIONS)
        self.assertIn("calendar.write", KNOWN_PERMISSIONS)

    def test_add_list_update_delete(self):
        event = self.store.add_event({"user_id": "u1", "uid": "e1", "title": "Standup", "start": 1000, "end": 2000, "source": "caldav"})
        self.assertEqual(1, len(self.store.list_events("u1")))
        self.assertEqual(0, len(self.store.list_events("u2")))
        updated = self.store.update_event(event["id"], {"title": "Standup (moved)"})
        self.assertEqual("Standup (moved)", updated["title"])
        self.assertTrue(self.store.delete_event(event["id"]))
        self.assertFalse(self.store.delete_event(event["id"]))

    def test_find_overlapping(self):
        self.store.add_event({"user_id": "u1", "uid": "e1", "title": "A", "start": 1000, "end": 2000})
        overlapping = self.store.find_overlapping("u1", 1500, 2500)
        self.assertEqual(1, len(overlapping))
        non_overlapping = self.store.find_overlapping("u1", 3000, 4000)
        self.assertEqual(0, len(non_overlapping))

    def test_replace_synced_events_keeps_local_events(self):
        self.store.add_event({"user_id": "u1", "uid": "local1", "title": "Local only", "start": 100, "end": 200, "source": "local"})
        synced = self.store.replace_synced_events("u1", [{"uid": "remote1", "title": "Remote", "start": 500, "end": 600}])
        self.assertEqual(1, len(synced))
        all_events = self.store.list_events("u1")
        self.assertEqual(2, len(all_events))

    def test_store_self_heals_on_corrupt_file(self):
        path = os.environ["JARVIS_CALENDAR_STORE_PATH"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        store = CalendarEventStore()
        self.assertEqual([], store.list_events("u1"))


class CalendarServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_CALENDAR_STORE_PATH"] = os.path.join(base, "calendar.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")

        self.user_store = UserStore()
        self.group_store = GroupStore()
        self.membership_store = MembershipStore()
        self.permission_store = PermissionStore()
        self.store = CalendarEventStore()
        self.credential_store = IntegrationCredentialStore()
        self.audit_probe = _AuditLogProbe()
        self.fake_client = FakeCalDavClient()
        self.service = CalendarService(
            store=self.store,
            credential_store=self.credential_store,
            user_store=self.user_store,
            membership_store=self.membership_store,
            permission_store=self.permission_store,
            resolve_effective_permissions=resolve_effective_permissions,
            normalize_role=normalize_role,
            audit_log=self.audit_probe,
            client_factory=lambda creds: self.fake_client,
        )

    def tearDown(self):
        for key in ("JARVIS_EMERGENCY_STOP", "JARVIS_SECRET_KEY", "JARVIS_INTEGRATION_CREDENTIALS_PATH"):
            os.environ.pop(key, None)
        self.tmpdir.cleanup()

    def _configured_user(self, username="alice", perms=("calendar.read", "calendar.write")):
        user = self.user_store.create_user(username, role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], list(perms))
        self.service.set_credentials({"url": "https://caldav.example/cal", "username": "cal-user", "password": "pw"}, user_id=user["id"], role=user["role"])
        return user

    def test_standard_user_denied_without_permission(self):
        user = self.user_store.create_user("bob", role="standard_user", enabled=True)
        with self.assertRaises(CalendarAccessError):
            self.service.list_events(user_id=user["id"], role=user["role"])

    def test_create_event_without_credentials_raises_lookup_error(self):
        user = self.user_store.create_user("carol", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["calendar.read", "calendar.write"])
        with self.assertRaises(LookupError):
            self.service.create_event({"title": "Meeting", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])

    def test_create_event_succeeds_and_pushes_to_client(self):
        user = self._configured_user()
        result = self.service.create_event({"title": "Design review", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        self.assertTrue(result["created"])
        self.assertEqual("Design review", result["event"]["title"])
        self.assertEqual(1, len(self.fake_client.put_calls))
        self.assertEqual("calendar_event_created", self.audit_probe.events[-1]["event"])

    def test_conflict_detection_blocks_creation_without_force(self):
        user = self._configured_user()
        self.service.create_event({"title": "First", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        result = self.service.create_event({"title": "Overlaps", "start": 1500, "end": 2500}, user_id=user["id"], role=user["role"])
        self.assertFalse(result["created"])
        self.assertEqual(1, len(result["conflicts"]))
        # Only the first event was pushed to the CalDAV server.
        self.assertEqual(1, len(self.fake_client.put_calls))

    def test_conflict_can_be_forced(self):
        user = self._configured_user()
        self.service.create_event({"title": "First", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        result = self.service.create_event({"title": "Overlaps", "start": 1500, "end": 2500}, user_id=user["id"], role=user["role"], force=True)
        self.assertTrue(result["created"])
        self.assertEqual(1, len(result["conflicts"]))

    def test_emergency_stop_blocks_create(self):
        user = self._configured_user()
        os.environ["JARVIS_EMERGENCY_STOP"] = "1"
        with self.assertRaises(PermissionError):
            self.service.create_event({"title": "Blocked", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])

    def test_users_isolated_and_admin_can_delete_any(self):
        admin = self.user_store.create_user("owner", role="admin", enabled=True)
        self.service.set_credentials({"url": "https://caldav.example/cal", "username": "u", "password": "p"}, user_id=admin["id"], role=admin["role"])
        alice = self._configured_user("alice2")
        created = self.service.create_event({"title": "Alice's event", "start": 1000, "end": 2000}, user_id=alice["id"], role=alice["role"])
        event_id = created["event"]["id"]

        bob = self._configured_user("bob2")
        with self.assertRaises(LookupError):
            self.service.delete_event(event_id, user_id=bob["id"], role=bob["role"])

        admin_delete = self.service.delete_event(event_id, user_id=admin["id"], role=admin["role"])
        self.assertTrue(admin_delete["deleted"])

    def test_credentials_status_and_delete(self):
        user = self._configured_user()
        status = self.service.credentials_status(user_id=user["id"], role=user["role"])
        self.assertTrue(status["status"]["configured"])
        deleted = self.service.delete_credentials(user_id=user["id"], role=user["role"])
        self.assertTrue(deleted["deleted"])
        status_after = self.service.credentials_status(user_id=user["id"], role=user["role"])
        self.assertFalse(status_after["status"]["configured"])

    def test_sync_pulls_remote_events_into_store(self):
        user = self._configured_user()
        self.fake_client.events = [{"uid": "remote-1", "title": "Remote sync", "start": 5000, "end": 6000}]
        result = self.service.sync(user_id=user["id"], role=user["role"])
        self.assertEqual(1, result["synced_count"])
        events = self.service.list_events(user_id=user["id"], role=user["role"])["events"]
        self.assertEqual(1, len(events))
        self.assertEqual("Remote sync", events[0]["title"])

    def test_invalid_event_payload_rejected(self):
        user = self._configured_user()
        with self.assertRaises(ValueError):
            self.service.create_event({"title": "", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        with self.assertRaises(ValueError):
            self.service.create_event({"title": "Bad range", "start": 2000, "end": 1000}, user_id=user["id"], role=user["role"])


class CalendarApiTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        base = self.tmpdir.name
        os.environ["JARVIS_USER_STORE_PATH"] = os.path.join(base, "users.json")
        os.environ["JARVIS_GROUP_STORE_PATH"] = os.path.join(base, "groups.json")
        os.environ["JARVIS_MEMBERSHIP_STORE_PATH"] = os.path.join(base, "memberships.json")
        os.environ["JARVIS_PERMISSION_STORE_PATH"] = os.path.join(base, "permissions.json")
        os.environ["JARVIS_ADMIN_PASSWORD_STORE_PATH"] = os.path.join(base, "admin_passwords.json")
        os.environ["JARVIS_USER_PREFERENCES_PATH"] = os.path.join(base, "user_preferences.json")
        os.environ["JARVIS_CALENDAR_STORE_PATH"] = os.path.join(base, "calendar.json")
        os.environ["JARVIS_SECRET_KEY"] = generate_master_key()
        os.environ["JARVIS_INTEGRATION_CREDENTIALS_PATH"] = os.path.join(base, "creds.json")

        jarvisappv4.user_store = jarvisappv4.UserStore()
        jarvisappv4.group_store = jarvisappv4.GroupStore()
        jarvisappv4.membership_store = jarvisappv4.MembershipStore()
        jarvisappv4.permission_store = jarvisappv4.PermissionStore()
        jarvisappv4.admin_password_store = jarvisappv4.AdminPasswordStore()
        jarvisappv4.user_preferences_store = jarvisappv4.UserPreferencesStore()

        self.fake_client = FakeCalDavClient()
        jarvisappv4.calendar_event_store = jarvisappv4.CalendarEventStore()
        jarvisappv4.integration_credential_store = jarvisappv4.IntegrationCredentialStore()
        jarvisappv4.calendar_service = jarvisappv4.CalendarService(
            store=jarvisappv4.calendar_event_store,
            credential_store=jarvisappv4.integration_credential_store,
            user_store=jarvisappv4.user_store,
            membership_store=jarvisappv4.membership_store,
            permission_store=jarvisappv4.permission_store,
            resolve_effective_permissions=jarvisappv4.resolve_effective_permissions,
            normalize_role=jarvisappv4.normalize_role,
            audit_log=jarvisappv4.audit_log,
            client_factory=lambda creds: self.fake_client,
        )
        jarvisappv4._identity_tokens.clear()
        self.client = TestClient(jarvisappv4.app)

    def tearDown(self):
        os.environ.pop("JARVIS_SECRET_KEY", None)
        os.environ.pop("JARVIS_INTEGRATION_CREDENTIALS_PATH", None)
        self.tmpdir.cleanup()

    def _create_user_with_permissions(self, admin_token, admin_id, username, permissions):
        created = self.client.post(
            "/admin/users",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"username": username, "role": "standard_user", "enabled": True, "password": f"{username}-pass"},
        )
        user_id = created.json()["id"]
        self.client.put(
            f"/admin/permissions/users/{user_id}",
            headers={"Authorization": f"Bearer {admin_token}", "X-Jarvis-Role": "admin", "X-Jarvis-User-Id": admin_id},
            json={"permissions": permissions},
        )
        login = self.client.post("/auth/login", json={"username": username, "password": f"{username}-pass"})
        return user_id, login.json()["session_token"]

    def test_full_lifecycle_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "caluser", ["calendar.read", "calendar.write"])
        headers = {"X-Jarvis-Session": session_token}

        status = self.client.get("/calendar/credentials/status", headers=headers)
        self.assertEqual(200, status.status_code)
        self.assertFalse(status.json()["status"]["configured"])

        set_creds = self.client.put("/calendar/credentials", headers=headers, json={"url": "https://caldav.example/cal", "username": "u", "password": "p"})
        self.assertEqual(200, set_creds.status_code)

        created = self.client.post("/calendar/events", headers=headers, json={"title": "Kickoff", "start": 1000, "end": 2000})
        self.assertEqual(200, created.status_code)
        self.assertTrue(created.json()["created"])
        event_id = created.json()["event"]["id"]

        listed = self.client.get("/calendar/events", headers=headers)
        self.assertEqual(1, len(listed.json()["events"]))

        conflict = self.client.post("/calendar/events", headers=headers, json={"title": "Clash", "start": 1500, "end": 2500})
        self.assertEqual(200, conflict.status_code)
        self.assertFalse(conflict.json()["created"])

        deleted = self.client.delete(f"/calendar/events/{event_id}", headers=headers)
        self.assertEqual(200, deleted.status_code)
        self.assertTrue(deleted.json()["deleted"])

    def test_permission_denied_returns_403(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "noperm", [])
        denied = self.client.get("/calendar/events", headers={"X-Jarvis-Session": session_token})
        self.assertEqual(403, denied.status_code)

    def test_create_without_credentials_returns_409(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "nocalcreds", ["calendar.read", "calendar.write"])
        response = self.client.post("/calendar/events", headers={"X-Jarvis-Session": session_token}, json={"title": "X", "start": 1000, "end": 2000})
        self.assertEqual(409, response.status_code)


if __name__ == "__main__":
    unittest.main()
