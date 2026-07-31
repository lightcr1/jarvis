from __future__ import annotations

import json
import os
import uuid
from pathlib import Path


_DEFAULT_PLANS: list[dict] = [
    {
        "id": "plan-free",
        "name": "Free",
        "price_chf_per_month": 0.0,
        "ai_credit_chf_monthly": 2.0,
        "storage_gb_included": 2.0,
        "sort_order": 0,
    },
    {
        "id": "plan-standard",
        "name": "Standard",
        "price_chf_per_month": 8.0,
        "ai_credit_chf_monthly": 10.0,
        "storage_gb_included": 20.0,
        "sort_order": 1,
    },
    {
        "id": "plan-pro",
        "name": "Pro",
        "price_chf_per_month": 20.0,
        "ai_credit_chf_monthly": 30.0,
        "storage_gb_included": 100.0,
        "sort_order": 2,
    },
]


def _normalize_plan(payload: dict) -> dict:
    def _f(key: str, default: float = 0.0) -> float:
        try:
            return max(0.0, round(float(payload.get(key, default)), 2))
        except (TypeError, ValueError):
            return default

    return {
        "id": str(payload.get("id") or ""),
        "name": str(payload.get("name") or "Unnamed plan").strip() or "Unnamed plan",
        "price_chf_per_month": _f("price_chf_per_month"),
        "ai_credit_chf_monthly": _f("ai_credit_chf_monthly"),
        "storage_gb_included": _f("storage_gb_included"),
        "sort_order": int(payload.get("sort_order") or 0),
        "stripe_price_id": str(payload.get("stripe_price_id") or "").strip(),
    }


class PlanStore:
    """Admin-managed catalog of subscription plans (bundled AI credit + storage)."""

    def __init__(self) -> None:
        configured = os.getenv("JARVIS_PLAN_STORE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/plans.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"plans": [], "seeded": False}

    def _load(self) -> dict:
        if not self.path.exists():
            base = self._empty()
            base["plans"] = [dict(p) for p in _DEFAULT_PLANS]
            base["seeded"] = True
            self._save_data(base)
            return base
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            merged = {**self._empty(), **content}
            original_plans = merged.get("plans")
            if not isinstance(original_plans, list):
                original_plans = []
            was_seeded = bool(merged.get("seeded"))
            plans = ([dict(p) for p in _DEFAULT_PLANS] + original_plans) if not was_seeded else original_plans
            merged["plans"] = [_normalize_plan(p) for p in plans]
            merged["seeded"] = True
            if not was_seeded or merged["plans"] != original_plans:
                self._save_data(merged)
            return merged
        except (OSError, json.JSONDecodeError):
            base = self._empty()
            base["plans"] = [dict(p) for p in _DEFAULT_PLANS]
            base["seeded"] = True
            return base

    def _save_data(self, data: dict) -> None:
        try:
            self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _save(self) -> None:
        self._save_data(self.data)

    def list_plans(self) -> list[dict]:
        return sorted((dict(p) for p in self.data.get("plans", [])), key=lambda p: p.get("sort_order", 0))

    def get_plan(self, plan_id: str) -> dict | None:
        for plan in self.data.get("plans", []):
            if plan.get("id") == plan_id:
                return dict(plan)
        return None

    def create_plan(self, payload: dict) -> dict:
        plan = _normalize_plan(payload)
        plan["id"] = f"plan-{uuid.uuid4().hex[:10]}"
        self.data.setdefault("plans", []).append(plan)
        self._save()
        return dict(plan)

    def update_plan(self, plan_id: str, patch: dict) -> dict | None:
        plans = self.data.setdefault("plans", [])
        for idx, plan in enumerate(plans):
            if plan.get("id") != plan_id:
                continue
            merged = {**plan, **{k: v for k, v in patch.items() if v is not None}}
            merged["id"] = plan_id
            plans[idx] = _normalize_plan(merged)
            plans[idx]["id"] = plan_id
            self._save()
            return dict(plans[idx])
        return None

    def delete_plan(self, plan_id: str) -> bool:
        plans = self.data.setdefault("plans", [])
        before = len(plans)
        self.data["plans"] = [p for p in plans if p.get("id") != plan_id]
        if len(self.data["plans"]) < before:
            self._save()
            return True
        return False
