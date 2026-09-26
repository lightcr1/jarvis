"""Server-seitige Pod-Budget-Rechnung (Plan 0.3)."""
from __future__ import annotations

import pytest

from jarvis import pod_budget
from jarvis.pod_budget import PodBudgetStore, month_start, pod_start_decision


class _Clock:
    def __init__(self, now):
        self.now = now
    def __call__(self):
        return self.now


def _store(tmp_path, now=1_700_000_000.0):
    return PodBudgetStore(tmp_path / "pod_budget.sqlite3", clock=_Clock(now))


def test_spent_is_computed_from_sessions_not_params(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "10")
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "2")
    monkeypatch.setenv("JARVIS_POD_PLANNED_HOURS", "1")
    store = _store(tmp_path)
    store.open_session("default", 2.0, now=1_700_000_000.0)
    store.close_open_sessions(now=1_700_000_000.0 + 3600)  # 2 CHF verbraucht
    decision = pod_start_decision(store, "default", now=1_700_000_000.0 + 3600)
    assert decision["spent_chf"] == 2.0
    assert decision["estimate_chf"] == 2.0
    assert decision["allowed"] is True  # 2 + 2 <= 10


def test_open_session_uses_now_and_can_exceed(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "5")
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "3")
    monkeypatch.setenv("JARVIS_POD_PLANNED_HOURS", "1")
    store = _store(tmp_path)
    store.open_session("default", 3.0, now=1_700_000_000.0)
    decision = pod_start_decision(store, "default", now=1_700_000_000.0 + 3600)  # 3 verbraucht
    assert decision["spent_chf"] == 3.0
    assert decision["allowed"] is False  # 3 + 3 > 5


def test_requires_budget_and_rate(tmp_path, monkeypatch):
    store = _store(tmp_path)
    monkeypatch.delenv("JARVIS_POD_MONTHLY_BUDGET_CHF", raising=False)
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "2")
    assert pod_start_decision(store, "default")["allowed"] is False
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "10")
    monkeypatch.delenv("JARVIS_POD_COST_PER_HOUR_CHF", raising=False)
    assert pod_start_decision(store, "default")["allowed"] is False


def test_controller_reconciliation_closes_dangling_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "100")
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "1")
    store = _store(tmp_path)
    store.open_session("default", 1.0, now=1_700_000_000.0)
    assert store.has_open_session() is True
    pod_stopped = type("P", (), {"status": lambda self: {"pod": None}})()
    pod_start_decision(store, "default", pod_control=pod_stopped, now=1_700_000_100.0)
    assert store.has_open_session() is False


def test_month_start_is_the_first_utc_day():
    start = month_start(1_700_000_000.0)
    assert start % 86400 == 0


def test_only_current_month_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_POD_MONTHLY_BUDGET_CHF", "10")
    monkeypatch.setenv("JARVIS_POD_COST_PER_HOUR_CHF", "1")
    store = _store(tmp_path)
    old = month_start(1_700_000_000.0) - 2 * 86400 * 40
    store.open_session("default", 100.0, now=old)
    store.close_open_sessions(now=old + 3600)
    decision = pod_start_decision(store, "default", now=1_700_000_000.0)
    assert decision["spent_chf"] == 0.0 and decision["allowed"] is True


def test_agent_grants_deps_wire_totp_and_pod(tmp_path):
    from types import SimpleNamespace
    from jarvis.router_dependencies import build_agent_grants_deps
    state = SimpleNamespace(
        agent_grant_store=None, patch_review_store=None, email_service=None,
        pod_control="pod", pod_budget_store="budget", totp_store="totp",
        _get_identity_session=lambda token: None, normalize_role=lambda r: r,
        _audit_admin_event=lambda *a: None,
    )
    deps = build_agent_grants_deps(state)
    assert deps["pod_control"].get() == "pod"
    assert deps["pod_budget_store"].get() == "budget"
    assert deps["totp_store"].get() == "totp"
