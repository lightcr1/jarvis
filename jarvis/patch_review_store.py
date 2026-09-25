"""Review queue for agent patch submissions (4.1 -> 7.2).

Stores the patch text and metadata so the owner can review the diff in the
admin UI and then create the PR or reject it. Contains no credentials.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

VALID_STATUSES = frozenset({"pending", "pr_requested", "rejected"})


class PatchReviewStore:
    def __init__(self, path: str | Path | None = None, *, clock=None):
        self.path = Path(path or os.getenv("JARVIS_PATCH_REVIEW_PATH",
                                           "/var/lib/jarvis/patch_review.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        self.clock = clock or time.time
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS patch_submissions (
                id TEXT PRIMARY KEY, repository TEXT NOT NULL, branch TEXT NOT NULL,
                base TEXT NOT NULL, commit_sha TEXT NOT NULL, message TEXT NOT NULL,
                patch TEXT NOT NULL, paths TEXT NOT NULL, status TEXT NOT NULL,
                pr_number INTEGER, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            )""")

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def record(self, *, repository: str, branch: str, base: str, commit: str,
               message: str, patch: str, paths: list[str]) -> dict:
        if not repository or not branch or not commit:
            raise ValueError("repository, branch and commit required")
        if len(patch.encode()) > 1024 * 1024:
            raise ValueError("patch too large")
        now = int(self.clock())
        identifier = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("""INSERT INTO patch_submissions
                (id,repository,branch,base,commit_sha,message,patch,paths,status,pr_number,
                 created_at,updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (identifier, repository, branch, base, commit, message[:200], patch,
                 json.dumps(list(paths)), "pending", None, now, now))
        return self.get(identifier)

    def get(self, patch_id: str) -> dict | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM patch_submissions WHERE id=?", (patch_id,)).fetchone()
        return self._decode(row) if row else None

    def list(self, *, status: str | None = None, limit: int = 100) -> list[dict]:
        query = "SELECT * FROM patch_submissions"
        params: list = []
        if status:
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
        params.append(max(1, min(limit, 500)))
        with self._connect() as db:
            rows = db.execute(query, params).fetchall()
        return [self._decode(row) for row in rows]

    def decide(self, patch_id: str, *, actor: str, decision: str,
               pr_number: int | None = None) -> dict | None:
        if decision not in ("pr_requested", "rejected"):
            raise ValueError("decision must be pr_requested or rejected")
        with self._connect() as db:
            db.execute("""UPDATE patch_submissions SET status=?, pr_number=?, updated_at=?
                WHERE id=? AND status='pending'""",
                (decision, pr_number, int(self.clock()), patch_id))
            changed = db.execute("SELECT changes()").fetchone()[0]
        return self.get(patch_id) if changed else None

    @staticmethod
    def _decode(row) -> dict:
        item = dict(row)
        item["commit"] = item.pop("commit_sha", None)
        item["paths"] = json.loads(item.get("paths") or "[]")
        return item
