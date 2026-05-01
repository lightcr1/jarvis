from __future__ import annotations

import json
import os
from pathlib import Path
from urllib import error, request


class HomeAssistantClient:
    def __init__(self) -> None:
        self.base_url = (os.getenv("JARVIS_HOME_ASSISTANT_URL") or "").strip()
        self.api_token = (os.getenv("JARVIS_HOME_ASSISTANT_TOKEN") or "").strip()
        self.calendar_url = (os.getenv("JARVIS_HOME_ASSISTANT_CALENDAR_URL") or "").strip()
        self.calendar_token = (os.getenv("JARVIS_HOME_ASSISTANT_CALENDAR_TOKEN") or "").strip()
        self.calendar_write_url = (os.getenv("JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_URL") or "").strip()
        self.calendar_write_token = (os.getenv("JARVIS_HOME_ASSISTANT_CALENDAR_WRITE_TOKEN") or "").strip()
        self.calendar_file = (os.getenv("JARVIS_HOME_ASSISTANT_CALENDAR_FILE") or "").strip()
        self.calendar_seed = (os.getenv("JARVIS_HOME_ASSISTANT_CALENDAR_SEED") or "").strip()
        self.inbox_url = (os.getenv("JARVIS_HOME_ASSISTANT_INBOX_URL") or "").strip()
        self.inbox_token = (os.getenv("JARVIS_HOME_ASSISTANT_INBOX_TOKEN") or "").strip()
        self.inbox_write_url = (os.getenv("JARVIS_HOME_ASSISTANT_INBOX_WRITE_URL") or "").strip()
        self.inbox_write_token = (os.getenv("JARVIS_HOME_ASSISTANT_INBOX_WRITE_TOKEN") or "").strip()
        self.inbox_file = (os.getenv("JARVIS_HOME_ASSISTANT_INBOX_FILE") or "").strip()
        self.inbox_seed = (os.getenv("JARVIS_HOME_ASSISTANT_INBOX_SEED") or "").strip()

    def config_summary(self) -> dict[str, object]:
        configured = bool(self.base_url and self.api_token)
        return {
            "configured": configured,
            "base_url": self.base_url,
            "mode": "external_home_assistant",
            "healthy": configured,
            "calendar_provider": "http" if self.calendar_url else ("file" if self.calendar_file else ("seed" if self.calendar_seed else "scaffold")),
            "calendar_write_enabled": bool(self.calendar_write_url),
            "inbox_provider": "http" if self.inbox_url else ("file" if self.inbox_file else ("seed" if self.inbox_seed else "scaffold")),
            "inbox_write_enabled": bool(self.inbox_write_url),
        }

    def _load_seed_list(self, raw: str) -> list[dict[str, object]]:
        if not raw:
            return []
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _load_file_list(self, path_value: str) -> list[dict[str, object]]:
        if not path_value:
            return []
        try:
            raw = Path(path_value).read_text(encoding="utf-8")
        except OSError:
            return []
        return self._load_seed_list(raw)

    def _fetch_json_list(self, url: str, token: str = "") -> list[dict[str, object]]:
        if not url:
            return []
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(url, headers=headers, method="GET")
        try:
            with request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            return []
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def _send_json(self, url: str, payload: dict[str, object], token: str = "", method: str = "POST") -> dict[str, object] | None:
        if not url:
            return None
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method=method,
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                raw = response.read().decode("utf-8").strip()
        except (error.URLError, TimeoutError):
            return None
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def fetch_states(self) -> list[dict[str, object]]:
        if not (self.base_url and self.api_token):
            return []

        url = f"{self.base_url.rstrip('/')}/api/states"
        req = request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (error.URLError, TimeoutError, json.JSONDecodeError):
            return []

        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    def fetch_calendar_items(self) -> list[dict[str, object]]:
        if self.calendar_url:
            return self._fetch_json_list(self.calendar_url, self.calendar_token)
        if self.calendar_file:
            return self._load_file_list(self.calendar_file)
        return self._load_seed_list(self.calendar_seed)

    def fetch_inbox_items(self) -> list[dict[str, object]]:
        if self.inbox_url:
            return self._fetch_json_list(self.inbox_url, self.inbox_token)
        if self.inbox_file:
            return self._load_file_list(self.inbox_file)
        return self._load_seed_list(self.inbox_seed)

    def create_calendar_item(self, item: dict[str, object]) -> dict[str, object] | None:
        return self._send_json(self.calendar_write_url, item, self.calendar_write_token)

    def create_inbox_item(self, item: dict[str, object]) -> dict[str, object] | None:
        return self._send_json(self.inbox_write_url, item, self.inbox_write_token)

    def update_calendar_item(self, item: dict[str, object], action: str) -> dict[str, object] | None:
        return self._send_json(
            self.calendar_write_url,
            {"mode": "update", "action": action, "item": item},
            self.calendar_write_token,
        )

    def update_inbox_item(self, item: dict[str, object], action: str) -> dict[str, object] | None:
        return self._send_json(
            self.inbox_write_url,
            {"mode": "update", "action": action, "item": item},
            self.inbox_write_token,
        )
