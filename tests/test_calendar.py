import io
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient

import jarvisappv4
from jarvis.authz import resolve_effective_permissions
from jarvis.calendar.client import CalDavClient, CalDavConnectionError
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
        self.delete_calls: list[dict] = []
        self.put_calls: list[dict] = []
        self.fail_put = False
        self.fail_list_events = False
        self.connected = True

    def list_events(self, start, end):
        if self.fail_list_events:
            raise CalDavConnectionError("simulated connection failure")
        return list(self.events)

    def put_event(self, event: dict, *, href: str | None = None) -> str | None:
        self.put_calls.append({**event, "href": href})
        if self.fail_put:
            return None
        self.events.append({**event, "start": event["start"], "end": event["end"]})
        return href or f"https://caldav.example/cal/{event['uid']}.ics"

    def delete_event(self, uid: str, *, href: str | None = None) -> bool:
        self.deleted.append(uid)
        self.delete_calls.append({"uid": uid, "href": href})
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

    def test_replace_synced_events_preserves_href_and_etag(self):
        synced = self.store.replace_synced_events("u1", [
            {"uid": "remote1", "title": "Remote", "start": 500, "end": 600, "href": "/cal/opaque-name-123.ics", "etag": '"abc"'},
        ])
        self.assertEqual("/cal/opaque-name-123.ics", synced[0]["href"])
        self.assertEqual('"abc"', synced[0]["etag"])
        stored = self.store.list_events("u1")[0]
        self.assertEqual("/cal/opaque-name-123.ics", stored["href"])

    def test_store_self_heals_on_corrupt_file(self):
        path = os.environ["JARVIS_CALENDAR_STORE_PATH"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{not valid json")
        store = CalendarEventStore()
        self.assertEqual([], store.list_events("u1"))


def _multistatus(*responses: str) -> bytes:
    body = '<?xml version="1.0" encoding="utf-8"?>\n'
    body += '<D:multistatus xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">\n'
    body += "\n".join(responses)
    body += "\n</D:multistatus>"
    return body.encode("utf-8")


def _resourcetype_response(href: str, *, is_calendar: bool) -> str:
    marker = "<D:collection/><C:calendar/>" if is_calendar else "<D:collection/>"
    return f"""<D:response>
  <D:href>{href}</D:href>
  <D:propstat><D:prop><D:resourcetype>{marker}</D:resourcetype></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>
</D:response>"""


def _principal_response(href: str) -> str:
    return f"""<D:response>
  <D:href>/</D:href>
  <D:propstat><D:prop><D:current-user-principal><D:href>{href}</D:href></D:current-user-principal></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>
</D:response>"""


def _home_set_response(href: str) -> str:
    return f"""<D:response>
  <D:href>/principal/</D:href>
  <D:propstat><D:prop><C:calendar-home-set><D:href>{href}</D:href></C:calendar-home-set></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>
</D:response>"""


_ICS_EVENT = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Test//EN
BEGIN:VEVENT
UID:{uid}
SUMMARY:{summary}
DTSTART:20260801T090000Z
DTEND:20260801T100000Z
DTSTAMP:20260801T080000Z
END:VEVENT
END:VCALENDAR"""


def _report_response(href: str, uid: str, summary: str) -> str:
    ics = _ICS_EVENT.format(uid=uid, summary=summary)
    return f"""<D:response>
  <D:href>{href}</D:href>
  <D:propstat><D:prop><D:getetag>"etag-{uid}"</D:getetag><C:calendar-data>{ics}</C:calendar-data></D:prop><D:status>HTTP/1.1 200 OK</D:status></D:propstat>
</D:response>"""


class _FakeCalDavResponse:
    def __init__(self, status: int, body: bytes, url: str):
        self.status = status
        self._body = body
        self._url = url

    def read(self):
        return self._body

    def geturl(self):
        return self._url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _http_error(url: str, code: int, *, location: str | None = None, body: bytes = b"") -> HTTPError:
    hdrs = {"Location": location} if location else {}
    return HTTPError(url, code, "error", hdrs, io.BytesIO(body))


class CalDavClientTests(unittest.TestCase):
    def _client(self, base_url="https://caldav.icloud.com") -> CalDavClient:
        return CalDavClient(base_url, "user@example.com", "app-specific-pw")

    def test_redirect_followed_on_propfind(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            if req.full_url == "https://caldav.icloud.com":
                raise _http_error(req.full_url, 302, location="https://p01-caldav.icloud.com/")
            if req.full_url == "https://p01-caldav.icloud.com/":
                body = _multistatus(_resourcetype_response("/calendars/home/", is_calendar=True))
                return _FakeCalDavResponse(207, body, req.full_url)
            raise AssertionError(f"unexpected request to {req.full_url}")

        client = self._client()
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            urls = client._discover_calendar_urls()
        self.assertEqual(["https://p01-caldav.icloud.com/calendars/home/"], urls)
        self.assertEqual(2, len(calls))

    def test_max_redirects_raises(self):
        def fake_urlopen(req, timeout=None):
            raise _http_error(req.full_url, 302, location=req.full_url)

        client = self._client()
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(CalDavConnectionError):
                client._discover_calendar_urls()

    def test_auth_failure_raises_immediately(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            raise _http_error(req.full_url, 401)

        client = self._client()
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(CalDavConnectionError) as ctx:
                client._discover_calendar_urls()
        self.assertIn("authentication failed", str(ctx.exception))
        self.assertEqual(1, len(calls))

    def test_direct_url_skips_full_discovery(self):
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.full_url)
            body = _multistatus(_resourcetype_response("/cal/home/", is_calendar=True))
            return _FakeCalDavResponse(207, body, req.full_url)

        client = self._client(base_url="https://dav.example.com/cal/home/")
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            urls = client._discover_calendar_urls()
        self.assertEqual(["https://dav.example.com/cal/home/"], urls)
        self.assertEqual(1, len(calls))

    def test_full_discovery_chain_via_well_known(self):
        def fake_urlopen(req, timeout=None):
            url = req.full_url
            body_bytes = req.data or b""
            if url == "https://caldav.icloud.com" and b"resourcetype" in body_bytes:
                raise _http_error(url, 404)
            if url == "https://caldav.icloud.com" and b"current-user-principal" in body_bytes:
                raise _http_error(url, 404)
            if url == "https://caldav.icloud.com/.well-known/caldav":
                return _FakeCalDavResponse(200, b"", "https://p01-caldav.icloud.com/")
            if url == "https://p01-caldav.icloud.com/" and b"current-user-principal" in body_bytes:
                body = _multistatus(_principal_response("/1234/principal/"))
                return _FakeCalDavResponse(207, body, url)
            if url == "https://p01-caldav.icloud.com/1234/principal/":
                body = _multistatus(_home_set_response("/1234/calendars/"))
                return _FakeCalDavResponse(207, body, url)
            if url == "https://p01-caldav.icloud.com/1234/calendars/":
                body = _multistatus(
                    _resourcetype_response("/1234/calendars/", is_calendar=False),
                    _resourcetype_response("/1234/calendars/home/", is_calendar=True),
                    _resourcetype_response("/1234/calendars/work/", is_calendar=True),
                )
                return _FakeCalDavResponse(207, body, url)
            raise AssertionError(f"unexpected request to {url} body={body_bytes!r}")

        client = self._client()
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            urls = client._discover_calendar_urls()
        self.assertEqual(
            {"https://p01-caldav.icloud.com/1234/calendars/home/", "https://p01-caldav.icloud.com/1234/calendars/work/"},
            set(urls),
        )

    def test_list_events_aggregates_across_multiple_calendars(self):
        def fake_urlopen(req, timeout=None):
            url = req.full_url
            if req.get_method() == "PROPFIND":
                body = _multistatus(
                    _resourcetype_response("/cal/home/", is_calendar=True),
                    _resourcetype_response("/cal/work/", is_calendar=True),
                )
                return _FakeCalDavResponse(207, body, url)
            if req.get_method() == "REPORT" and url == "https://dav.example.com/cal/home/":
                body = _multistatus(_report_response("/cal/home/evt1.ics", "evt-1", "Home event"))
                return _FakeCalDavResponse(207, body, url)
            if req.get_method() == "REPORT" and url == "https://dav.example.com/cal/work/":
                body = _multistatus(_report_response("/cal/work/evt2.ics", "evt-2", "Work event"))
                return _FakeCalDavResponse(207, body, url)
            raise AssertionError(f"unexpected {req.get_method()} to {url}")

        client = self._client(base_url="https://dav.example.com/cal/")
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            events = client.list_events(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 12, 31, tzinfo=timezone.utc))
        self.assertEqual({"Home event", "Work event"}, {e["title"] for e in events})

    def test_list_events_raises_on_report_failure(self):
        def fake_urlopen(req, timeout=None):
            if req.get_method() == "PROPFIND":
                body = _multistatus(_resourcetype_response("/cal/home/", is_calendar=True))
                return _FakeCalDavResponse(207, body, req.full_url)
            return _FakeCalDavResponse(500, b"", req.full_url)

        client = self._client(base_url="https://dav.example.com/cal/home/")
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            with self.assertRaises(CalDavConnectionError):
                client.list_events(datetime(2026, 1, 1, tzinfo=timezone.utc), datetime(2026, 12, 31, tzinfo=timezone.utc))

    def test_put_event_returns_false_on_connection_failure(self):
        def fake_urlopen(req, timeout=None):
            raise _http_error(req.full_url, 401)

        client = self._client()
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            ok = client.put_event({"uid": "evt-1", "title": "X", "start": 1000, "end": 2000})
        self.assertFalse(ok)

    def test_delete_event_returns_false_on_connection_failure(self):
        def fake_urlopen(req, timeout=None):
            raise _http_error(req.full_url, 401)

        client = self._client()
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            ok = client.delete_event("evt-1")
        self.assertFalse(ok)

    def test_put_event_writes_to_explicit_href_not_guessed_url(self):
        requested_urls = []

        def fake_urlopen(req, timeout=None):
            requested_urls.append((req.get_method(), req.full_url))
            if req.get_method() == "PROPFIND":
                body = _multistatus(_resourcetype_response("/cal/home/", is_calendar=True))
                return _FakeCalDavResponse(207, body, req.full_url)
            return _FakeCalDavResponse(204, b"", req.full_url)

        client = self._client(base_url="https://dav.example.com/cal/home/")
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            target = client.put_event({"uid": "opaque-uid", "title": "X", "start": 1000, "end": 2000}, href="/cal/home/apple-opaque-name.ics")

        self.assertEqual("https://dav.example.com/cal/home/apple-opaque-name.ics", target)
        put_calls = [(m, u) for m, u in requested_urls if m == "PUT"]
        self.assertEqual([("PUT", "https://dav.example.com/cal/home/apple-opaque-name.ics")], put_calls)

    def test_delete_event_uses_explicit_href_not_guessed_url(self):
        requested_urls = []

        def fake_urlopen(req, timeout=None):
            requested_urls.append((req.get_method(), req.full_url))
            if req.get_method() == "PROPFIND":
                body = _multistatus(_resourcetype_response("/cal/home/", is_calendar=True))
                return _FakeCalDavResponse(207, body, req.full_url)
            return _FakeCalDavResponse(204, b"", req.full_url)

        client = self._client(base_url="https://dav.example.com/cal/home/")
        with patch("jarvis.calendar.client.request.urlopen", side_effect=fake_urlopen):
            ok = client.delete_event("opaque-uid", href="/cal/home/apple-opaque-name.ics")

        self.assertTrue(ok)
        delete_calls = [(m, u) for m, u in requested_urls if m == "DELETE"]
        self.assertEqual([("DELETE", "https://dav.example.com/cal/home/apple-opaque-name.ics")], delete_calls)


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

    def test_update_event_succeeds_and_pushes_href(self):
        user = self._configured_user()
        created = self.service.create_event({"title": "Design review", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        event_id = created["event"]["id"]
        result = self.service.update_event(event_id, {"title": "Design review (moved)", "start": 3000, "end": 4000}, user_id=user["id"], role=user["role"])
        self.assertTrue(result["updated"])
        self.assertEqual("Design review (moved)", result["event"]["title"])
        self.assertEqual(3000, result["event"]["start"])
        self.assertEqual("calendar_event_updated", self.audit_probe.events[-1]["event"])
        # The update was pushed to the CalDAV client using the event's own href, not a fresh guess.
        last_put = self.fake_client.put_calls[-1]
        self.assertEqual(created["event"]["href"], last_put["href"])

    def test_update_event_conflict_blocks_without_force(self):
        user = self._configured_user()
        first = self.service.create_event({"title": "First", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        second = self.service.create_event({"title": "Second", "start": 5000, "end": 6000}, user_id=user["id"], role=user["role"])
        result = self.service.update_event(second["event"]["id"], {"title": "Second", "start": 1500, "end": 2500}, user_id=user["id"], role=user["role"])
        self.assertFalse(result["updated"])
        self.assertEqual(1, len(result["conflicts"]))
        self.assertEqual(first["event"]["id"], result["conflicts"][0]["id"])

    def test_update_event_conflict_can_be_forced(self):
        user = self._configured_user()
        self.service.create_event({"title": "First", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        second = self.service.create_event({"title": "Second", "start": 5000, "end": 6000}, user_id=user["id"], role=user["role"])
        result = self.service.update_event(second["event"]["id"], {"title": "Second", "start": 1500, "end": 2500}, user_id=user["id"], role=user["role"], force=True)
        self.assertTrue(result["updated"])

    def test_update_event_does_not_conflict_with_its_own_previous_time(self):
        user = self._configured_user()
        created = self.service.create_event({"title": "Standup", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        # Editing an event to keep (part of) its own original time range must not
        # be reported as conflicting with itself (find_overlapping excludes it).
        result = self.service.update_event(created["event"]["id"], {"title": "Standup (renamed)", "start": 1000, "end": 2000}, user_id=user["id"], role=user["role"])
        self.assertTrue(result["updated"])
        self.assertEqual(0, len(result["conflicts"]))

    def test_update_event_rejects_editing_other_users_event(self):
        alice = self._configured_user("alice3")
        created = self.service.create_event({"title": "Alice's event", "start": 1000, "end": 2000}, user_id=alice["id"], role=alice["role"])
        bob = self._configured_user("bob3")
        with self.assertRaises(LookupError):
            self.service.update_event(created["event"]["id"], {"title": "Hijacked", "start": 1000, "end": 2000}, user_id=bob["id"], role=bob["role"])

    def test_delete_event_uses_tracked_href_not_guessed_url(self):
        user = self._configured_user()
        self.fake_client.events = [{"uid": "remote-1", "title": "Remote", "start": 5000, "end": 6000, "href": "/cal/apple-opaque-name.ics"}]
        self.service.sync(user_id=user["id"], role=user["role"])
        events = self.service.list_events(user_id=user["id"], role=user["role"])["events"]
        event_id = events[0]["id"]
        self.service.delete_event(event_id, user_id=user["id"], role=user["role"])
        self.assertEqual(1, len(self.fake_client.delete_calls))
        self.assertEqual("/cal/apple-opaque-name.ics", self.fake_client.delete_calls[0]["href"])

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

    def test_set_credentials_rejects_when_connection_test_fails(self):
        user = self.user_store.create_user("dana", role="standard_user", enabled=True)
        self.permission_store.set_user_permissions(user["id"], ["calendar.read", "calendar.write"])
        self.fake_client.connected = False
        with self.assertRaises(CalDavConnectionError):
            self.service.set_credentials(
                {"url": "https://caldav.icloud.com", "username": "bad", "password": "wrong"},
                user_id=user["id"], role=user["role"],
            )
        self.assertIsNone(self.credential_store.get_credentials(user["id"], "calendar"))

    def test_set_credentials_does_not_overwrite_working_creds_on_failed_update(self):
        user = self._configured_user("erin")
        working = self.credential_store.get_credentials(user["id"], "calendar")
        self.fake_client.connected = False
        with self.assertRaises(CalDavConnectionError):
            self.service.set_credentials(
                {"url": "https://broken.example", "username": "x", "password": "y"},
                user_id=user["id"], role=user["role"],
            )
        self.assertEqual(working, self.credential_store.get_credentials(user["id"], "calendar"))

    def test_sync_raises_on_client_connection_error(self):
        user = self._configured_user("frank")
        self.fake_client.fail_list_events = True
        with self.assertRaises(CalDavConnectionError):
            self.service.sync(user_id=user["id"], role=user["role"])


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

        updated = self.client.put(f"/calendar/events/{event_id}", headers=headers, json={"title": "Kickoff (renamed)", "start": 1000, "end": 2000})
        self.assertEqual(200, updated.status_code)
        self.assertTrue(updated.json()["updated"])
        self.assertEqual("Kickoff (renamed)", updated.json()["event"]["title"])

        deleted = self.client.delete(f"/calendar/events/{event_id}", headers=headers)
        self.assertEqual(200, deleted.status_code)
        self.assertTrue(deleted.json()["deleted"])

    def test_update_conflict_returns_conflicts_without_force_via_api(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "calconflict", ["calendar.read", "calendar.write"])
        headers = {"X-Jarvis-Session": session_token}
        self.client.put("/calendar/credentials", headers=headers, json={"url": "https://caldav.example/cal", "username": "u", "password": "p"})

        first = self.client.post("/calendar/events", headers=headers, json={"title": "First", "start": 1000, "end": 2000}).json()
        second = self.client.post("/calendar/events", headers=headers, json={"title": "Second", "start": 5000, "end": 6000}).json()

        conflict = self.client.put(f"/calendar/events/{second['event']['id']}", headers=headers, json={"title": "Second", "start": 1500, "end": 2500})
        self.assertEqual(200, conflict.status_code)
        self.assertFalse(conflict.json()["updated"])
        self.assertEqual(1, len(conflict.json()["conflicts"]))

        forced = self.client.put(f"/calendar/events/{second['event']['id']}", headers=headers, json={"title": "Second", "start": 1500, "end": 2500, "force": True})
        self.assertEqual(200, forced.status_code)
        self.assertTrue(forced.json()["updated"])

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

    def test_set_credentials_returns_502_on_connection_failure(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "badcal", ["calendar.read", "calendar.write"])
        self.fake_client.connected = False
        response = self.client.put(
            "/calendar/credentials", headers={"X-Jarvis-Session": session_token},
            json={"url": "https://caldav.icloud.com", "username": "bad", "password": "wrong"},
        )
        self.assertEqual(502, response.status_code)

    def test_sync_returns_502_on_connection_failure(self):
        admin = self.client.post("/admin/login", json={"username": "admin", "password": "admin123"}).json()
        _, session_token = self._create_user_with_permissions(admin["token"], admin["user_id"], "syncfail", ["calendar.read", "calendar.write"])
        headers = {"X-Jarvis-Session": session_token}
        set_creds = self.client.put("/calendar/credentials", headers=headers, json={"url": "https://caldav.example/cal", "username": "u", "password": "p"})
        self.assertEqual(200, set_creds.status_code)
        self.fake_client.fail_list_events = True
        response = self.client.post("/calendar/sync", headers=headers)
        self.assertEqual(502, response.status_code)


if __name__ == "__main__":
    unittest.main()
