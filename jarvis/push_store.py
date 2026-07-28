from __future__ import annotations

import json
import os
import time
from pathlib import Path


class PushSubscriptionStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_PUSH_SUBSCRIPTIONS_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/push_subscriptions.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"subscriptions": {}}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            if not isinstance(merged.get("subscriptions"), dict):
                merged["subscriptions"] = {}
            return merged
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def list_for_user(self, user_id: str) -> list[dict]:
        return [dict(s) for s in self.data.get("subscriptions", {}).get(user_id, [])]

    def list_all(self) -> dict[str, list[dict]]:
        return {
            uid: [dict(s) for s in subs]
            for uid, subs in self.data.get("subscriptions", {}).items()
            if subs
        }

    def add(self, user_id: str, subscription: dict) -> dict:
        endpoint = str(subscription.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("subscription endpoint is required")
        keys = subscription.get("keys") or {}
        entry = {
            "endpoint": endpoint,
            "keys": {
                "p256dh": str(keys.get("p256dh") or ""),
                "auth": str(keys.get("auth") or ""),
            },
            "created_at": int(time.time()),
        }
        bucket = self.data.setdefault("subscriptions", {}).setdefault(user_id, [])
        bucket[:] = [s for s in bucket if s.get("endpoint") != endpoint]
        bucket.append(entry)
        self._save()
        return entry

    def remove(self, user_id: str, endpoint: str) -> bool:
        bucket = self.data.setdefault("subscriptions", {}).get(user_id, [])
        filtered = [s for s in bucket if s.get("endpoint") != endpoint]
        if len(filtered) == len(bucket):
            return False
        self.data["subscriptions"][user_id] = filtered
        self._save()
        return True

    def remove_by_endpoint(self, user_id: str, endpoint: str) -> None:
        """Best-effort removal used to prune subscriptions the push service reports as gone."""
        self.remove(user_id, endpoint)

    def remove_all_for_user(self, user_id: str) -> bool:
        removed = self.data.setdefault("subscriptions", {}).pop(user_id, None)
        if removed:
            self._save()
            return True
        return False
