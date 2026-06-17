import base64
import sqlite3
import threading
import json
import os
import re
import tempfile
import time
import uuid
from pathlib import Path
from urllib import parse as urlparse
from urllib import request as urlrequest


def default_writable_path(filename: str) -> Path:
    preferred = Path("/var/lib/jarvis") / filename
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        with preferred.open("a", encoding="utf-8"):
            pass
        return preferred
    except OSError:
        fallback_dir = Path(tempfile.gettempdir()) / "jarvis"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        return fallback_dir / filename


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    owner_key TEXT NOT NULL,
    owner_user_id TEXT,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    pending_ha_action TEXT
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    text TEXT NOT NULL,
    ts INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id);
CREATE INDEX IF NOT EXISTS idx_ses_owner   ON sessions(owner_key);
CREATE INDEX IF NOT EXISTS idx_ses_updated ON sessions(updated_at DESC);
"""


class ChatHistoryStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_CHAT_HISTORY_PATH")
        if configured:
            db_path = Path(configured).with_suffix(".db")
        else:
            db_path = default_writable_path("chat_history.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db_path = str(db_path)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._migrate_json(configured)

    def _migrate_json(self, configured: str | None) -> None:
        if configured:
            json_path = Path(configured).with_suffix(".json")
        else:
            json_path = default_writable_path("chat_history.json")
        if not json_path.exists():
            return
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        sessions = data.get("sessions", {})
        if not sessions:
            return
        existing = {r[0] for r in self._conn.execute("SELECT id FROM sessions")}
        with self._lock:
            for sid, s in sessions.items():
                if sid in existing:
                    continue
                self._conn.execute(
                    "INSERT OR IGNORE INTO sessions(id,title,owner_key,owner_user_id,created_at,updated_at,pending_ha_action) VALUES(?,?,?,?,?,?,?)",
                    (sid, s.get("title","New chat"), s.get("owner_key","guest:anonymous"),
                     s.get("owner_user_id"), s.get("created_at",0), s.get("updated_at",0),
                     json.dumps(s["pending_home_assistant_action"]) if s.get("pending_home_assistant_action") else None),
                )
                for msg in s.get("messages", []):
                    self._conn.execute(
                        "INSERT INTO messages(session_id,role,text,ts) VALUES(?,?,?,?)",
                        (sid, msg.get("role","user"), msg.get("text",""), msg.get("ts",0)),
                    )
            self._conn.commit()
        json_path.rename(json_path.with_suffix(".json.migrated"))

    def _ex(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def _row_to_session(self, row: sqlite3.Row, messages: list[dict] | None = None) -> dict:
        pending = None
        if row["pending_ha_action"]:
            try:
                pending = json.loads(row["pending_ha_action"])
            except (json.JSONDecodeError, TypeError):
                pending = None
        return {
            "id": row["id"],
            "title": row["title"],
            "owner_key": row["owner_key"],
            "owner_user_id": row["owner_user_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "messages": messages if messages is not None else [],
            "pending_home_assistant_action": pending,
        }

    def create_session(self, title: str | None = None, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> dict:
        now = int(time.time())
        session_id = f"chat-{uuid.uuid4().hex[:12]}"
        clean_title = (title or "New chat").strip() or "New chat"
        with self._lock:
            self._ex(
                "INSERT INTO sessions(id,title,owner_key,owner_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                (session_id, clean_title, owner_key, owner_user_id, now, now),
            )
            self._conn.commit()
        return {"id": session_id, "title": clean_title, "owner_key": owner_key,
                "owner_user_id": owner_user_id, "created_at": now, "updated_at": now,
                "messages": [], "pending_home_assistant_action": None}

    def ensure_session(self, session_id: str | None, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> dict:
        if session_id:
            row = self._ex("SELECT * FROM sessions WHERE id=? AND owner_key=?", (session_id, owner_key)).fetchone()
            if row:
                return self._row_to_session(row)
        return self.create_session(owner_key=owner_key, owner_user_id=owner_user_id)

    def append_message(self, session_id: str, role: str, text: str, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> None:
        session = self.ensure_session(session_id, owner_key=owner_key, owner_user_id=owner_user_id)
        sid = session["id"]
        now = int(time.time())
        with self._lock:
            self._ex("INSERT INTO messages(session_id,role,text,ts) VALUES(?,?,?,?)", (sid, role, text, now))
            if role == "user":
                row = self._ex("SELECT title FROM sessions WHERE id=?", (sid,)).fetchone()
                if row and row["title"] == "New chat":
                    self._ex("UPDATE sessions SET title=?,updated_at=? WHERE id=?", (text[:50] or "New chat", now, sid))
                else:
                    self._ex("UPDATE sessions SET updated_at=? WHERE id=?", (now, sid))
            else:
                self._ex("UPDATE sessions SET updated_at=? WHERE id=?", (now, sid))
            self._conn.commit()

    def get_pending_home_assistant_action(self, session_id: str, owner_key: str = "guest:anonymous") -> dict | None:
        row = self._ex("SELECT pending_ha_action FROM sessions WHERE id=? AND owner_key=?", (session_id, owner_key)).fetchone()
        if not row or not row["pending_ha_action"]:
            return None
        try:
            val = json.loads(row["pending_ha_action"])
            return val if isinstance(val, dict) else None
        except (json.JSONDecodeError, TypeError):
            return None

    def set_pending_home_assistant_action(self, session_id: str, pending: dict | None, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> None:
        session = self.ensure_session(session_id, owner_key=owner_key, owner_user_id=owner_user_id)
        sid = session["id"]
        now = int(time.time())
        encoded = json.dumps(pending) if isinstance(pending, dict) else None
        with self._lock:
            self._ex("UPDATE sessions SET pending_ha_action=?,updated_at=? WHERE id=?", (encoded, now, sid))
            self._conn.commit()

    def clear_pending_home_assistant_action(self, session_id: str, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> None:
        self.set_pending_home_assistant_action(session_id, None, owner_key=owner_key, owner_user_id=owner_user_id)

    def list_sessions(self, owner_key: str = "guest:anonymous") -> list[dict]:
        rows = self._ex(
            "SELECT s.id, s.title, s.updated_at, s.created_at, COUNT(m.id) as message_count "
            "FROM sessions s LEFT JOIN messages m ON m.session_id=s.id "
            "WHERE s.owner_key=? GROUP BY s.id ORDER BY s.updated_at DESC",
            (owner_key,),
        ).fetchall()
        return [{"id": r["id"], "title": r["title"], "updated_at": r["updated_at"],
                 "created_at": r["created_at"], "message_count": r["message_count"]} for r in rows]

    def get_session(self, session_id: str, owner_key: str = "guest:anonymous") -> dict | None:
        row = self._ex("SELECT * FROM sessions WHERE id=? AND owner_key=?", (session_id, owner_key)).fetchone()
        if not row:
            return None
        msgs = self._ex("SELECT role,text,ts FROM messages WHERE session_id=? ORDER BY ts,id", (session_id,)).fetchall()
        messages = [{"role": m["role"], "text": m["text"], "ts": m["ts"]} for m in msgs]
        return self._row_to_session(row, messages)

    def search_messages(self, query: str, owner_key: str = "guest:anonymous", limit: int = 30) -> list[dict]:
        q = query.strip()
        if not q:
            return []
        rows = self._ex(
            "SELECT m.session_id, s.title, m.role, m.text, m.ts "
            "FROM messages m JOIN sessions s ON s.id=m.session_id "
            "WHERE s.owner_key=? AND m.text LIKE ? ESCAPE '\\' "
            "ORDER BY m.ts DESC LIMIT ?",
            (owner_key, f"%{q}%", limit),
        ).fetchall()
        results = []
        ql = q.lower()
        for r in rows:
            text = r["text"]
            idx = text.lower().find(ql)
            start = max(0, idx - 60)
            snippet = ("…" if start else "") + text[start:idx + len(q) + 60].replace("\n", " ")
            if start + len(snippet.lstrip("…")) < len(text):
                snippet += "…"
            results.append({"session_id": r["session_id"], "session_title": r["title"],
                             "role": r["role"], "snippet": snippet, "ts": r["ts"]})
        return results

    def delete_session(self, session_id: str, owner_key: str = "guest:anonymous") -> bool:
        with self._lock:
            cur = self._ex("DELETE FROM sessions WHERE id=? AND owner_key=?", (session_id, owner_key))
            self._conn.commit()
        return cur.rowcount > 0

    def delete_all_sessions(self, owner_key: str) -> int:
        with self._lock:
            cur = self._ex("DELETE FROM sessions WHERE owner_key=?", (owner_key,))
            self._conn.commit()
        return cur.rowcount

    def rename_session(self, session_id: str, title: str, owner_key: str = "guest:anonymous") -> dict | None:
        clean = (title or "").strip()[:80] or "New chat"
        now = int(time.time())
        with self._lock:
            cur = self._ex("UPDATE sessions SET title=?,updated_at=? WHERE id=? AND owner_key=?", (clean, now, session_id, owner_key))
            self._conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get_session(session_id, owner_key=owner_key)


class JarvisStatusHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._version = 0
        self._states: dict[str, dict[str, object]] = {}
        self._priority = ["recording", "processing", "speaking"]

    def begin(self, state: str, *, source: str = "", mode: str = "") -> str:
        token = uuid.uuid4().hex
        with self._lock:
            self._states[token] = {
                "state": state,
                "source": source,
                "mode": mode,
                "ts": time.time(),
            }
            self._version += 1
        return token

    def end(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            if token in self._states:
                self._states.pop(token, None)
                self._version += 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            active = list(self._states.values())
            counts: dict[str, int] = {}
            for item in active:
                state = str(item.get("state") or "idle")
                counts[state] = counts.get(state, 0) + 1
            current = "idle"
            for candidate in self._priority:
                if counts.get(candidate):
                    current = candidate
                    break
            return {
                "state": current,
                "version": self._version,
                "updated_at": time.time(),
                "active": len(active),
                "counts": counts,
            }


class RagStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_RAG_CACHE_PATH")
        self.path = Path(configured) if configured else default_writable_path("rag_cache.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"sources": {"wikijs": [], "github": []}, "updated_at": 0}

    def _load(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
            return {**self._empty(), **content}
        except (OSError, json.JSONDecodeError):
            return self._empty()

    def _save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass

    @staticmethod
    def _env_int(name: str, default: int, minimum: int = 1) -> int:
        raw = os.getenv(name)
        try:
            value = int(raw) if raw is not None else default
        except (TypeError, ValueError):
            value = default
        return max(minimum, value)

    @staticmethod
    def _allowed_github_extensions() -> set[str]:
        configured = (os.getenv("GITHUB_RAG_INCLUDE_EXTENSIONS") or "").strip()
        if configured:
            values = configured.split(",")
        else:
            values = [
                ".md", ".txt", ".rst",
                ".py", ".json", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".env",
                ".js", ".ts", ".tsx", ".jsx", ".html", ".css",
                ".sh",
            ]
        return {
            value.strip().lower() if value.strip().startswith(".") else f".{value.strip().lower()}"
            for value in values
            if value.strip()
        }

    @staticmethod
    def _is_github_text_path(path: str) -> bool:
        suffix = Path(path).suffix.lower()
        return suffix in RagStore._allowed_github_extensions()

    @staticmethod
    def _normalize_github_text(content: str, max_chars: int) -> str:
        normalized = re.sub(r"\s+", " ", (content or "").strip())
        return normalized[:max_chars].strip()

    def _decode_github_blob_text(self, blob: dict) -> str:
        if not isinstance(blob, dict):
            return ""
        if blob.get("encoding") == "base64":
            raw = (blob.get("content") or "").encode("utf-8")
            try:
                decoded = base64.b64decode(raw, validate=False).decode("utf-8", errors="ignore")
            except Exception:
                return ""
            return decoded
        if isinstance(blob.get("content"), str):
            return blob["content"]
        return ""

    def _http_json(self, url: str, method: str = "GET", headers: dict | None = None, payload: dict | None = None) -> dict:
        body = None
        hdrs = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        req = urlrequest.Request(url, data=body, headers=hdrs, method=method)
        with urlrequest.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw or "{}")

    def refresh(self) -> dict:
        report = {"wikijs": "skipped", "github": "skipped"}
        sources = {"wikijs": [], "github": []}

        wikijs_url = (os.getenv("WIKIJS_GRAPHQL_URL") or "").strip()
        wikijs_key = (os.getenv("WIKIJS_API_KEY") or "").strip()
        wikijs_query = os.getenv("WIKIJS_GRAPHQL_QUERY") or "query { pages { list(orderBy: TITLE) { title path description } } }"
        if wikijs_url and wikijs_key:
            try:
                resp = self._http_json(
                    wikijs_url,
                    method="POST",
                    headers={"Authorization": f"Bearer {wikijs_key}"},
                    payload={"query": wikijs_query},
                )
                raw_items = (((resp.get("data") or {}).get("pages") or {}).get("list") or [])
                for item in raw_items:
                    title = (item.get("title") or "").strip()
                    path = (item.get("path") or "").strip()
                    desc = (item.get("description") or "").strip()
                    text = " | ".join(x for x in [title, path, desc] if x)
                    if text:
                        sources["wikijs"].append({"title": title or path or "wiki", "text": text, "url": path})
                report["wikijs"] = f"ok ({len(sources['wikijs'])})"
            except Exception as exc:
                report["wikijs"] = f"error: {type(exc).__name__}"

        gh_repo = (os.getenv("GITHUB_REPO") or "").strip()
        gh_branch = (os.getenv("GITHUB_BRANCH") or "main").strip()
        gh_pat = (os.getenv("GITHUB_PAT") or "").strip()
        if gh_repo:
            try:
                headers = {"User-Agent": "jarvis-rag"}
                if gh_pat:
                    headers["Authorization"] = f"Bearer {gh_pat}"
                max_files = self._env_int("GITHUB_RAG_MAX_FILES", default=40, minimum=1)
                max_blob_chars = self._env_int("GITHUB_RAG_MAX_BLOB_CHARS", default=12000, minimum=20)
                tree_url = f"https://api.github.com/repos/{gh_repo}/git/trees/{gh_branch}?recursive=1"
                tree = self._http_json(tree_url, headers=headers)
                files = [item for item in tree.get("tree", []) if item.get("type") == "blob"]
                for item in files:
                    path = item.get("path", "")
                    if not path or not self._is_github_text_path(path):
                        continue
                    blob_url = (item.get("url") or "").strip()
                    if not blob_url:
                        continue
                    blob = self._http_json(blob_url, headers=headers)
                    text = self._normalize_github_text(self._decode_github_blob_text(blob), max_blob_chars)
                    if not text:
                        continue
                    sources["github"].append(
                        {
                            "title": path,
                            "text": text,
                            "url": f"https://github.com/{gh_repo}/blob/{gh_branch}/{urlparse.quote(path)}",
                            "path": path,
                            "repo": gh_repo,
                            "branch": gh_branch,
                            "sha": (blob.get("sha") or item.get("sha") or "").strip(),
                        }
                    )
                    if len(sources["github"]) >= max_files:
                        break
                report["github"] = f"ok ({len(sources['github'])})"
            except Exception as exc:
                report["github"] = f"error: {type(exc).__name__}"

        self.data = {"sources": sources, "updated_at": int(time.time()), "report": report}
        self._save()
        return report

    def search(self, query: str, limit: int = 5) -> list[dict]:
        q = (query or "").strip().lower()
        if not q:
            return []
        scored = []
        for source, items in (self.data.get("sources") or {}).items():
            for item in items:
                hay = f"{item.get('title','')} {item.get('text','')}".lower()
                score = 0
                for token in q.split():
                    if token in hay:
                        score += 1
                if score:
                    scored.append((score, {**item, "source": source}))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]
