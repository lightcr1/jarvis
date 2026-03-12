from __future__ import annotations

import json
import math
import os
from pathlib import Path
import time
from typing import Iterable, Iterator


class AuditLogStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_AUDIT_LOG_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/audit.log")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, event: str, payload: dict) -> None:
        entry = {"ts": int(time.time()), "event": event, **payload}
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            return

    @staticmethod
    def _normalized_text(value: object) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    @classmethod
    def _is_unset_filter(cls, value: object) -> bool:
        return value is None or cls._normalized_text(value) == ""

    @classmethod
    def _matches_event_filter(cls, item: dict, event: object | None) -> bool:
        if cls._is_unset_filter(event):
            return True
        return cls._normalized_text(item.get("event")) == cls._normalized_text(event)

    @classmethod
    def _matches_role_filter(cls, item: dict, role: object | None) -> bool:
        if cls._is_unset_filter(role):
            return True
        normalized_role = cls._normalized_text(role)
        return (
            cls._normalized_text(item.get("role")) == normalized_role
            or cls._normalized_text(item.get("actor_role")) == normalized_role
        )

    @classmethod
    def _matches_actor_user_filter(cls, item: dict, actor_user_id: object | None) -> bool:
        if cls._is_unset_filter(actor_user_id):
            return True
        raw_actor_user_id = item.get("actor_user_id")
        if raw_actor_user_id is None:
            return False
        return str(raw_actor_user_id) == str(actor_user_id)

    @classmethod
    def _matches_token_fingerprint_filter(cls, item: dict, token_fingerprint: object | None) -> bool:
        if cls._is_unset_filter(token_fingerprint):
            return True
        return cls._normalized_text(item.get("token_fingerprint")) == cls._normalized_text(token_fingerprint)

    @staticmethod
    def _is_event_item(item: object) -> bool:
        return isinstance(item, dict)

    def _iter_raw_lines(self, newest_first: bool = False) -> Iterable[str]:
        try:
            exists = self.path.exists()
        except OSError:
            return ()
        if not exists:
            return ()
        if newest_first:
            try:
                return reversed(self.path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError):
                return ()

        def _forward_lines() -> Iterator[str]:
            try:
                with self.path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        yield line.rstrip("\n")
            except (OSError, UnicodeDecodeError):
                return

        return _forward_lines()

    @staticmethod
    def _extract_ts(item: dict) -> int | None:
        raw_ts = item.get("ts")
        if raw_ts is None:
            return 0
        if isinstance(raw_ts, bool):
            return None
        if isinstance(raw_ts, float):
            if not math.isfinite(raw_ts):
                return None
            if not raw_ts.is_integer():
                return None
        try:
            return int(raw_ts)
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _coerce_limit(value: object | None, default: int = 100) -> int:
        if value is None or isinstance(value, bool):
            return default
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                return default
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _coerce_ts_bound(value: object | None) -> int | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, float):
            if not math.isfinite(value) or not value.is_integer():
                return None
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError):
            return None

    def _iter_filtered_events(
        self,
        *,
        event: object | None = None,
        role: object | None = None,
        since_ts: object | None = None,
        until_ts: object | None = None,
        actor_user_id: object | None = None,
        token_fingerprint: object | None = None,
        newest_first: bool = False,
    ) -> Iterator[dict]:
        parsed_since_ts = self._coerce_ts_bound(since_ts)
        parsed_until_ts = self._coerce_ts_bound(until_ts)

        for raw in self._iter_raw_lines(newest_first=newest_first):
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not self._is_event_item(item):
                continue
            if not self._matches_event_filter(item, event):
                continue
            if not self._matches_role_filter(item, role):
                continue
            if not self._matches_actor_user_filter(item, actor_user_id):
                continue
            if not self._matches_token_fingerprint_filter(item, token_fingerprint):
                continue
            ts = self._extract_ts(item)
            if ts is None:
                continue
            if parsed_since_ts is not None and ts < parsed_since_ts:
                continue
            if parsed_until_ts is not None and ts > parsed_until_ts:
                continue
            yield item

    def read_events(
        self,
        limit: object | None = 100,
        event: object | None = None,
        role: object | None = None,
        since_ts: object | None = None,
        until_ts: object | None = None,
        actor_user_id: object | None = None,
        token_fingerprint: object | None = None,
    ) -> list[dict]:
        parsed_limit = self._coerce_limit(limit)
        cap = max(1, min(parsed_limit, 500))
        out: list[dict] = []
        for item in self._iter_filtered_events(
            event=event,
            role=role,
            since_ts=since_ts,
            until_ts=until_ts,
            actor_user_id=actor_user_id,
            token_fingerprint=token_fingerprint,
            newest_first=True,
        ):
            if not self._is_event_item(item):
                continue
            out.append(item)
            if len(out) >= cap:
                break
        return out

    def count_events(
        self,
        event: object | None = None,
        role: object | None = None,
        since_ts: object | None = None,
        until_ts: object | None = None,
        actor_user_id: object | None = None,
        token_fingerprint: object | None = None,
    ) -> int:
        count = 0
        for item in self._iter_filtered_events(
            event=event,
            role=role,
            since_ts=since_ts,
            until_ts=until_ts,
            actor_user_id=actor_user_id,
            token_fingerprint=token_fingerprint,
        ):
            if not self._is_event_item(item):
                continue
            count += 1
        return count

    def aggregate_counts(
        self,
        event: object | None = None,
        role: object | None = None,
        since_ts: object | None = None,
        until_ts: object | None = None,
        actor_user_id: object | None = None,
        token_fingerprint: object | None = None,
    ) -> dict[str, int]:
        out: dict[str, int] = {}
        for item in self._iter_filtered_events(
            event=event,
            role=role,
            since_ts=since_ts,
            until_ts=until_ts,
            actor_user_id=actor_user_id,
            token_fingerprint=token_fingerprint,
        ):
            if not self._is_event_item(item):
                continue
            event_name = self._normalized_text(item.get("event")) or "unknown"
            out[event_name] = out.get(event_name, 0) + 1
        return out
