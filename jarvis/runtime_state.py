import base64
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


class ChatHistoryStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_CHAT_HISTORY_PATH")
        self.path = Path(configured) if configured else default_writable_path("chat_history.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data = self._load()

    def _empty(self) -> dict:
        return {"sessions": {}}

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

    def create_session(self, title: str | None = None, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> dict:
        now = int(time.time())
        session_id = f"chat-{uuid.uuid4().hex[:12]}"
        item = {
            "id": session_id,
            "title": (title or "New chat").strip() or "New chat",
            "created_at": now,
            "updated_at": now,
            "owner_key": owner_key,
            "owner_user_id": owner_user_id,
            "messages": [],
            "pending_home_assistant_action": None,
        }
        self.data.setdefault("sessions", {})[session_id] = item
        self._save()
        return item

    def ensure_session(self, session_id: str | None, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> dict:
        if session_id and session_id in self.data.get("sessions", {}):
            session = self.data["sessions"][session_id]
            if session.get("owner_key") == owner_key:
                return session
        return self.create_session(owner_key=owner_key, owner_user_id=owner_user_id)

    def append_message(self, session_id: str, role: str, text: str, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> None:
        session = self.ensure_session(session_id, owner_key=owner_key, owner_user_id=owner_user_id)
        now = int(time.time())
        session.setdefault("messages", []).append({"role": role, "text": text, "ts": now})
        session["updated_at"] = now
        if role == "user" and session.get("title", "New chat") == "New chat":
            session["title"] = text[:50] or "New chat"
        self.data.setdefault("sessions", {})[session["id"]] = session
        self._save()

    def get_pending_home_assistant_action(self, session_id: str, owner_key: str = "guest:anonymous") -> dict | None:
        session = self.get_session(session_id, owner_key=owner_key)
        if not session:
            return None
        pending = session.get("pending_home_assistant_action")
        return pending if isinstance(pending, dict) else None

    def set_pending_home_assistant_action(self, session_id: str, pending: dict | None, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> None:
        session = self.ensure_session(session_id, owner_key=owner_key, owner_user_id=owner_user_id)
        session["pending_home_assistant_action"] = pending if isinstance(pending, dict) else None
        session["updated_at"] = int(time.time())
        self.data.setdefault("sessions", {})[session["id"]] = session
        self._save()

    def clear_pending_home_assistant_action(self, session_id: str, owner_key: str = "guest:anonymous", owner_user_id: str | None = None) -> None:
        self.set_pending_home_assistant_action(session_id, None, owner_key=owner_key, owner_user_id=owner_user_id)

    def list_sessions(self, owner_key: str = "guest:anonymous") -> list[dict]:
        sessions = [s for s in self.data.get("sessions", {}).values() if s.get("owner_key") == owner_key]
        sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return [{
            "id": s.get("id", ""),
            "title": s.get("title", "New chat"),
            "updated_at": s.get("updated_at", 0),
            "created_at": s.get("created_at", 0),
            "message_count": len(s.get("messages", [])),
        } for s in sessions]

    def get_session(self, session_id: str, owner_key: str = "guest:anonymous") -> dict | None:
        session = self.data.get("sessions", {}).get(session_id)
        if not session or session.get("owner_key") != owner_key:
            return None
        return session

    def delete_session(self, session_id: str, owner_key: str = "guest:anonymous") -> bool:
        sessions = self.data.setdefault("sessions", {})
        if session_id not in sessions or sessions[session_id].get("owner_key") != owner_key:
            return False
        sessions.pop(session_id, None)
        self._save()
        return True

    def rename_session(self, session_id: str, title: str, owner_key: str = "guest:anonymous") -> dict | None:
        session = self.get_session(session_id, owner_key=owner_key)
        if not session:
            return None
        clean = (title or "").strip()[:80] or "New chat"
        session["title"] = clean
        session["updated_at"] = int(time.time())
        self.data.setdefault("sessions", {})[session_id] = session
        self._save()
        return session


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
