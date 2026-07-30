from __future__ import annotations

import time


def _current_ym() -> str:
    return time.strftime("%Y-%m", time.gmtime())


def assign_plan(user_id: str, plan_id: str, *, plan_store, user_limits_store, credit_store) -> dict:
    """Assign a user to a plan: syncs their storage quota and grants the plan's monthly AI credit immediately.

    Pass an empty plan_id to unassign (clears the plan, leaves storage_quota_mb at 0 / admin default).
    """
    plan = plan_store.get_plan(plan_id) if plan_id else None
    if plan_id and plan is None:
        raise ValueError("plan not found")

    storage_quota_mb = int(round(plan["storage_gb_included"] * 1024)) if plan else 0
    updated = user_limits_store.update(user_id, {"plan_id": plan_id, "storage_quota_mb": storage_quota_mb})

    if plan and plan["ai_credit_chf_monthly"] > 0:
        credit_store.top_up(user_id, plan["ai_credit_chf_monthly"], note=f"Plan assigned: {plan['name']}", actor="system")
        updated = user_limits_store.update(user_id, {"plan_last_grant_ym": _current_ym()})

    return updated


def ensure_monthly_grant(user_id: str, *, plan_store, user_limits_store, credit_store) -> bool:
    """Grants the user's plan AI credit once per calendar month (UTC). Returns True if a grant was made.

    Called lazily from billing views and the AI router preflight — there is no background
    scheduler for this yet, so a plan's credit is only granted the next time the user's
    account is actually touched after the month rolls over.
    """
    limits = user_limits_store.get(user_id)
    plan_id = limits.get("plan_id") or ""
    if not plan_id:
        return False
    plan = plan_store.get_plan(plan_id)
    if plan is None:
        return False

    current_ym = _current_ym()
    if limits.get("plan_last_grant_ym") == current_ym:
        return False

    if plan["ai_credit_chf_monthly"] > 0:
        credit_store.top_up(user_id, plan["ai_credit_chf_monthly"], note=f"Monthly plan credit: {plan['name']}", actor="system")
    user_limits_store.update(user_id, {"plan_last_grant_ym": current_ym})
    return True
