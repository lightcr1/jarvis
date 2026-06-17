"""Append-only JSONL usage log — mirrors AuditLogStore but with numeric SUM aggregation.

Log fields per record:
    ts, user_id, conversation_id, provider, model, billing_mode,
    input_tokens, output_tokens, total_tokens,
    estimated_cost_usd, estimated_cost_chf,
    request_status ("ok" | "error" | "blocked"), error
"""

import json
import os
import time
from pathlib import Path


class UsageLogStore:
    def __init__(self) -> None:
        path_str = os.getenv("JARVIS_USAGE_LOG_PATH") or ""
        if path_str:
            self.path = Path(path_str)
        else:
            self.path = Path("/var/lib/jarvis/usage.log")
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, record: dict) -> None:
        entry = {"ts": int(time.time()), **record}
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    def _iter_raw(self, newest_first: bool = False):
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        lines = [l for l in text.splitlines() if l.strip()]
        if newest_first:
            lines = list(reversed(lines))
        for line in lines:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    def _matches(self, entry: dict, user_id=None, provider=None, model=None, billing_mode=None, since_ts=None, until_ts=None) -> bool:
        if user_id and entry.get("user_id") != user_id:
            return False
        if provider and entry.get("provider") != provider:
            return False
        if model and entry.get("model") != model:
            return False
        if billing_mode and entry.get("billing_mode") != billing_mode:
            return False
        ts = entry.get("ts", 0)
        if since_ts and ts < since_ts:
            return False
        if until_ts and ts > until_ts:
            return False
        return True

    def aggregate(
        self,
        *,
        user_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        billing_mode: str | None = None,
        since_ts: int | None = None,
        until_ts: int | None = None,
    ) -> dict:
        total_in = 0
        total_out = 0
        total_cost_usd = 0.0
        total_cost_chf = 0.0
        count = 0
        for entry in self._iter_raw():
            if not self._matches(entry, user_id=user_id, provider=provider, model=model, billing_mode=billing_mode, since_ts=since_ts, until_ts=until_ts):
                continue
            count += 1
            total_in += int(entry.get("input_tokens") or 0)
            total_out += int(entry.get("output_tokens") or 0)
            total_cost_usd += float(entry.get("estimated_cost_usd") or 0.0)
            total_cost_chf += float(entry.get("estimated_cost_chf") or 0.0)
        return {
            "request_count": count,
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "total_cost_usd": round(total_cost_usd, 6),
            "total_cost_chf": round(total_cost_chf, 6),
        }

    def recent(self, user_id: str | None = None, limit: int = 100) -> list[dict]:
        limit = max(1, min(int(limit), 500))
        results = []
        for entry in self._iter_raw(newest_first=True):
            if user_id and entry.get("user_id") != user_id:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def daily_buckets(self, *, user_id: str | None = None, days: int = 7) -> list[dict]:
        now = int(time.time())
        bucket_size = 86400  # 1 day
        cutoff = now - (days * bucket_size)
        buckets: dict[int, dict] = {}
        for entry in self._iter_raw():
            ts = entry.get("ts", 0)
            if ts < cutoff:
                continue
            if user_id and entry.get("user_id") != user_id:
                continue
            day_start = (ts // bucket_size) * bucket_size
            if day_start not in buckets:
                buckets[day_start] = {"bucket_ts": day_start, "cost_chf": 0.0, "requests": 0}
            buckets[day_start]["cost_chf"] += float(entry.get("estimated_cost_chf") or 0.0)
            buckets[day_start]["requests"] += 1
        result = sorted(buckets.values(), key=lambda b: b["bucket_ts"])
        for b in result:
            b["cost_chf"] = round(b["cost_chf"], 6)
        return result
