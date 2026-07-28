from __future__ import annotations

import base64
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from urllib import error, request

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
    """

    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password

    def _headers(self, content_type: str = "") -> dict[str, str]:
        token = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
        headers = {"Authorization": f"Basic {token}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def test_connection(self) -> bool:
        req = request.Request(self.base_url, headers={**self._headers(), "Depth": "0"}, method="PROPFIND")
        try:
            with request.urlopen(req, timeout=8) as resp:
                return resp.status in (200, 207)
        except (error.URLError, TimeoutError, error.HTTPError):
            return False

    def list_events(self, start: datetime, end: datetime) -> list[dict]:
        body = _REPORT_BODY.format(start=_to_ical_utc(start), end=_to_ical_utc(end)).encode("utf-8")
        req = request.Request(
            self.base_url,
            data=body,
            headers={**self._headers("application/xml; charset=utf-8"), "Depth": "1"},
            method="REPORT",
        )
        try:
            with request.urlopen(req, timeout=15) as resp:
                raw = resp.read()
        except (error.URLError, TimeoutError, error.HTTPError):
            return []
        return self._parse_multistatus(raw)

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

    def _event_url(self, uid: str) -> str:
        return f"{self.base_url}/{uid}.ics"

    def put_event(self, event: dict) -> bool:
        body = build_ics(event)
        req = request.Request(
            self._event_url(event["uid"]),
            data=body,
            headers=self._headers("text/calendar; charset=utf-8"),
            method="PUT",
        )
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 201, 204)
        except (error.URLError, TimeoutError, error.HTTPError):
            return False

    def delete_event(self, uid: str) -> bool:
        req = request.Request(self._event_url(uid), headers=self._headers(), method="DELETE")
        try:
            with request.urlopen(req, timeout=10) as resp:
                return resp.status in (200, 204, 404)
        except error.HTTPError as exc:
            return exc.code == 404
        except (error.URLError, TimeoutError):
            return False
