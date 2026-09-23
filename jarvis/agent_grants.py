"""Owner-managed, scoped agent grants. Not a substitute for tool-side enforcement.

The agent can submit requests, but cannot approve them. This store deliberately
contains no credentials and never executes an action. Tool gateways must call
``authorize`` with their OWN trusted action/target classification before effects.
"""
from __future__ import annotations

import os
import sqlite3
import time
import uuid
from pathlib import Path

# These categories require separate, action-specific human confirmation in the
# actual tool gateway. A grant here never authorizes them.
RESERVED = frozenset({"payment", "billing", "purchase", "contract", "publish", "external_message",
                      "delete", "security", "credentials", "policy", "runpod", "deployment"})
SAFE_KINDS = frozenset({"repository", "integration", "workspace", "business_research", "other_project"})


class AgentGrantStore:
    def __init__(self, path: str | Path | None = None, *, clock=None):
        self.path = Path(path or os.getenv("JARVIS_AGENT_GRANTS_PATH", "/var/lib/jarvis/agent_grants.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self.clock = clock or time.time
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL,
                operation TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
                created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                decided_at INTEGER, decided_by TEXT, revoked_at INTEGER
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS grants_lookup ON requests(kind,target,operation,status)")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    @staticmethod
    def _validate(kind: str, target: str, operation: str) -> None:
        if kind not in SAFE_KINDS:
            raise ValueError("unsupported project kind")
        # Exact names only; wildcards, URL wildcards, and control characters are forbidden.
        for value in (target, operation):
            if not value or value != value.strip() or len(value) > 180 or any(
                c in value for c in ("*", "?", "\n", "\r", "\0")
            ):
                raise ValueError("specific target and operation required")
        if operation.lower() in RESERVED or any(piece in RESERVED for piece in operation.lower().replace("-", "_").split(".")):
            raise ValueError("reserved action requires separate authorization")

    def request(self, *, kind: str, target: str, operation: str, reason: str,
                duration_seconds: int = 3600) -> dict:
        self._validate(kind, target, operation)
        if not reason.strip() or len(reason) > 1000:
            raise ValueError("reason required (max 1000 characters)")
        if not 60 <= duration_seconds <= 30 * 24 * 3600:
            raise ValueError("duration outside allowed range")
        now = int(self.clock())
        entry = (uuid.uuid4().hex, kind, target, operation, reason.strip(), "pending",
                 now, now + duration_seconds)
        with self._connect() as db:
            db.execute("""INSERT INTO requests
                (id,kind,target,operation,reason,status,created_at,expires_at)
                VALUES (?,?,?,?,?,?,?,?)""", entry)
        return self.get(entry[0])

    def get(self, request_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def list_requests(self, limit: int = 100) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM requests ORDER BY created_at DESC, id DESC LIMIT ?",
                              (max(1, min(limit, 200)),)).fetchall()
        return [dict(row) for row in rows]

    def decide(self, request_id: str, *, actor: str, approve: bool) -> dict | None:
        now = int(self.clock())
        with self._connect() as db:
            db.execute("""UPDATE requests SET status=?, decided_at=?, decided_by=?
                WHERE id=? AND status='pending' AND expires_at>?""",
                ("approved" if approve else "rejected", now, actor, request_id, now))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get(request_id) if changed else None

    def revoke(self, request_id: str, *, actor: str) -> dict | None:
        now = int(self.clock())
        with self._connect() as db:
            db.execute("""UPDATE requests SET status='revoked', revoked_at=?, decided_by=?
                WHERE id=? AND status='approved'""", (now, actor, request_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get(request_id) if changed else None

    def authorize(self, *, kind: str, target: str, operation: str) -> bool:
        """Fail closed. Never pass untrusted agent classification to a real tool."""
        try:
            self._validate(kind, target, operation)
        except ValueError:
            return False
        with self._connect() as db:
            row = db.execute("""SELECT 1 FROM requests WHERE kind=? AND target=?
                AND operation=? AND status='approved' AND expires_at>? LIMIT 1""",
                (kind, target, operation, int(self.clock()))).fetchone()
        return row is not None
