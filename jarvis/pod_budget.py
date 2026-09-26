"""Server-seitige Pod-Budget-Rechnung (Plan 0.3).

Der Verbrauch wird **nicht** aus den Parametern der Anfrage gelesen, sondern aus
serverseitig gefuehrten Pod-Sitzungen (Startzeit bis Stop/Reconciliation). Der
Schaetzwert ergibt sich aus dem konfigurierten Stundensatz und der geplanten
Dauer. Ohne gesetztes Monatsbudget *oder* ohne bekannten Stundensatz wird ein
Start fail-closed abgelehnt.
"""
from __future__ import annotations

import calendar
import os
import sqlite3
import time
import uuid
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    try:
        return max(0.0, float(os.getenv(name, "") or default))
    except (TypeError, ValueError):
        return default


def cost_per_hour_chf() -> float:
    return _env_float("JARVIS_POD_COST_PER_HOUR_CHF", 0.0)


def planned_hours() -> float:
    return _env_float("JARVIS_POD_PLANNED_HOURS", 1.0)


def monthly_budget_chf() -> float:
    return _env_float("JARVIS_POD_MONTHLY_BUDGET_CHF", 0.0)


def month_start(ts: float) -> float:
    """UTC-Monatsanfang zu einem Zeitstempel."""
    struct = time.gmtime(ts)
    return float(calendar.timegm((struct.tm_year, struct.tm_mon, 1, 0, 0, 0, 0, 0, 0)))


def _session_cost(session: dict, now: float) -> float:
    start = float(session["started_at"])
    end = float(session["stopped_at"]) if session.get("stopped_at") else now
    hours = max(0.0, end - start) / 3600.0
    return hours * float(session["hourly_cost_chf"])


class PodBudgetStore:
    def __init__(self, path: str | Path | None = None, *, clock=time.time) -> None:
        self.path = Path(path or os.getenv("JARVIS_POD_BUDGET_PATH", "/var/lib/jarvis/pod_budget.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS pod_sessions (
                id TEXT PRIMARY KEY, profile TEXT NOT NULL, started_at REAL NOT NULL,
                stopped_at REAL, hourly_cost_chf REAL NOT NULL
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def open_session(self, profile: str, hourly_cost_chf: float, *, now: float | None = None) -> dict:
        moment = self.clock() if now is None else now
        identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("INSERT INTO pod_sessions (id,profile,started_at,stopped_at,hourly_cost_chf) VALUES (?,?,?,NULL,?)",
                       (identifier, str(profile or "default"), float(moment), max(0.0, float(hourly_cost_chf))))
        return {"id": identifier, "profile": str(profile or "default"), "started_at": float(moment),
                "stopped_at": None, "hourly_cost_chf": max(0.0, float(hourly_cost_chf))}

    def close_open_sessions(self, *, now: float | None = None) -> int:
        moment = self.clock() if now is None else now
        with self._connect() as db:
            db.execute("UPDATE pod_sessions SET stopped_at=? WHERE stopped_at IS NULL", (float(moment),))
            return db.execute("SELECT changes()").fetchone()[0]

    def list_sessions(self, *, since: float | None = None) -> list[dict]:
        query = "SELECT * FROM pod_sessions"
        params: list = []
        if since is not None:
            query += " WHERE started_at>=?"
            params.append(float(since))
        query += " ORDER BY started_at, id"
        with self._connect() as db:
            return [dict(row) for row in db.execute(query, params).fetchall()]

    def spent_chf(self, *, since: float, now: float | None = None) -> float:
        moment = self.clock() if now is None else now
        return round(sum(_session_cost(s, moment) for s in self.list_sessions(since=since)), 4)

    def has_open_session(self) -> bool:
        with self._connect() as db:
            row = db.execute("SELECT 1 FROM pod_sessions WHERE stopped_at IS NULL LIMIT 1").fetchone()
        return row is not None


def pod_start_decision(store: PodBudgetStore, profile: str, *, pod_control=None,
                       now: float | None = None) -> dict:
    """Budget-Entscheidung fuer einen Pod-Start; nie aus Anfrage-Parametern."""
    moment = time.time() if now is None else now
    if pod_control is not None:
        # Controller ist die Autoritaet, ob noch ein Pod laeuft. Nur wenn er
        # explizit keinen Pod meldet, werden haengende Sitzungen geschlossen
        # (sonst bewusst Ueberzaehlung = fail-closed).
        try:
            status = pod_control.status()
            if isinstance(status, dict) and not status.get("pod"):
                store.close_open_sessions(now=moment)
        except Exception:  # noqa: BLE001 - Entscheidung darf daran nicht brechen
            pass
    cap = monthly_budget_chf()
    rate = cost_per_hour_chf()
    hours = planned_hours()
    spent = store.spent_chf(since=month_start(moment), now=moment)
    estimate = round(rate * hours, 2)
    allowed = cap > 0 and rate > 0 and (spent + estimate) <= cap
    return {
        "allowed": allowed,
        "profile": str(profile or "default"),
        "cap_chf": cap,
        "rate_chf": round(rate, 4),
        "planned_hours": hours,
        "estimate_chf": estimate,
        "spent_chf": spent,
    }
