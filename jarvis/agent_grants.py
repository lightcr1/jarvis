"""Owner-managed, scoped agent grants. Not a substitute for tool-side enforcement.

The agent can submit requests, but cannot approve them. This store deliberately
contains no credentials and never executes an action. Tool gateways must call
``authorize`` with their OWN trusted action/target classification before effects.
"""
from __future__ import annotations

import hashlib
import json
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
            db.execute("""CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL,
                title TEXT NOT NULL, operations TEXT NOT NULL, status TEXT NOT NULL,
                created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                decided_at INTEGER, decided_by TEXT, revoked_at INTEGER
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS one_time_actions (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, target TEXT NOT NULL,
                payload TEXT NOT NULL, digest TEXT NOT NULL, status TEXT NOT NULL,
                created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                decided_at INTEGER, decided_by TEXT, consumed_at INTEGER
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS ideas (
                id TEXT PRIMARY KEY, source TEXT NOT NULL, kind TEXT NOT NULL,
                title TEXT NOT NULL, summary TEXT NOT NULL, benefit TEXT NOT NULL,
                risks TEXT NOT NULL, next_step TEXT NOT NULL,
                status TEXT NOT NULL, created_at INTEGER NOT NULL,
                reviewed_at INTEGER, reviewed_by TEXT
            )""")

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

    def propose_idea(self, *, source: str, kind: str, title: str, summary: str,
                     benefit: str, risks: str, next_step: str) -> dict:
        """Create a proposal, never a tool grant or a project execution mandate."""
        if source not in {"owner", "agent"} or kind not in {"business", "platform", "integration", "other_project"}:
            raise ValueError("invalid idea source or kind")
        fields = (title, summary, benefit, risks, next_step)
        if any(not value.strip() or value != value.strip() or len(value) > 2000 or
               any(c in value for c in ("\0", "\r")) for value in fields) or len(title) > 140:
            raise ValueError("complete, bounded proposal required")
        now = int(self.clock())
        with self._connect() as db:
            if source == "agent":
                # Avoid infinite autonomous idea generation when no useful work exists.
                count = db.execute("SELECT count(*) FROM ideas WHERE source='agent' AND status='proposed'\n"
                                   "AND created_at>?", (now - 24 * 3600,)).fetchone()[0]
                if count >= 3:
                    raise ValueError("agent proposal limit reached; review existing ideas first")
            identifier = uuid.uuid4().hex
            db.execute("""INSERT INTO ideas
                (id,source,kind,title,summary,benefit,risks,next_step,status,created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (identifier, source, kind, title, summary, benefit, risks, next_step, "proposed", now))
        return self.get_idea(identifier)

    def get_idea(self, idea_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM ideas WHERE id=?", (idea_id,)).fetchone()
        return dict(row) if row else None

    def list_ideas(self, limit: int = 100) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("""SELECT * FROM ideas ORDER BY
                CASE WHEN status='proposed' THEN 0 ELSE 1 END,
                CASE WHEN source='owner' THEN 0 ELSE 1 END,
                created_at DESC LIMIT ?""", (max(1, min(limit, 200)),)).fetchall()
        return [dict(row) for row in rows]

    def review_idea(self, idea_id: str, *, actor: str, status: str) -> dict | None:
        if status not in {"shortlisted", "dismissed"}:
            raise ValueError("invalid review status")
        with self._connect() as db:
            db.execute("""UPDATE ideas SET status=?, reviewed_at=?, reviewed_by=?
                WHERE id=? AND status='proposed'""", (status, int(self.clock()), actor, idea_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_idea(idea_id) if changed else None

    def request_project(self, *, kind: str, target: str, title: str,
                        operations: list[str], duration_seconds: int = 7 * 24 * 3600) -> dict:
        if not title.strip() or len(title) > 200 or not operations or len(operations) > 20:
            raise ValueError("bounded project title and operations required")
        normalized = sorted(set(operations))
        for operation in normalized:
            self._validate(kind, target, operation)
        if not 3600 <= duration_seconds <= 30 * 24 * 3600:
            raise ValueError("project duration outside allowed range")
        now = int(self.clock()); identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO projects
                (id,kind,target,title,operations,status,created_at,expires_at)
                VALUES (?,?,?,?,?,'pending',?,?)""",
                (identifier, kind, target, title.strip(), json.dumps(normalized), now, now + duration_seconds))
        return self.get_project(identifier)

    def get_project(self, identifier: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM projects WHERE id=?", (identifier,)).fetchone()
        return dict(row) if row else None

    def list_projects(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM projects ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]

    def decide_project(self, identifier: str, *, actor: str, approve: bool) -> dict | None:
        now = int(self.clock())
        with self._connect() as db:
            db.execute("""UPDATE projects SET status=?, decided_at=?, decided_by=?
                WHERE id=? AND status='pending' AND expires_at>?""",
                ("approved" if approve else "rejected", now, actor, identifier, now))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_project(identifier) if changed else None

    def revoke_project(self, identifier: str, *, actor: str) -> dict | None:
        now = int(self.clock())
        with self._connect() as db:
            db.execute("""UPDATE projects SET status='revoked', revoked_at=?, decided_by=?
                WHERE id=? AND status='approved'""", (now, actor, identifier))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_project(identifier) if changed else None

    @staticmethod
    def _action_digest(kind: str, target: str, payload: dict) -> tuple[str, str]:
        encoded = json.dumps({"kind": kind, "target": target, "payload": payload},
                             ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")), hashlib.sha256(encoded.encode()).hexdigest()

    def request_one_time_action(self, *, kind: str, target: str, payload: dict) -> dict:
        if kind != "github_create_pr" or not isinstance(payload, dict):
            raise ValueError("unsupported one-time action")
        from .github_gateway import canonical_repo, validate_pull_request
        owner, repository = target.split("/", 1) if target.count("/") == 1 else ("", "")
        if canonical_repo(owner, repository) != target:
            raise ValueError("canonical target required")
        validate_pull_request(payload)
        body, digest = self._action_digest(kind, target, payload)
        now = int(self.clock())
        identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO one_time_actions
                (id,kind,target,payload,digest,status,created_at,expires_at)
                VALUES (?,?,?,?,?,'pending',?,?)""", (identifier, kind, target, body, digest, now, now + 24 * 3600))
        return self.get_one_time_action(identifier)

    def get_one_time_action(self, identifier: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM one_time_actions WHERE id=?", (identifier,)).fetchone()
        return dict(row) if row else None

    def list_one_time_actions(self) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM one_time_actions ORDER BY created_at DESC LIMIT 100").fetchall()
        return [dict(row) for row in rows]

    def decide_one_time_action(self, identifier: str, *, actor: str, approve: bool) -> dict | None:
        now = int(self.clock())
        with self._connect() as db:
            db.execute("""UPDATE one_time_actions SET status=?, decided_at=?, decided_by=?
                WHERE id=? AND status='pending' AND expires_at>?""",
                ("approved" if approve else "rejected", now, actor, identifier, now))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get_one_time_action(identifier) if changed else None

    def consume_one_time_action(self, identifier: str) -> dict | None:
        """Claim atomically before any external effect. A failed call needs new approval."""
        now = int(self.clock())
        with self._connect() as db:
            db.execute("""UPDATE one_time_actions SET status='consumed', consumed_at=?
                WHERE id=? AND status='approved' AND expires_at>?""", (now, identifier, now))
            changed = db.execute("SELECT changes()").fetchone()[0]
        if not changed:
            return None
        item = self.get_one_time_action(identifier)
        assert item is not None
        payload = json.loads(item["payload"])
        _, digest = self._action_digest(item["kind"], item["target"], payload)
        if digest != item["digest"]:
            raise ValueError("action digest mismatch")
        return item

    def authorize(self, *, kind: str, target: str, operation: str) -> bool:
        """Fail closed. Never pass untrusted agent classification to a real tool."""
        try:
            self._validate(kind, target, operation)
        except ValueError:
            return False
        now = int(self.clock())
        with self._connect() as db:
            row = db.execute("""SELECT 1 FROM requests WHERE kind=? AND target=?
                AND operation=? AND status='approved' AND expires_at>? LIMIT 1""",
                (kind, target, operation, now)).fetchone()
            if row is not None:
                return True
            projects = db.execute("""SELECT operations FROM projects WHERE kind=? AND target=?
                AND status='approved' AND expires_at>?""", (kind, target, now)).fetchall()
        return any(operation in json.loads(project["operations"]) for project in projects)
