from __future__ import annotations

import base64
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib import error, request
from urllib.parse import urljoin

from icalendar import Calendar as ICalendar
from icalendar import Event as ICalEvent

_REPORT_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<C:calendar-query xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop>
    <D:getetag/>
    <C:calendar-data/>
  </D:prop>
  <C:filter>
    <C:comp-filter name="VCALENDAR">
      <C:comp-filter name="VEVENT">
        <C:time-range start="{start}" end="{end}"/>
      </C:comp-filter>
    </C:comp-filter>
  </C:filter>
</C:calendar-query>"""

_PROPFIND_RESOURCETYPE_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:resourcetype/></D:prop>
</D:propfind>"""

_PROPFIND_CURRENT_USER_PRINCIPAL_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop><D:current-user-principal/></D:prop>
</D:propfind>"""

_PROPFIND_CALENDAR_HOME_SET_BODY = """<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
  <D:prop><C:calendar-home-set/></D:prop>
</D:propfind>"""

_MAX_REDIRECTS = 5
_REDIRECT_CODES = (301, 302, 303, 307, 308)
_DISCOVERY_BUDGET_SEC = 7.0


class CalDavConnectionError(RuntimeError):
    pass


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _to_ical_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _as_datetime(value) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if hasattr(value, "isoformat"):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    return None


def parse_ics_event(ics_text: str, *, href: str = "", etag: str = "") -> dict | None:
    try:
        cal = ICalendar.from_ical(ics_text)
    except (ValueError, IndexError):
        return None
    for component in cal.walk("VEVENT"):
        start = _as_datetime(component.get("dtstart").dt) if component.get("dtstart") else None
        end = _as_datetime(component.get("dtend").dt) if component.get("dtend") else start
        if start is None:
            continue
        return {
            "uid": str(component.get("uid") or uuid.uuid4().hex),
            "title": str(component.get("summary") or "(untitled)"),
            "description": str(component.get("description") or ""),
            "location": str(component.get("location") or ""),
            "start": int(start.timestamp()),
            "end": int((end or start).timestamp()),
            "href": href,
            "etag": etag,
        }
    return None


def build_ics(event: dict) -> bytes:
    cal = ICalendar()
    cal.add("prodid", "-//JARVIS//Calendar//EN")
    cal.add("version", "2.0")
    vevent = ICalEvent()
    vevent.add("uid", event["uid"])
    vevent.add("summary", event.get("title", ""))
    vevent.add("dtstart", datetime.fromtimestamp(event["start"], tz=timezone.utc))
    vevent.add("dtend", datetime.fromtimestamp(event["end"], tz=timezone.utc))
    if event.get("description"):
        vevent.add("description", event["description"])
    if event.get("location"):
        vevent.add("location", event["location"])
    vevent.add("dtstamp", datetime.now(timezone.utc))
    cal.add_component(vevent)
    return cal.to_ical()


class CalDavClient:
    """Pure CalDAV I/O over raw HTTP (urllib + Basic auth) — no external HTTP client
    dependency, matching the pattern of jarvis/home_assistant/client.py. Uses the
    `icalendar` library only for RFC 5545 parsing/generation, not for transport.

    Implements RFC 4791/6764 discovery (.well-known/caldav -> current-user-principal
    -> calendar-home-set -> calendar collections) so a single pasted service-root URL
    (e.g. iCloud's https://caldav.icloud.com) resolves to real calendar collections,
    with a fast path that skips discovery entirely when the pasted URL is already a
    calendar collection (the common self-hosted Nextcloud/Radicale case).
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self._calendar_urls: list[str] | None = None

    def _headers(self, content_type: str = "") -> dict[str, str]:
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        headers = {"Authorization": f"Basic {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request(
        self,
        url: str,
        *,
        method: str,
        body: bytes | None = None,
        depth: str | None = None,
        content_type: str = "",
        timeout: float = 8,
        deadline: float | None = None,
        _redirects: int = 0,
    ) -> tuple[int, bytes, str]:
        if deadline is not None:
            left = deadline - time.monotonic()
            if left <= 0:
                raise CalDavConnectionError(f"timed out before requesting {url}")
            timeout = min(timeout, left)
        headers = self._headers(content_type)
        if depth is not None:
            headers["Depth"] = depth
        req = request.Request(url, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=max(timeout, 0.001)) as resp:
                return resp.status, resp.read(), resp.geturl()
        except error.HTTPError as exc:
            if exc.code in _REDIRECT_CODES:
                if _redirects >= _MAX_REDIRECTS:
                    raise CalDavConnectionError(f"too many redirects starting at {url}") from exc
                location = exc.headers.get("Location") if exc.headers else None
                if not location:
                    raise CalDavConnectionError(f"redirect from {url} had no Location header") from exc
                next_url = urljoin(url, location)
                return self._request(
                    next_url, method=method, body=body, depth=depth, content_type=content_type,
                    timeout=timeout, deadline=deadline, _redirects=_redirects + 1,
                )
            if exc.code in (401, 403):
                raise CalDavConnectionError(
                    f"authentication failed (HTTP {exc.code}) — check the CalDAV username and password"
                ) from exc
            return exc.code, exc.read(), url
        except (error.URLError, TimeoutError) as exc:
            raise CalDavConnectionError(f"{method} {url} failed: {exc}") from exc

    def _parse_calendar_collections(self, raw: bytes, base_url: str) -> list[str]:
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []
        collections: list[str] = []
        for response_el in root:
            if _local_name(response_el.tag) != "response":
                continue
            href = ""
            is_calendar = False
            for child in response_el.iter():
                name = _local_name(child.tag)
                if name == "href" and not href:
                    href = child.text or ""
                elif name == "calendar":
                    is_calendar = True
            if href and is_calendar:
                collections.append(urljoin(base_url, href))
        return collections

    def _try_direct_url(self, *, deadline: float) -> list[str]:
        status, raw, final_url = self._request(
            self.base_url, method="PROPFIND", depth="0",
            body=_PROPFIND_RESOURCETYPE_BODY.encode("utf-8"),
            content_type="application/xml; charset=utf-8", deadline=deadline,
        )
        if status != 207:
            return []
        return self._parse_calendar_collections(raw, final_url)

    def _propfind_single_href(self, url: str, prop_body: str, want_tag: str, *, deadline: float) -> str | None:
        status, raw, final_url = self._request(
            url, method="PROPFIND", depth="0", body=prop_body.encode("utf-8"),
            content_type="application/xml; charset=utf-8", deadline=deadline,
        )
        if status != 207:
            return None
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return None
        for el in root.iter():
            if _local_name(el.tag) != want_tag:
                continue
            for href_el in el.iter():
                if _local_name(href_el.tag) == "href" and href_el.text:
                    return urljoin(final_url, href_el.text)
        return None

    def _resolve_well_known(self, *, deadline: float) -> str | None:
        url = urljoin(self.base_url + "/", ".well-known/caldav")
        try:
            status, _, final_url = self._request(url, method="GET", deadline=deadline)
        except CalDavConnectionError:
            return None
        return final_url if status < 400 else None

    def _discover_calendar_urls(self) -> list[str]:
        if self._calendar_urls is not None:
            return self._calendar_urls
        deadline = time.monotonic() + _DISCOVERY_BUDGET_SEC

        direct = self._try_direct_url(deadline=deadline)
        if direct:
            self._calendar_urls = direct
            return direct

        principal = self._propfind_single_href(
            self.base_url, _PROPFIND_CURRENT_USER_PRINCIPAL_BODY, "current-user-principal", deadline=deadline,
        )
        if principal is None:
            well_known_root = self._resolve_well_known(deadline=deadline)
            if well_known_root is not None:
                principal = self._propfind_single_href(
                    well_known_root, _PROPFIND_CURRENT_USER_PRINCIPAL_BODY, "current-user-principal",
                    deadline=deadline,
                )
        if principal is None:
            raise CalDavConnectionError(
                f"could not discover a CalDAV principal at {self.base_url} "
                "(tried the URL directly and RFC 6764 .well-known/caldav discovery)"
            )

        home = self._propfind_single_href(
            principal, _PROPFIND_CALENDAR_HOME_SET_BODY, "calendar-home-set", deadline=deadline,
        )
        if home is None:
            raise CalDavConnectionError(f"could not find a calendar-home-set for principal {principal}")

        status, raw, final_home = self._request(
            home, method="PROPFIND", depth="1", body=_PROPFIND_RESOURCETYPE_BODY.encode("utf-8"),
            content_type="application/xml; charset=utf-8", deadline=deadline,
        )
        collections = self._parse_calendar_collections(raw, final_home) if status == 207 else []
        if not collections:
            raise CalDavConnectionError(f"no calendar collections found under {home}")
        self._calendar_urls = collections
        return collections

    def test_connection(self) -> bool:
        try:
            return bool(self._discover_calendar_urls())
        except CalDavConnectionError:
            return False

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        urls = self._discover_calendar_urls()
        body = _REPORT_BODY.format(start=_to_ical_utc(start), end=_to_ical_utc(end)).encode("utf-8")
        events: list[dict] = []
        for url in urls:
            status, raw, _ = self._request(
                url, method="REPORT", depth="1", body=body,
                content_type="application/xml; charset=utf-8", timeout=15,
            )
            if status != 207:
                raise CalDavConnectionError(f"REPORT against {url} failed with HTTP {status}")
            events.extend(self._parse_multistatus(raw))
        return events

    def _parse_multistatus(self, raw: bytes) -> list[dict]:
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            return []
        events: list[dict] = []
        for response_el in root:
            if _local_name(response_el.tag) != "response":
                continue
            href, etag, ics_text = "", "", ""
            for child in response_el.iter():
                name = _local_name(child.tag)
                if name == "href" and not href:
                    href = child.text or ""
                elif name == "getetag":
                    etag = child.text or ""
                elif name == "calendar-data":
                    ics_text = child.text or ""
            if not ics_text:
                continue
            parsed = parse_ics_event(ics_text, href=href, etag=etag)
            if parsed:
                events.append(parsed)
        return events

    def _event_url(self, collection_url: str, uid: str) -> str:
        return f"{collection_url.rstrip('/')}/{uid}.ics"

    def _resolve_write_target(self, uid: str, href: str | None) -> str:
        collection = self._discover_calendar_urls()[0]
        return urljoin(collection, href) if href else self._event_url(collection, uid)

    def put_event(self, event: dict, *, href: str | None = None) -> str | None:
        try:
            target = self._resolve_write_target(event["uid"], href)
            status, _, _ = self._request(
                target, method="PUT", body=build_ics(event),
                content_type="text/calendar; charset=utf-8", timeout=10,
            )
        except CalDavConnectionError:
            return None
        return target if status in (200, 201, 204) else None

    def delete_event(self, uid: str, *, href: str | None = None) -> bool:
        try:
            target = self._resolve_write_target(uid, href)
            status, _, _ = self._request(target, method="DELETE", timeout=10)
        except CalDavConnectionError:
            return False
        return status in (200, 204, 404)
