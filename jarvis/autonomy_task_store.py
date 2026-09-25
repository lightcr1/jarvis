"""Owner-managed autonomy backlog (task queue) and structured round reports.

The agent may *propose* tasks and *report* round outcomes, but cannot approve
its own proposals or mark work done. This store contains no credentials and
never executes anything.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

VALID_STATUSES = frozenset(
    {"proposed", "open", "in_progress", "submitted", "done", "blocked", "rejected"}
)
VALID_SIZES = frozenset({"small", "medium"})
VALID_SOURCES = frozenset({"owner", "agent", "issue"})
VALID_OUTCOMES = frozenset({"done", "partial", "blocked", "no_change", "submitted", "unknown"})
MAX_TASK_ATTEMPTS = 3

# Agent proposals without owner review are capped like ideas (anti-spam).
AGENT_PROPOSAL_LIMIT = 3
AGENT_PROPOSAL_WINDOW_S = 24 * 3600


def _clean(value: str, *, limit: int, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{field} required")
    if len(value) > limit or any(c in value for c in ("\0", "\r")):
        raise ValueError(f"{field} invalid (max {limit} characters)")
    return value


def validate_text_list(value, *, field: str, limit: int = 100) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{field} must be a list (max {limit})")
    items = []
    for item in value:
        if not isinstance(item, str) or len(item) > 300 or any(c in item for c in ("\0", "\r")):
            raise ValueError(f"{field} entries invalid")
        items.append(item)
    return items


class AutonomyTaskStore:
    def __init__(self, path: str | Path | None = None, *, clock=None):
        self.path = Path(path or os.getenv("JARVIS_AUTONOMY_TASKS_PATH",
                                           "/var/lib/jarvis/autonomy_tasks.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self.clock = clock or time.time
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS autonomy_tasks (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL,
                area TEXT NOT NULL, size TEXT NOT NULL, priority INTEGER NOT NULL,
                status TEXT NOT NULL, source TEXT NOT NULL, attempts INTEGER NOT NULL,
                last_round_id TEXT, escalated INTEGER NOT NULL DEFAULT 0,
                external_id TEXT, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            )""")
            self._migrate(db)
            db.execute("CREATE INDEX IF NOT EXISTS autonomy_tasks_status ON autonomy_tasks(status,priority)")
            db.execute("""CREATE TABLE IF NOT EXISTS round_reports (
                id TEXT PRIMARY KEY, task_id TEXT, round_id TEXT, outcome TEXT NOT NULL,
                summary TEXT NOT NULL, branch TEXT NOT NULL, files_changed TEXT NOT NULL,
                tests TEXT NOT NULL, next_step TEXT NOT NULL, owner_question TEXT NOT NULL,
                created_at INTEGER NOT NULL
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS round_reports_task ON round_reports(task_id,created_at)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _migrate(db) -> None:
        """Add columns introduced after the first schema without data loss."""
        columns = {row[1] for row in db.execute("PRAGMA table_info(autonomy_tasks)")}
        if "escalated" not in columns:
            db.execute("ALTER TABLE autonomy_tasks ADD COLUMN escalated INTEGER NOT NULL DEFAULT 0")
        if "external_id" not in columns:
            db.execute("ALTER TABLE autonomy_tasks ADD COLUMN external_id TEXT")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS autonomy_tasks_external ON autonomy_tasks(external_id)")

    def find_by_external(self, external_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM autonomy_tasks WHERE external_id=?", (external_id,)).fetchone()
        return dict(row) if row else None

    # -- tasks -----------------------------------------------------------

    def create_task(self, *, title: str, description: str = "", area: str = "",
                    size: str = "medium", priority: int = 100, source: str = "owner",
                    status: str = "open", external_id: str | None = None) -> dict:
        title = _clean(title, limit=140, field="title")
        description = description or ""
        if description and (description != description.strip() or len(description) > 4000
                            or any(c in description for c in ("\0", "\r"))):
            raise ValueError("description invalid (max 4000 characters)")
        area = area or "general"
        if area != area.strip() or len(area) > 40 or any(c in area for c in ("\0", "\r", "/")):
            raise ValueError("area invalid (max 40 characters)")
        if size not in VALID_SIZES:
            raise ValueError("size must be small or medium")
        if source not in VALID_SOURCES:
            raise ValueError("invalid source")
        if status not in VALID_STATUSES:
            raise ValueError("invalid status")
        if not isinstance(priority, int) or not 0 <= priority <= 10000:
            raise ValueError("priority must be 0..10000")
        now = int(self.clock())
        identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO autonomy_tasks
                (id,title,description,area,size,priority,status,source,attempts,
                 last_round_id,external_id,created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (identifier, title, description, area, size, priority, status, source,
                 0, None, external_id, now, now))
        return self.get_task(identifier)

    def propose_task(self, *, title: str, description: str = "", area: str = "",
                     size: str = "medium") -> dict:
        """Agent proposal: owner must approve before it counts as open work."""
        now = int(self.clock())
        with self._connect() as db:
            count = db.execute(
                "SELECT count(*) FROM autonomy_tasks WHERE source='agent' AND status='proposed' AND created_at>?",
                (now - AGENT_PROPOSAL_WINDOW_S,)).fetchone()[0]
        if count >= AGENT_PROPOSAL_LIMIT:
            raise ValueError("agent proposal limit reached; owner review required")
        return self.create_task(title=title, description=description, area=area,
                                size=size, source="agent", status="proposed")

    def get_task(self, task_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM autonomy_tasks WHERE id=?", (task_id,)).fetchone()
        return dict(row) if row else None

    def list_tasks(self, *, status: str | None = None, area: str | None = None,
                   limit: int = 200) -> list[dict]:
        query = "SELECT * FROM autonomy_tasks"
        where, params = [], []
        if status:
            where.append("status=?"); params.append(status)
        if area:
            where.append("area=?"); params.append(area)
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY priority DESC, created_at ASC, id ASC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def update_task(self, task_id: str, *, title: str | None = None,
                    description: str | None = None, area: str | None = None,
                    size: str | None = None, priority: int | None = None,
                    status: str | None = None) -> dict | None:
        fields: dict[str, object] = {}
        if title is not None:
            fields["title"] = _clean(title, limit=140, field="title")
        if description is not None:
            if len(description) > 4000 or any(c in description for c in ("\0", "\r")):
                raise ValueError("description invalid (max 4000 characters)")
            fields["description"] = description
        if area is not None:
            if not area or area != area.strip() or len(area) > 40 or "/" in area:
                raise ValueError("area invalid")
            fields["area"] = area
        if size is not None:
            if size not in VALID_SIZES:
                raise ValueError("size must be small or medium")
            fields["size"] = size
        if priority is not None:
            if not isinstance(priority, int) or not 0 <= priority <= 10000:
                raise ValueError("priority must be 0..10000")
            fields["priority"] = priority
        if status is not None:
            if status not in VALID_STATUSES:
                raise ValueError("invalid status")
            fields["status"] = status
        if not fields:
            return self.get_task(task_id)
        fields["updated_at"] = int(self.clock())
        columns = ", ".join(f"{name}=?" for name in fields)
        with self._connect() as db:
            db.execute(f"UPDATE autonomy_tasks SET {columns} WHERE id=?",
                       (*fields.values(), task_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_task(task_id) if changed else None

    def decide_task(self, task_id: str, *, actor: str, approve: bool) -> dict | None:
        new_status = "open" if approve else "rejected"
        with self._connect() as db:
            db.execute("""UPDATE autonomy_tasks SET status=?, updated_at=?
                WHERE id=? AND status='proposed'""",
                (new_status, int(self.clock()), task_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_task(task_id) if changed else None

    def next_open_task(self, *, area: str | None = None,
                       exclude_ids: set[str] | None = None,
                       exclude_areas: set[str] | None = None) -> dict | None:
        """Höchstpriorisierte offene Aufgabe; optionaler Bereichsfilter (3.3).

        ``exclude_areas`` verhindert, dass zwei parallele Runden denselben
        Bereich bearbeiten.
        """
        excluded = set(exclude_ids or ())
        blocked_areas = set(exclude_areas or ())
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM autonomy_tasks
                WHERE status='open' AND escalated=0
                ORDER BY priority DESC, created_at ASC, id ASC LIMIT 50""").fetchall()
        for row in rows:
            task = dict(row)
            if task["id"] in excluded:
                continue
            if area and task["area"] not in (area, "general"):
                continue
            if task["area"] in blocked_areas and task["area"] != "general":
                continue
            return task
        return None

    def claim_task(self, task_id: str, *, round_id: str) -> dict | None:
        """Atomically open -> in_progress; escalates to blocked after MAX_TASK_ATTEMPTS."""
        now = int(self.clock())
        with self._connect() as db:
            row = db.execute("SELECT * FROM autonomy_tasks WHERE id=?", (task_id,)).fetchone()
            if row is None or row["status"] != "open":
                return None
            if row["attempts"] >= MAX_TASK_ATTEMPTS:
                db.execute("UPDATE autonomy_tasks SET status='blocked', updated_at=? WHERE id=? AND status='open'",
                           (now, task_id))
                return self.get_task(task_id)
            db.execute("""UPDATE autonomy_tasks SET status='in_progress', attempts=attempts+1,
                last_round_id=?, updated_at=? WHERE id=? AND status='open'""",
                (round_id, now, task_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_task(task_id) if changed else None

    # -- round reports ---------------------------------------------------

    def record_report(self, *, task_id: str | None, round_id: str, outcome: str,
                      summary: str, branch: str = "", files_changed=None,
                      tests=None, next_step: str = "", owner_question: str = "") -> dict:
        if outcome not in VALID_OUTCOMES:
            raise ValueError("invalid outcome")
        summary = _clean(summary[:800], limit=800, field="summary")
        branch = (branch or "")[:200]
        next_step = (next_step or "")[:800]
        owner_question = (owner_question or "")[:800]
        files = validate_text_list(files_changed, field="files_changed")
        test_list = validate_text_list(tests, field="tests", limit=50)
        now = int(self.clock())
        identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO round_reports
                (id,task_id,round_id,outcome,summary,branch,files_changed,tests,
                 next_step,owner_question,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (identifier, task_id, round_id, outcome, summary, branch,
                 json.dumps(files), json.dumps(test_list), next_step, owner_question, now))
            if task_id:
                self._apply_outcome(db, task_id, outcome, now)
        return self.get_report(identifier)

    @staticmethod
    def _apply_outcome(db, task_id: str, outcome: str, now: int) -> None:
        row = db.execute("SELECT attempts FROM autonomy_tasks WHERE id=?", (task_id,)).fetchone()
        attempts = int(row["attempts"]) if row else 0
        if outcome == "done":
            status = "done"
        elif outcome == "submitted":
            status = "submitted"
        elif outcome == "blocked":
            status = "blocked"
        else:
            status = "blocked" if attempts >= MAX_TASK_ATTEMPTS else "open"
        # 7.6: wiederholtes Scheitern -> fuer ein staerkeres Modell markieren.
        escalated = 1 if (outcome in ("no_change", "blocked") and attempts >= 2) else 0
        db.execute("UPDATE autonomy_tasks SET status=?, escalated=?, updated_at=? WHERE id=?",
                   (status, escalated, now, task_id))

    def review_task(self, task_id: str, *, actor: str, decision: str) -> dict | None:
        """7.7: Ergebnis eines Agenten-PRs (merged/rejected) in die Aufgabe schreiben."""
        if decision not in ("merged", "rejected"):
            raise ValueError("decision must be merged or rejected")
        status = "done" if decision == "merged" else "rejected"
        with self._connect() as db:
            db.execute("""UPDATE autonomy_tasks SET status=?, escalated=0, updated_at=?
                WHERE id=?""", (status, int(self.clock()), task_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_task(task_id) if changed else None

    def area_success_rates(self) -> dict[str, dict]:
        """Erfolgsquote pro Bereich (done / abgeschlossen) fuer Discovery (7.7)."""
        with self._connect() as db:
            rows = db.execute("""SELECT area,
                sum(CASE WHEN status='done' THEN 1 ELSE 0 END) AS done,
                sum(CASE WHEN status IN ('done','rejected','blocked') THEN 1 ELSE 0 END) AS closed,
                count(*) AS total
                FROM autonomy_tasks GROUP BY area""").fetchall()
        result = {}
        for row in rows:
            closed = int(row["closed"])
            result[row["area"]] = {
                "done": int(row["done"]),
                "closed": closed,
                "total": int(row["total"]),
                "success_rate": round(int(row["done"]) / closed, 3) if closed else None,
            }
        return result

    def get_report(self, report_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM round_reports WHERE id=?", (report_id,)).fetchone()
        return self._decode_report(row) if row else None

    def last_report(self, task_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("""SELECT * FROM round_reports WHERE task_id=?
                ORDER BY created_at DESC, rowid DESC LIMIT 1""", (task_id,)).fetchone()
        return self._decode_report(row) if row else None

    def list_reports(self, *, task_id: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM round_reports"
        params: list = []
        if task_id:
            query += " WHERE task_id=?"; params.append(task_id)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._decode_report(row) for row in rows]

    @staticmethod
    def _decode_report(row) -> dict:
        report = dict(row)
        report["files_changed"] = json.loads(report.get("files_changed") or "[]")
        report["tests"] = json.loads(report.get("tests") or "[]")
        return report

    def daily_summary(self, *, since: int | None = None, now: int | None = None) -> dict:
        """Kurzer, TTS-tauglicher Report der letzten 24h (7.4)."""
        current = int(self.clock() if now is None else now)
        since = current - 24 * 3600 if since is None else int(since)
        with self._connect() as db:
            rows = db.execute("""SELECT outcome, summary FROM round_reports
                WHERE created_at>=? ORDER BY created_at DESC, rowid DESC""", (since,)).fetchall()
            task_rows = db.execute("SELECT status, count(*) AS c FROM autonomy_tasks GROUP BY status").fetchall()
        outcomes: dict[str, int] = {}
        for row in rows:
            outcomes[row["outcome"]] = outcomes.get(row["outcome"], 0) + 1
        return {
            "rounds": len(rows),
            "outcomes": outcomes,
            "latest": str(rows[0]["summary"]) if rows else "",
            "tasks_by_status": {row["status"]: int(row["c"]) for row in task_rows},
        }
