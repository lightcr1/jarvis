import json
import os
import threading
import time
import uuid
from pathlib import Path


class CreditStore:
    """Per-user CHF credit balance + ledger.

    Schema: {
        "balances": {user_id: {"balance_chf": float, "updated_at": int}},
        "ledger":   [{id, user_id, type, amount_chf, balance_after, note, created_at}]
    }

    `deduct` is protected by a threading.Lock to prevent race conditions under
    concurrent requests. Plain `_save()` (same as all other stores) is used.
    """

    def __init__(self) -> None:
        path_str = os.getenv("JARVIS_CREDIT_STORE_PATH") or ""
        if path_str:
            self.path = Path(path_str)
        else:
            self.path = Path("/var/lib/jarvis/credits.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.data = self._load()

    def _empty(self) -> dict:
        return {"balances": {}, "ledger": []}

    def _load(self) -> dict:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_balance(self, user_id: str) -> float:
        entry = self.data["balances"].get(user_id) or {}
        return float(entry.get("balance_chf", 0.0))

    def top_up(self, user_id: str, amount_chf: float, *, note: str = "", actor: str = "admin") -> dict:
        if amount_chf <= 0:
            raise ValueError("top-up amount must be positive")
        now = int(time.time())
        current = self.get_balance(user_id)
        new_balance = round(current + amount_chf, 6)
        self.data["balances"][user_id] = {"balance_chf": new_balance, "updated_at": now}
        entry = {
            "id": f"cr-{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "type": "topup",
            "amount_chf": round(amount_chf, 6),
            "balance_after": new_balance,
            "note": note,
            "actor": actor,
            "created_at": now,
        }
        self.data["ledger"].append(entry)
        self._save()
        return entry

    def deduct(self, user_id: str, amount_chf: float, *, note: str = "") -> tuple[bool, float]:
        """Deduct amount from balance. Returns (ok, new_balance). Refuses to go negative."""
        with self._lock:
            now = int(time.time())
            current = self.get_balance(user_id)
            if amount_chf > current:
                return False, current
            new_balance = round(current - amount_chf, 6)
            self.data["balances"][user_id] = {"balance_chf": new_balance, "updated_at": now}
            entry = {
                "id": f"cr-{uuid.uuid4().hex[:12]}",
                "user_id": user_id,
                "type": "deduction",
                "amount_chf": round(amount_chf, 6),
                "balance_after": new_balance,
                "note": note,
                "created_at": now,
            }
            self.data["ledger"].append(entry)
            self._save()
            return True, new_balance

    def list_ledger(self, user_id: str, limit: int = 50) -> list[dict]:
        entries = [e for e in self.data["ledger"] if e.get("user_id") == user_id]
        return list(reversed(entries))[:max(1, min(limit, 500))]
