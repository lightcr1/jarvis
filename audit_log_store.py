from __future__ import annotations

import json
import os
from pathlib import Path
import time


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

    def read_events(
        self,
        limit: int = 100,
        event: str | None = None,
        role: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> list[dict]:
        if not self.path.exists():
            return []
        cap = max(1, min(limit, 500))
        lines = self.path.read_text(encoding="utf-8").splitlines()
        out: list[dict] = []
        for raw in reversed(lines):
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event and item.get("event") != event:
                continue
            if role and (item.get("role") or "") != role:
                continue
            ts = int(item.get("ts") or 0)
            if since_ts is not None and ts < since_ts:
                continue
            if until_ts is not None and ts > until_ts:
                continue
            out.append(item)
            if len(out) >= cap:
                break
        return out


    def count_events(
        self,
        event: str | None = None,
        role: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> int:
        if not self.path.exists():
            return 0
        count = 0
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if event and item.get("event") != event:
                continue
            if role and (item.get("role") or "") != role:
                continue
            ts = int(item.get("ts") or 0)
            if since_ts is not None and ts < since_ts:
                continue
            if until_ts is not None and ts > until_ts:
                continue
            count += 1
        return count


    def aggregate_counts(
        self,
        role: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> dict[str, int]:
        if not self.path.exists():
            return {}

        out: dict[str, int] = {}
        for raw in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if role and (item.get("role") or "") != role:
                continue
            ts = int(item.get("ts") or 0)
            if since_ts is not None and ts < since_ts:
                continue
            if until_ts is not None and ts > until_ts:
                continue
            event = str(item.get("event") or "unknown")
            out[event] = out.get(event, 0) + 1
        return out
