"""Woechentliche Messgroessen fuer den Assistenten (Plan Abschnitt 6.1).

Rein rechnend und damit testbar: bekommt fertige Listen (Aufgaben, Rundenberichte,
Freigabe-Anfragen) und liefert die Kennzahlen des Plans -- gemessen aus den
vorhandenen Stores, nicht geschaetzt.
"""
from __future__ import annotations

from collections import Counter


def summarize(tasks, reports, approvals=None, *, gpu_seconds: float = 0.0,
              frequent_yes_threshold: int = 3) -> dict:
    tasks = list(tasks or [])
    reports = list(reports or [])
    approvals = list(approvals or [])

    total = len(tasks)
    done = sum(1 for t in tasks if t.get("status") == "done")
    blocked = sum(1 for t in tasks if t.get("status") == "blocked")

    report_total = len(reports)
    blocked_reports = sum(1 for r in reports if r.get("outcome") == "blocked")

    approved = [a for a in approvals if a.get("status") == "approved"]
    rejected = [a for a in approvals if a.get("status") == "rejected"]
    pending = [a for a in approvals if a.get("status") == "pending"]

    # Haeufige Ja-Antworten ohne Ablehnung -> Kandidat fuer stehende Freigabe (6.1).
    yes = Counter(a.get("capability") for a in approved if not a.get("always"))
    no = Counter(a.get("capability") for a in rejected)
    suggestions = sorted(
        cap for cap, count in yes.items()
        if cap and count >= frequent_yes_threshold and no.get(cap, 0) == 0
    )

    gpu_seconds = float(gpu_seconds or 0.0)
    return {
        "tasks": {"total": total, "done": done, "blocked": blocked,
                  "done_rate": round(done / total, 3) if total else 0.0},
        "rounds": {"reports": report_total, "blocked": blocked_reports,
                   "blocked_rate": round(blocked_reports / report_total, 3) if report_total else 0.0},
        "approvals": {"asked": len(approvals), "approved": len(approved),
                      "rejected": len(rejected), "pending": len(pending)},
        "gpu_seconds": round(gpu_seconds, 1),
        "done_per_gpu_hour": round(done / (gpu_seconds / 3600), 3) if gpu_seconds else 0.0,
        "standing_grant_suggestions": suggestions,
    }


def weekly_metrics(task_store, grant_store=None, *, gpu_seconds: float = 0.0) -> dict:
    """Kennzahlen direkt aus den Stores ziehen (Aufgaben, Berichte, Freigaben)."""
    approvals = grant_store.list_approvals(status=None) if grant_store is not None else []
    return summarize(task_store.list_tasks(), task_store.list_reports(), approvals,
                     gpu_seconds=gpu_seconds)
