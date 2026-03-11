import base64
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from openai import OpenAI
from google import genai

# Local STT
from faster_whisper import WhisperModel

from proxmox_module import build_router, proxmox_lxc_status, proxmox_vm_status
from authz import build_permission_context, permission_decision, resolve_effective_permissions
from admin_access import require_admin_access as require_admin_access_guard
from audit_log_store import AuditLogStore
from identity import get_active_user_or_raise
from user_store import UserStore
from group_store import GroupStore
from membership_store import MembershipStore
from permission_store import PermissionStore, KNOWN_PERMISSIONS
from jarvis_engine import (
    JarvisEngine,
    build_registry,
    SecurityPolicy,
    normalize_role,
    role_has_permission,
    emergency_stop_enabled,
)

app = FastAPI(title="Jarvis Backend")
logger = logging.getLogger("jarvis.audio")

# Static Website
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


@app.get("/static/orb-v2.html")
def orb_legacy_redirect():
    return FileResponse("static/orb.html")


@app.get("/static/static-v4-tts.html")
def chat_legacy_redirect():
    return FileResponse("static/index.html")


# --- Clients / State ---
_openai_client: OpenAI | None = None
_gemini_client: genai.Client | None = None
_whisper: WhisperModel | None = None

_tokens: dict[str, float] = {}  # token -> expires_epoch


# ---------------------------
# Models
# ---------------------------
class ChatIn(BaseModel):
    text: str
    session_id: str | None = None
    source: str | None = None  # optional: "text" | "voice"


class ChatOut(BaseModel):
    reply: str
    data: dict | None = None
    session_id: str | None = None


class ChatSessionCreateIn(BaseModel):
    title: str | None = None


class ChatMessage(BaseModel):
    role: str
    text: str
    ts: int


class ChatSessionOut(BaseModel):
    id: str
    title: str
    updated_at: int
    created_at: int
    messages: list[ChatMessage] = Field(default_factory=list)


class UnlockIn(BaseModel):
    passphrase: str


class TTSIn(BaseModel):
    text: str


class UnlockOut(BaseModel):
    token: str
    expires_in_sec: int


class AdminUserCreateIn(BaseModel):
    username: str
    role: str = "standard_user"
    enabled: bool = True


class AdminUserUpdateIn(BaseModel):
    role: str | None = None
    enabled: bool | None = None


class AdminGroupCreateIn(BaseModel):
    name: str
    description: str = ""


class AdminGroupUpdateIn(BaseModel):
    name: str | None = None
    description: str | None = None


class AdminMembershipIn(BaseModel):
    user_id: str
    group_id: str


class AdminPermissionSetIn(BaseModel):
    permissions: list[str] = Field(default_factory=list)


class ChatHistoryStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_CHAT_HISTORY_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/chat_history.json")
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
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def create_session(self, title: str | None = None) -> dict:
        now = int(time.time())
        session_id = f"chat-{uuid.uuid4().hex[:12]}"
        item = {
            "id": session_id,
            "title": (title or "New chat").strip() or "New chat",
            "created_at": now,
            "updated_at": now,
            "messages": [],
        }
        self.data.setdefault("sessions", {})[session_id] = item
        self._save()
        return item

    def ensure_session(self, session_id: str | None) -> dict:
        if session_id and session_id in self.data.get("sessions", {}):
            return self.data["sessions"][session_id]
        return self.create_session()

    def append_message(self, session_id: str, role: str, text: str) -> None:
        session = self.ensure_session(session_id)
        now = int(time.time())
        session.setdefault("messages", []).append({"role": role, "text": text, "ts": now})
        session["updated_at"] = now
        if role == "user" and session.get("title", "New chat") == "New chat":
            session["title"] = text[:50] or "New chat"
        self.data.setdefault("sessions", {})[session["id"]] = session
        self._save()

    def list_sessions(self) -> list[dict]:
        sessions = list(self.data.get("sessions", {}).values())
        sessions.sort(key=lambda s: s.get("updated_at", 0), reverse=True)
        return [{
            "id": s.get("id", ""),
            "title": s.get("title", "New chat"),
            "updated_at": s.get("updated_at", 0),
            "created_at": s.get("created_at", 0),
            "message_count": len(s.get("messages", [])),
        } for s in sessions]

    def get_session(self, session_id: str) -> dict | None:
        return self.data.get("sessions", {}).get(session_id)

    def delete_session(self, session_id: str) -> bool:
        sessions = self.data.setdefault("sessions", {})
        if session_id not in sessions:
            return False
        sessions.pop(session_id, None)
        self._save()
        return True




class RagStore:
    def __init__(self) -> None:
        configured = os.getenv("JARVIS_RAG_CACHE_PATH")
        self.path = Path(configured) if configured else Path("/var/lib/jarvis/rag_cache.json")
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
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

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
            except Exception as e:
                report["wikijs"] = f"error: {type(e).__name__}"

        gh_repo = (os.getenv("GITHUB_REPO") or "").strip()
        gh_branch = (os.getenv("GITHUB_BRANCH") or "main").strip()
        gh_pat = (os.getenv("GITHUB_PAT") or "").strip()
        if gh_repo:
            try:
                headers = {"User-Agent": "jarvis-rag"}
                if gh_pat:
                    headers["Authorization"] = f"Bearer {gh_pat}"
                tree_url = f"https://api.github.com/repos/{gh_repo}/git/trees/{gh_branch}?recursive=1"
                tree = self._http_json(tree_url, headers=headers)
                files = [i for i in tree.get("tree", []) if i.get("type") == "blob"][:80]
                for f in files:
                    path = f.get("path", "")
                    if not path or path.endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".zip")):
                        continue
                    sources["github"].append({"title": path, "text": path, "url": f.get("url", "")})
                report["github"] = f"ok ({len(sources['github'])})"
            except Exception as e:
                report["github"] = f"error: {type(e).__name__}"

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
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:limit]]


chat_history = ChatHistoryStore()
rag_store = RagStore()
audit_log = AuditLogStore()
user_store = UserStore()
group_store = GroupStore()
membership_store = MembershipStore()
permission_store = PermissionStore()


@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------
# Provider + Clients
# ---------------------------
def get_provider() -> str:
    configured = (os.getenv("LLM_PROVIDER") or "").lower().strip()
    if configured:
        return configured
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if (os.getenv("LOCAL_LLM_ENABLED") or "").strip() in {"1", "true", "yes", "on"}:
        return "local"
    return "openai"


def get_local_model_dir() -> str:
    return os.getenv("LOCAL_LLM_MODEL_DIR") or "/var/lib/jarvis/local-ai/models"


def local_ai_stub_reply(text: str) -> str:
    model_dir = get_local_model_dir()
    model_hint = os.getenv("LOCAL_LLM_DEFAULT_MODEL") or "future-local-model"
    model_exists = os.path.isdir(model_dir) and any(os.scandir(model_dir))

    if not model_exists:
        return (
            "Understood. Local AI prep is active, but no local model is installed yet "
            f"(expected in {model_dir}, default={model_hint})."
        )
    return "On it. Local AI mode is enabled and model files are available."


def build_context_reply(text: str) -> str:
    t = (text or "").strip().lower()
    if "web gui" in t or "gui" in t:
        return (
            "Understood. Quick check path: service status, recent logs, and network reachability. "
            "Try 'status nginx', 'logs nginx' and 'ping <host>'."
        )
    if "deploy" in t and "branch" in t:
        return (
            "On it. Suggested deploy flow: fetch branch, run tests, build artifact, deploy, then verify health endpoint."
        )
    if "proxmox" in t or "pve" in t:
        return (
            "Understood. For Proxmox I can check host/VM/LXC status with deterministic skills. "
            "Use 'proxmox health' or 'pve vm status <host_id> <node> <vmid>'."
        )
    return (
        "On it. Cloud AI is currently unavailable, but I can still help with deterministic checks. "
        "Try 'skills' or describe the system/service/target to inspect."
    )


def get_stt_provider() -> str:
    return (os.getenv("STT_PROVIDER") or "local").lower().strip()  # local|gemini


def get_openai() -> OpenAI:
    global _openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY not set")
    if _openai_client is None:
        _openai_client = OpenAI(api_key=api_key, timeout=20.0, max_retries=1)
    return _openai_client


def get_gemini() -> genai.Client:
    global _gemini_client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(500, "GEMINI_API_KEY not set")
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def get_whisper() -> WhisperModel:
    global _whisper
    # Modelle: tiny/base/small/medium/large-v3 (CPU: small/base empfohlen)
    model_name = os.getenv("WHISPER_MODEL") or "small"
    compute = os.getenv("WHISPER_COMPUTE") or "int8"  # int8 ist CPU-friendly
    if _whisper is None:
        _whisper = WhisperModel(model_name, device="cpu", compute_type=compute)
    return _whisper


# ---------------------------
# Jarvis Prompt
# ---------------------------
SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S from Iron Man. "
    "Speak concise, confident, technical. "
    "Start responses like 'On it.' or 'Understood.' (vary it). "
    "Then ONE short sentence. No explanations unless explicitly asked or necessary."
)


# ---------------------------
# Unlock / Token
# ---------------------------
def _issue_token() -> UnlockOut:
    ttl_min = int(os.getenv("JARVIS_TOKEN_TTL_MIN") or "20")
    token = secrets.token_urlsafe(32)
    _tokens[token] = time.time() + ttl_min * 60
    return UnlockOut(token=token, expires_in_sec=ttl_min * 60)


def require_token(auth: str | None):
    if not auth or not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing token")
    token = auth.split(" ", 1)[1].strip()
    exp = _tokens.get(token)
    if not exp or time.time() > exp:
        raise HTTPException(401, "Token expired or invalid")


app.include_router(build_router(require_token))


def require_admin_access(
    x_jarvis_user_id: str | None,
    x_jarvis_role: str | None,
    authorization: str | None,
    *,
    allow_bootstrap: bool = False,
) -> tuple[str, str]:
    return require_admin_access_guard(
        user_store,
        _tokens,
        x_jarvis_user_id,
        x_jarvis_role,
        authorization,
        allow_bootstrap=allow_bootstrap,
    )


def _validate_audit_query(limit: int, since_ts: int | None, until_ts: int | None) -> None:
    if limit < 1 or limit > 500:
        raise HTTPException(400, "limit must be between 1 and 500")
    if since_ts is not None and until_ts is not None and since_ts > until_ts:
        raise HTTPException(400, "since_ts must be <= until_ts")

engine = JarvisEngine(build_registry(), SecurityPolicy())


@app.post("/unlock", response_model=UnlockOut)
def unlock(payload: UnlockIn):
    expected = (os.getenv("JARVIS_PASSPHRASE") or "").strip()
    if not expected:
        raise HTTPException(500, "JARVIS_PASSPHRASE not set")

    if (payload.passphrase or "").strip().lower() != expected.lower():
        raise HTTPException(401, "Wrong passphrase")

    return _issue_token()


# ---------------------------
# Skills (no LLM)
# ---------------------------
ALLOWED_SYSTEMD_SERVICES = {
    "jarvis", "nginx", "docker", "ssh", "ufw", "fail2ban"
}


def run_cmd(cmd: list[str], timeout: int = 8) -> str:
    p = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=timeout,
    )
    return (p.stdout or "").strip()


def tts_preprocess_text(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    lowered = cleaned.lower()

    command_map = {
        "status jarvis": "Understood. Jarvis is online and ready.",
        "health": "Understood. System health check is ready.",
        "proxmox health": "Understood. Proxmox health check is ready.",
        "skills": "Understood. I can provide a list of available skills.",
    }
    if lowered in command_map:
        return command_map[lowered]

    # pronunciation tweaks for less robotic output
    replacements = {
        "pve": "P V E",
        "vmid": "V M I D",
        "api": "A P I",
        "jarvis": "J.A.R.V.I.S",
    }
    out = cleaned
    for src, dst in replacements.items():
        out = re.sub(rf"\b{re.escape(src)}\b", dst, out, flags=re.IGNORECASE)

    if out and out[-1] not in ".!?":
        out += "."
    return out


def wakeword_enabled() -> bool:
    return (os.getenv("JARVIS_WAKEWORD_ENABLED") or "0").strip().lower() not in {"0", "false", "no", "off"}


def wakeword_phrase() -> str:
    return (os.getenv("JARVIS_WAKEWORD_PHRASE") or "hey jarvis").strip().lower()


def strip_wakeword(text: str) -> tuple[str, bool]:
    raw = (text or "").strip()
    lowered = raw.lower()
    phrase = wakeword_phrase()
    if lowered == phrase:
        return "status jarvis", True
    if lowered.startswith(phrase + " "):
        return raw[len(phrase):].strip(), True
    return raw, False


def synthesize_tts(text: str) -> bytes:
    piper_bin = os.getenv("PIPER_BIN") or "/usr/local/bin/piper"
    model = os.getenv("PIPER_MODEL") or os.getenv("PIPER_VOICE_MODEL") or ""
    if not model:
        raise HTTPException(500, "PIPER_MODEL not set")

    length_scale = os.getenv("PIPER_LENGTH_SCALE") or "1.12"
    noise_scale = os.getenv("PIPER_NOISE_SCALE") or "0.55"
    noise_w = os.getenv("PIPER_NOISE_W") or "0.75"

    speak_text = tts_preprocess_text(text)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_wav = tmp.name

    try:
        subprocess.run(
            [
                piper_bin,
                "--model", model,
                "--output_file", out_wav,
                "--length_scale", str(length_scale),
                "--noise_scale", str(noise_scale),
                "--noise_w", str(noise_w),
            ],
            input=speak_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            timeout=20,
        )
        with open(out_wav, "rb") as f:
            return f.read()
    except subprocess.CalledProcessError as e:
        logger.exception("TTS process failed")
        raise HTTPException(502, f"TTS error: {e.stderr}") from e
    except FileNotFoundError as e:
        logger.exception("TTS binary not found")
        raise HTTPException(500, "TTS binary not found") from e
    except Exception as e:
        logger.exception("TTS failed")
        raise HTTPException(502, f"TTS error: {type(e).__name__}: {e}") from e
    finally:
        try:
            os.remove(out_wav)
        except Exception:
            pass


def transcribe_local(audio_path: str) -> str:
    model = get_whisper()
    segments, _ = model.transcribe(audio_path, beam_size=1)
    return " ".join([seg.text.strip() for seg in segments]).strip()


def transcribe_gemini(audio_bytes: bytes, content_type: str | None) -> str:
    client = get_gemini()
    model_name = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    resp = client.models.generate_content(
        model=model_name,
        contents=[
            {
                "role": "user",
                "parts": [
                    {"text": "Transcribe this audio to text. Return only the transcript."},
                    {
                        "inline_data": {
                            "mime_type": content_type or "audio/wav",
                            "data": audio_b64,
                        }
                    },
                ],
            }
        ],
    )
    return (getattr(resp, "text", "") or "").strip()


def valid_service_name(name: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_.@-]+", name))


def ensure_service_allowed(service: str) -> None:
    if not valid_service_name(service):
        raise HTTPException(400, "Invalid service name")
    if service not in ALLOWED_SYSTEMD_SERVICES:
        raise HTTPException(403, f"Service not allowed: {service}")


def is_write_command(text: str) -> bool:
    t = text.strip().lower()
    return t.startswith(("restart ", "start ", "stop "))


def format_bytes(size: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


def tail_lines(text: str, max_lines: int = 6) -> str:
    lines = [line for line in (text or "").splitlines() if line.strip()]
    return "\n".join(lines[-max_lines:]) if lines else ""


def parse_meminfo() -> dict[str, int] | None:
    try:
        info = {}
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                key, value = line.split(":", 1)
                parts = value.strip().split()
                if not parts:
                    continue
                info[key] = int(parts[0]) * 1024
        return info
    except Exception:
        return None


def parse_ping(output: str) -> dict[str, str]:
    data: dict[str, str] = {}
    loss_match = re.search(r"(\d+)%\s+packet loss", output)
    if loss_match:
        data["packet_loss"] = f"{loss_match.group(1)}%"
    rtt_match = re.search(r"rtt .* = ([0-9.]+)/([0-9.]+)/([0-9.]+)/([0-9.]+)", output)
    if rtt_match:
        data["rtt_min_ms"] = rtt_match.group(1)
        data["rtt_avg_ms"] = rtt_match.group(2)
        data["rtt_max_ms"] = rtt_match.group(3)
        data["rtt_mdev_ms"] = rtt_match.group(4)
    return data


def block_write_if_unauthorized(role: str, token: str | None, granted_permissions: list[str] | None = None) -> dict[str, object] | None:
    if emergency_stop_enabled():
        return {"reply": "Emergency stop active.", "data": {"error": "emergency_stop"}}
    if not token:
        return {"reply": "Token required.", "data": {"error": "missing_token"}}
    if not (role_has_permission(role, "actions.write.execute") or ((granted_permissions or []) and "actions.write.execute" in set(granted_permissions))):
        return {
            "reply": "Permission denied.",
            "data": {"error": "permission_denied", "permission": "actions.write.execute", "role": role},
        }
    return None


def try_skill(text: str, role: str = "admin", token: str | None = None, granted_permissions: list[str] | None = None) -> dict[str, object] | None:
    t = text.strip().lower()

    # READ
    if t in {"health", "status", "ping jarvis"}:
        return {"reply": "On it. Backend is healthy.", "data": {"ok": True}}

    if t in {"uptime", "server uptime"}:
        out = run_cmd(["/usr/bin/uptime", "-p"])
        return {"reply": f"On it. {out}", "data": {"raw": out}}

    if t in {"disk", "df"}:
        usage = shutil.disk_usage("/")
        used_pct = usage.used / usage.total * 100 if usage.total else 0
        reply = (
            f"On it. Disk /: {used_pct:.0f}% used "
            f"({format_bytes(usage.used)}/{format_bytes(usage.total)})."
        )
        data = {
            "path": "/",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
        }
        return {"reply": reply, "data": data}

    if t in {"memory", "ram"}:
        info = parse_meminfo()
        if info and "MemTotal" in info and "MemAvailable" in info:
            total = info["MemTotal"]
            avail = info["MemAvailable"]
            used = total - avail
            used_pct = used / total * 100 if total else 0
            reply = (
                f"On it. Memory: {format_bytes(avail)} free / "
                f"{format_bytes(total)} total ({used_pct:.0f}% used)."
            )
            data = {"total_bytes": total, "available_bytes": avail, "used_bytes": used}
            return {"reply": reply, "data": data}
        out = run_cmd(["/usr/bin/free", "-h"])
        return {"reply": "On it. Memory details ready.", "data": {"raw": out}}

    if t in {"docker", "docker ps"}:
        out = run_cmd(
            ["/usr/bin/sudo", "/usr/bin/docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"],
            timeout=12,
        )
        rows = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                rows.append({"name": parts[0], "status": parts[1], "image": parts[2]})
        if not rows:
            reply = "On it. No containers running."
        else:
            summary = ", ".join([f"{row['name']} ({row['status']})" for row in rows[:3]])
            reply = f"On it. {len(rows)} container(s) running."
            if summary:
                reply = f"{reply} {summary}"
        return {"reply": reply, "data": {"containers": rows}}

    if t.startswith("pve vm status "):
        parts = t.split()
        if len(parts) != 6:
            raise HTTPException(400, "Usage: pve vm status <host_id> <node> <vmid>")
        host_id, node, vmid = parts[3], parts[4], parts[5]
        data = proxmox_vm_status(host_id, node, vmid).get("data", {})
        status = data.get("status") or "unknown"
        reply = f"On it. Proxmox VM {vmid} on {node} is {status}."
        return {"reply": reply, "data": data}

    if t.startswith("pve lxc status "):
        parts = t.split()
        if len(parts) != 6:
            raise HTTPException(400, "Usage: pve lxc status <host_id> <node> <vmid>")
        host_id, node, vmid = parts[3], parts[4], parts[5]
        data = proxmox_lxc_status(host_id, node, vmid).get("data", {})
        status = data.get("status") or "unknown"
        reply = f"On it. Proxmox LXC {vmid} on {node} is {status}."
        return {"reply": reply, "data": data}

    if t.startswith("status "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        active = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        enabled = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-enabled", service], timeout=8)
        out = run_cmd(
            ["/usr/bin/sudo", "/bin/systemctl", "status", service, "--no-pager", "-n", "10"],
            timeout=12,
        )
        reply = f"On it. {service} is {active} ({enabled})."
        return {"reply": reply, "data": {"service": service, "active": active, "enabled": enabled, "raw": out}}

    if t.startswith("logs "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        out = run_cmd(
            ["/usr/bin/sudo", "/bin/journalctl", "-u", service, "-n", "60", "--no-pager"],
            timeout=12,
        )
        snippet = tail_lines(out, max_lines=6)
        reply = f"On it. Latest {service} logs (last 6 lines):\n{snippet or '(no log lines)'}"
        return {"reply": reply, "data": {"service": service, "raw": out}}

    if t.startswith("ping "):
        host = t.split(" ", 1)[1].strip()
        if not re.fullmatch(r"[a-zA-Z0-9.\-]+", host):
            raise HTTPException(400, "Invalid host")
        out = run_cmd(["/usr/bin/sudo", "/bin/ping", "-c", "2", host], timeout=8)
        metrics = parse_ping(out)
        loss = metrics.get("packet_loss", "unknown loss")
        avg = metrics.get("rtt_avg_ms")
        reply = f"On it. Ping {host}: {loss}"
        if avg:
            reply = f"{reply}, avg {avg} ms."
        return {"reply": reply, "data": {"host": host, "raw": out, **metrics}}

    if t in {"system status", "system_status", "system health"}:
        usage = shutil.disk_usage("/")
        meminfo = parse_meminfo() or {}
        total = meminfo.get("MemTotal", 0)
        avail = meminfo.get("MemAvailable", 0)
        used_pct = (total - avail) / total * 100 if total else 0
        load1, load5, load15 = os.getloadavg()
        cores = os.cpu_count() or 0
        reply = (
            "On it. "
            f"Load {load1:.2f} ({cores} cores), "
            f"Memory {used_pct:.0f}% used, "
            f"Disk / {usage.used / usage.total * 100:.0f}% used."
        )
        data = {
            "load": {"1m": load1, "5m": load5, "15m": load15},
            "cpu_cores": cores,
            "memory": {"total_bytes": total, "available_bytes": avail},
            "disk": {
                "path": "/",
                "total_bytes": usage.total,
                "used_bytes": usage.used,
                "free_bytes": usage.free,
            },
            "platform": platform.platform(),
        }
        return {"reply": reply, "data": data}

    if t in {"time", "date", "time and date", "what time is it"}:
        now = datetime.now().astimezone()
        reply = f"On it. {now.strftime('%Y-%m-%d %H:%M:%S %Z')}."
        return {"reply": reply, "data": {"iso": now.isoformat()}}

    if t in {"hostname", "host info", "host"}:
        hostname = platform.node()
        reply = f"On it. Hostname: {hostname}."
        return {"reply": reply, "data": {"hostname": hostname}}

    if t in {"help", "skills", "skills overview", "what can you do"}:
        overview = [
            "health/status/ping jarvis",
            "uptime",
            "disk",
            "memory",
            "docker",
            "status <service>",
            "logs <service>",
            "ping <host>",
            "pve vm status <host_id> <node> <vmid>",
            "pve lxc status <host_id> <node> <vmid>",
            "restart|start|stop <service>",
            "system status",
            "time and date",
            "hostname",
        ]
        reply = "On it. Available skills: " + ", ".join(overview) + "."
        return {"reply": reply, "data": {"skills": overview}}

    # WRITE
    if t.startswith("restart "):
        blocked = block_write_if_unauthorized(role, token, granted_permissions)
        if blocked is not None:
            return blocked
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} restarted ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("start "):
        blocked = block_write_if_unauthorized(role, token, granted_permissions)
        if blocked is not None:
            return blocked
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "start", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} started ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("stop "):
        blocked = block_write_if_unauthorized(role, token, granted_permissions)
        if blocked is not None:
            return blocked
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "stop", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} stopped ({st}).", "data": {"service": service, "active": st}}

    return None


def rag_query_from_prompt(text: str) -> dict | None:
    raw = (text or "").strip()
    lowered = raw.lower()

    # Explicit Wiki page requests
    wiki_match = re.search(r"(?:wiki\s*seite|wiki\s*page)\s+([a-zA-Z0-9_\-./ ]+)", lowered)
    if wiki_match:
        title = wiki_match.group(1).strip(" .,!?:;\"'“”„").strip()
        return {"query": title or raw, "source": "wikijs", "title": title, "mode": "page"}

    # Task-list oriented asks should prefer wiki task pages
    task_triggers = ["taskliste", "tasks", "aufgaben", "to do", "todo", "budgetplan", "budget"]
    if any(tok in lowered for tok in task_triggers):
        return {"query": "tasks", "source": "wikijs", "title": "", "mode": "tasks"}

    # Explicit GitHub/repo asks
    gh_match = re.search(r"(?:github|repo|repository)\s+([a-zA-Z0-9_\-./ ]+)", lowered)
    if gh_match:
        topic = gh_match.group(1).strip(" .,!?:;\"'“”„").strip()
        return {"query": topic or raw, "source": "github", "title": "", "mode": "repo"}

    # Keep RAG opt-in (avoid aggressive hijacking of normal questions)
    explicit_rag = ["wiki", "wikijs", "github", "repository", "repo", "rag"]
    if any(tok in lowered for tok in explicit_rag):
        return {"query": raw, "source": "", "title": "", "mode": "generic"}

    return None


def select_rag_hits(intent: dict, limit: int = 3) -> list[dict]:
    query = intent.get("query") or ""
    source = (intent.get("source") or "").strip().lower()
    title = (intent.get("title") or "").strip().lower()

    hits = rag_store.search(query, limit=8)
    if source:
        hits = [h for h in hits if (h.get("source") or "").lower() == source]

    if title:
        exact = [h for h in hits if (h.get("title") or "").strip().lower() == title]
        if exact:
            hits = exact + [h for h in hits if h not in exact]

    return hits[:limit]


def format_rag_reply(intent: dict, hits: list[dict]) -> str:
    mode = intent.get("mode") or "generic"
    if not hits:
        return "Understood. I found no matching RAG entries."

    if mode == "tasks":
        lines = []
        for i, h in enumerate(hits[:5], start=1):
            title = h.get("title") or "task"
            text = (h.get("text") or "").strip()
            snippet = text[:110] + ("…" if len(text) > 110 else "")
            lines.append(f"{i}. {title} — {snippet}" if snippet else f"{i}. {title}")
        return "Understood. Current tasks from wiki:\n" + "\n".join(lines)

    top = hits[0]
    snippet = (top.get("text") or "").strip()
    snippet = snippet[:260] + ("…" if len(snippet) > 260 else "")
    return f"Understood. From {top.get('source')}: {top.get('title')} — {snippet}" if snippet else f"Understood. From {top.get('source')}: {top.get('title')}"


def cloud_llm_available() -> bool:
    return bool((os.getenv("OPENAI_API_KEY") or "").strip() or (os.getenv("GEMINI_API_KEY") or "").strip())


def rag_needs_smart_llm(text: str) -> bool:
    lowered = (text or "").lower()
    smart_terms = [
        "liste", "list", "lese", "read", "vor", "vorlesen", "erklär", "explain",
        "zusammen", "summary", "analys", "plan", "budget", "task", "aufgabe",
    ]
    return any(term in lowered for term in smart_terms)


def rag_llm_answer(user_text: str, hits: list[dict]) -> str:
    provider = get_provider()
    context_lines = []
    for i, h in enumerate(hits[:8], start=1):
        context_lines.append(
            f"[{i}] source={h.get('source','')} title={h.get('title','')} text={h.get('text','')}"
        )
    context_blob = "\n".join(context_lines)

    prompt = (
        "You are J.A.R.V.I.S. Use only the provided RAG context. "
        "Answer in German, concise and structured, with bullets for lists/tasks. "
        "If user asks to list/read items, enumerate clearly.\n\n"
        f"User request: {user_text}\n\nRAG context:\n{context_blob}"
    )

    if provider == "gemini" and os.getenv("GEMINI_API_KEY"):
        client = get_gemini()
        model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
        resp = client.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": prompt}]}],
        )
        return (getattr(resp, "text", "") or "").strip() or "Understood. No output returned."

    if os.getenv("OPENAI_API_KEY"):
        client = get_openai()
        model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are J.A.R.V.I.S from Iron Man."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS") or "220"),
        )
        return (resp.choices[0].message.content or "").strip() or "Understood. No output returned."

    raise RuntimeError("No supported cloud LLM configured for RAG smart response")



# ---------------------------
# Chat (Skills -> LLM fallback)
# ---------------------------
@app.post("/chat", response_model=ChatOut)
def chat(
    payload: ChatIn,
    authorization: str | None = Header(default=None),
    x_jarvis_role: str | None = Header(default=None),
    x_jarvis_user_id: str | None = Header(default=None),
):
    text = (payload.text or "").strip()
    source = (payload.source or "text").strip().lower()

    if source == "voice" and wakeword_enabled():
        stripped, detected = strip_wakeword(text)
        if not detected:
            phrase = wakeword_phrase()
            return {
                "reply": f"Awaiting wake word. Say: '{phrase}'.",
                "data": {"wakeword_required": phrase},
                "session_id": payload.session_id,
            }
        text = stripped

    session = chat_history.ensure_session(payload.session_id)
    session_id = session["id"]
    if not text:
        return {"reply": "Say that again.", "session_id": session_id}

    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    chat_history.append_message(session_id, "user", text)

    role = normalize_role(x_jarvis_role)
    try:
        active_user = get_active_user_or_raise(user_store, x_jarvis_user_id)
    except LookupError:
        audit_log.write("invalid_user_context", {"role": role, "source": source, "text": text, "user_id": x_jarvis_user_id, "reason": "not_found"})
        raise HTTPException(404, "user not found")
    except PermissionError:
        audit_log.write("invalid_user_context", {"role": role, "source": source, "text": text, "user_id": x_jarvis_user_id, "reason": "disabled"})
        raise HTTPException(403, "user disabled")

    effective_user_id = active_user["id"] if active_user else None
    granted_permissions = sorted(resolve_effective_permissions(role, effective_user_id, membership_store, permission_store))

    skill_first = try_skill(text, role=role, token=token, granted_permissions=granted_permissions)
    if skill_first is not None:
        reply = skill_first.get("reply", "Done.")
        data = skill_first.get("data", {})
        if data.get("error") == "permission_denied":
            audit_log.write("permission_denied", {"role": role, "source": source, "text": text, "data": data, "path": "try_skill"})
        if data.get("error") == "emergency_stop":
            audit_log.write("emergency_stop_blocked", {"role": role, "source": source, "text": text, "path": "try_skill"})
        chat_history.append_message(session_id, "jarvis", reply)
        return {"reply": reply, "data": data, "session_id": session_id}

    rag_intent = rag_query_from_prompt(text)
    if rag_intent:
        rag_hits = select_rag_hits(rag_intent, limit=5 if rag_intent.get("mode") == "tasks" else 3)
        if rag_hits:
            needs_smart = rag_needs_smart_llm(text)
            if needs_smart and not cloud_llm_available():
                reply = "Understood. Für diese intelligente Wiki/Repo-Auswertung brauche ich Cloud-KI (OPENAI_API_KEY oder GEMINI_API_KEY)."
                data = {"route": "rag", "rag": rag_hits, "intent": rag_intent, "error": "cloud_llm_required"}
                chat_history.append_message(session_id, "jarvis", reply)
                return {"reply": reply, "data": data, "session_id": session_id}

            if needs_smart and cloud_llm_available():
                try:
                    reply = rag_llm_answer(text, rag_hits)
                except Exception:
                    reply = format_rag_reply(rag_intent, rag_hits)
            else:
                reply = format_rag_reply(rag_intent, rag_hits)

            data = {"route": "rag", "rag": rag_hits, "intent": rag_intent, "smart": needs_smart}
            chat_history.append_message(session_id, "jarvis", reply)
            return {"reply": reply, "data": data, "session_id": session_id}

    response = engine.process(text, token, role=role, source=source, granted_permissions=granted_permissions)
    summary = response.get("summary", "")
    data = response.get("data", {})

    if data.get("error") == "permission_denied":
        audit_log.write("permission_denied", {"role": role, "source": source, "text": text, "data": data})
    if data.get("error") == "emergency_stop":
        audit_log.write("emergency_stop_blocked", {"role": role, "source": source, "text": text, "path": "engine"})

    if data.get("confirm") in {"YES", "YES, proceed"}:
        audit_log.write("dangerous_action_confirmation_requested", {"role": role, "source": source, "text": text, "risk": data.get("risk")})

    if data.get("route") != "cloud":
        chat_history.append_message(session_id, "jarvis", summary)
        return {"reply": summary, "data": data, "session_id": session_id}

    provider = get_provider()

    try:
        if provider == "local":
            reply = local_ai_stub_reply(text)
            chat_history.append_message(session_id, "jarvis", reply)
            return {"reply": reply, "session_id": session_id}

        if provider == "gemini":
            client = get_gemini()
            model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

            resp = client.models.generate_content(
                model=model,
                contents=[
                    {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\nUser: {text}"}]},
                ],
            )
            out = (getattr(resp, "text", "") or "").strip() or "On it. (No output returned.)"
            chat_history.append_message(session_id, "jarvis", out)
            return {"reply": out, "session_id": session_id}

        # default: openai
        client = get_openai()
        model = os.getenv("OPENAI_MODEL") or "gpt-4.1-mini"

        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            temperature=0.3,
            max_tokens=int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        )
        out = (resp.choices[0].message.content or "").strip()
        chat_history.append_message(session_id, "jarvis", out)
        return {"reply": out, "session_id": session_id}

    except Exception:
        # Graceful assistant fallback instead of surfacing raw provider errors.
        reply = build_context_reply(text)
        chat_history.append_message(session_id, "jarvis", reply)
        return {
            "reply": reply,
            "data": {
                "route": "offline_assistant",
                "reason": "cloud_unavailable",
            },
            "session_id": session_id,
        }





@app.get("/admin/audit/events")
def admin_audit_events(
    limit: int = 100,
    event: str | None = None,
    role: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
    x_jarvis_user_id: str | None = Header(default=None),
    x_jarvis_role: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    _validate_audit_query(limit, since_ts, until_ts)

    events = audit_log.read_events(
        limit=limit,
        event=event,
        role=role,
        since_ts=since_ts,
        until_ts=until_ts,
    )
    return {
        "events": events,
        "count": len(events),
        "filters": {
            "limit": limit,
            "event": event,
            "role": role,
            "since_ts": since_ts,
            "until_ts": until_ts,
        },
    }





@app.get("/admin/audit/counts")
def admin_audit_counts(
    role: str | None = None,
    since_ts: int | None = None,
    until_ts: int | None = None,
    x_jarvis_user_id: str | None = Header(default=None),
    x_jarvis_role: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    _validate_audit_query(100, since_ts, until_ts)

    counts = audit_log.aggregate_counts(role=role, since_ts=since_ts, until_ts=until_ts)
    total = sum(counts.values())
    return {
        "total": total,
        "counts": counts,
        "filters": {"role": role, "since_ts": since_ts, "until_ts": until_ts},
    }

@app.get("/admin/users")
def admin_list_users(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    return {"users": user_store.list_users()}


@app.post("/admin/users")
def admin_create_user(payload: AdminUserCreateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    actor_user_id, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization, allow_bootstrap=True)
    if actor_user_id == "bootstrap":
        # During first-run bootstrap, only allow creating the initial enabled admin account.
        if normalize_role(payload.role) != "admin":
            raise HTTPException(400, "bootstrap can only create admin user")
        if not bool(payload.enabled):
            raise HTTPException(400, "bootstrap admin must be enabled")
    try:
        created = user_store.create_user(payload.username, role=payload.role, enabled=payload.enabled)
    except ValueError as exc:
        detail = str(exc)
        if detail == "username already exists":
            raise HTTPException(409, detail)
        raise HTTPException(400, detail)
    audit_log.write("admin_user_created", {"actor_role": caller_role, "user_id": created["id"], "username": created["username"], "role": created["role"]})
    return created


@app.patch("/admin/users/{user_id}")
def admin_update_user(user_id: str, payload: AdminUserUpdateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)

    current = user_store.get_user(user_id)
    if not current:
        raise HTTPException(404, "user not found")
    if (
        bool(current.get("enabled", False))
        and current.get("role") == "admin"
        and payload.enabled is False
        and user_store.enabled_admin_count() <= 1
    ):
        raise HTTPException(400, "cannot disable last enabled admin")
    if (
        bool(current.get("enabled", False))
        and current.get("role") == "admin"
        and payload.role is not None
        and normalize_role(payload.role) != "admin"
        and user_store.enabled_admin_count() <= 1
    ):
        raise HTTPException(400, "cannot demote last enabled admin")

    try:
        updated = user_store.update_user(user_id, role=payload.role, enabled=payload.enabled)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit_log.write("admin_user_updated", {"actor_role": caller_role, "user_id": user_id})
    return updated


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)

    target = user_store.get_user(user_id)
    if not target:
        raise HTTPException(404, "user not found")
    if target.get("role") == "admin" and bool(target.get("enabled", False)) and user_store.enabled_admin_count() <= 1:
        raise HTTPException(400, "cannot delete last enabled admin")

    deleted = user_store.delete_user(user_id)
    if not deleted:
        raise HTTPException(404, "user not found")
    removed_memberships = membership_store.remove_user_memberships(user_id)
    removed_permissions = permission_store.clear_user_permissions(user_id)
    audit_log.write(
        "admin_user_deleted",
        {
            "actor_role": caller_role,
            "user_id": user_id,
            "removed_memberships": removed_memberships,
            "removed_user_permissions": bool(removed_permissions),
        },
    )
    return {"ok": True, "id": user_id}



@app.get("/admin/groups")
def admin_list_groups(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    return {"groups": group_store.list_groups()}


@app.post("/admin/groups")
def admin_create_group(payload: AdminGroupCreateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    try:
        created = group_store.create_group(payload.name, description=payload.description)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    audit_log.write("admin_group_created", {"actor_role": caller_role, "group_id": created["id"], "name": created["name"]})
    return created


@app.patch("/admin/groups/{group_id}")
def admin_update_group(group_id: str, payload: AdminGroupUpdateIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    try:
        updated = group_store.update_group(group_id, name=payload.name, description=payload.description)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    if not updated:
        raise HTTPException(404, "group not found")
    audit_log.write("admin_group_updated", {"actor_role": caller_role, "group_id": group_id})
    return updated


@app.delete("/admin/groups/{group_id}")
def admin_delete_group(group_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    deleted = group_store.delete_group(group_id)
    if not deleted:
        raise HTTPException(404, "group not found")
    removed_memberships = membership_store.remove_group_memberships(group_id)
    removed_permissions = permission_store.clear_group_permissions(group_id)
    audit_log.write(
        "admin_group_deleted",
        {
            "actor_role": caller_role,
            "group_id": group_id,
            "removed_memberships": removed_memberships,
            "removed_group_permissions": bool(removed_permissions),
        },
    )
    return {"ok": True, "id": group_id}



@app.get("/admin/assignments")
def admin_list_assignments(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    return {"memberships": membership_store.list_memberships()}


@app.post("/admin/assignments")
def admin_add_assignment(payload: AdminMembershipIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    if not user_store.get_user(payload.user_id):
        raise HTTPException(404, "user not found")
    if not group_store.get_group(payload.group_id):
        raise HTTPException(404, "group not found")

    try:
        item = membership_store.add_membership(payload.user_id, payload.group_id)
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    audit_log.write(
        "admin_assignment_added",
        {"actor_role": caller_role, "user_id": payload.user_id, "group_id": payload.group_id},
    )
    return item


@app.delete("/admin/assignments")
def admin_remove_assignment(user_id: str, group_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    removed = membership_store.remove_membership(user_id, group_id)
    if not removed:
        raise HTTPException(404, "assignment not found")
    audit_log.write(
        "admin_assignment_removed",
        {"actor_role": caller_role, "user_id": user_id, "group_id": group_id},
    )
    return {"ok": True, "user_id": user_id, "group_id": group_id}



@app.get("/admin/permissions")
def admin_list_permissions(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    return {
        "known_permissions": sorted(KNOWN_PERMISSIONS),
        "group_permissions": permission_store.list_group_permissions(),
        "user_permissions": permission_store.list_user_permissions(),
    }


@app.put("/admin/permissions/groups/{group_id}")
def admin_set_group_permissions(group_id: str, payload: AdminPermissionSetIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    if not group_store.get_group(group_id):
        raise HTTPException(404, "group not found")

    invalid = permission_store.invalid_permissions(payload.permissions)
    if invalid:
        raise HTTPException(400, f"invalid permissions: {', '.join(invalid)}")

    try:
        updated = permission_store.set_group_permissions(group_id, payload.permissions)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit_log.write("admin_group_permissions_set", {"actor_role": caller_role, "group_id": group_id, "count": len(updated)})
    return {"group_id": group_id, "permissions": updated}


@app.put("/admin/permissions/users/{user_id}")
def admin_set_user_permissions(user_id: str, payload: AdminPermissionSetIn, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    if not user_store.get_user(user_id):
        raise HTTPException(404, "user not found")

    invalid = permission_store.invalid_permissions(payload.permissions)
    if invalid:
        raise HTTPException(400, f"invalid permissions: {', '.join(invalid)}")

    try:
        updated = permission_store.set_user_permissions(user_id, payload.permissions)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    audit_log.write("admin_user_permissions_set", {"actor_role": caller_role, "user_id": user_id, "count": len(updated)})
    return {"user_id": user_id, "permissions": updated}


@app.delete("/admin/permissions/groups/{group_id}")
def admin_clear_group_permissions(group_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    cleared = permission_store.clear_group_permissions(group_id)
    if not cleared:
        raise HTTPException(404, "group permissions not found")
    audit_log.write("admin_group_permissions_cleared", {"actor_role": caller_role, "group_id": group_id})
    return {"ok": True, "group_id": group_id}


@app.delete("/admin/permissions/users/{user_id}")
def admin_clear_user_permissions(user_id: str, x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    _, caller_role = require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)
    cleared = permission_store.clear_user_permissions(user_id)
    if not cleared:
        raise HTTPException(404, "user permissions not found")
    audit_log.write("admin_user_permissions_cleared", {"actor_role": caller_role, "user_id": user_id})
    return {"ok": True, "user_id": user_id}



@app.get("/admin/permissions/effective/{user_id}")
def admin_effective_permissions(
    user_id: str,
    x_jarvis_user_id: str | None = Header(default=None),
    x_jarvis_role: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)

    try:
        user = get_active_user_or_raise(user_store, user_id)
    except LookupError:
        raise HTTPException(404, "user not found")
    except PermissionError:
        raise HTTPException(403, "user disabled")

    context = build_permission_context(user.get("role"), user_id, membership_store, permission_store)
    return {"user": user, "permissions": context}



@app.get("/admin/authz/check")
def admin_check_authorization(
    user_id: str,
    permission: str,
    x_jarvis_user_id: str | None = Header(default=None),
    x_jarvis_role: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)

    try:
        user = get_active_user_or_raise(user_store, user_id)
    except LookupError:
        raise HTTPException(404, "user not found")
    except PermissionError:
        raise HTTPException(403, "user disabled")

    decision = permission_decision(user.get("role"), user_id, permission, membership_store, permission_store)
    return {"user": user, **decision}



@app.get("/admin/status/summary")
def admin_status_summary(x_jarvis_user_id: str | None = Header(default=None), x_jarvis_role: str | None = Header(default=None), authorization: str | None = Header(default=None)):
    require_admin_access(x_jarvis_user_id, x_jarvis_role, authorization)

    users = user_store.list_users()
    groups = group_store.list_groups()
    user_ids = {u.get("id") for u in users}
    group_ids = {g.get("id") for g in groups}
    enabled_admins = [u for u in users if u.get("role") == "admin" and bool(u.get("enabled", False))]
    disabled_admins = [u for u in users if u.get("role") == "admin" and not bool(u.get("enabled", False))]

    if len(enabled_admins) == 0:
        admin_lockout_state = "locked_out"
    elif len(enabled_admins) == 1:
        admin_lockout_state = "at_risk"
    else:
        admin_lockout_state = "ok"

    memberships = membership_store.list_memberships()
    orphan_memberships = [
        m for m in memberships
        if (m.get("user_id") not in user_ids) or (m.get("group_id") not in group_ids)
    ]

    group_permissions = permission_store.list_group_permissions()
    user_permissions = permission_store.list_user_permissions()
    orphan_group_permission_sets = [gid for gid in group_permissions.keys() if gid not in group_ids]
    orphan_user_permission_sets = [uid for uid in user_permissions.keys() if uid not in user_ids]

    return {
        "counts": {
            "users": len(users),
            "enabled_admins": len(enabled_admins),
            "disabled_admins": len(disabled_admins),
            "groups": len(groups),
            "memberships": len(memberships),
            "group_permission_sets": len(group_permissions),
            "user_permission_sets": len(user_permissions),
            "audit_events": audit_log.count_events(),
            "orphan_memberships": len(orphan_memberships),
            "orphan_group_permission_sets": len(orphan_group_permission_sets),
            "orphan_user_permission_sets": len(orphan_user_permission_sets),
            "admin_lockout_risk": len(enabled_admins) <= 1,
            "admin_lockout_state": admin_lockout_state,
        },
        "orphans": {
            "memberships": orphan_memberships,
            "group_permission_sets": orphan_group_permission_sets,
            "user_permission_sets": orphan_user_permission_sets,
        }
    }

@app.get("/chat/sessions")
def list_chat_sessions():
    return {"sessions": chat_history.list_sessions()}


@app.post("/chat/sessions")
def create_chat_session(payload: ChatSessionCreateIn):
    session = chat_history.create_session(payload.title)
    return session


@app.get("/chat/sessions/{session_id}")
def get_chat_session(session_id: str):
    session = chat_history.get_session(session_id)
    if not session:
        raise HTTPException(404, "session not found")
    return session


@app.delete("/chat/sessions/{session_id}")
def delete_chat_session(session_id: str):
    deleted = chat_history.delete_session(session_id)
    if not deleted:
        raise HTTPException(404, "session not found")
    return {"ok": True, "id": session_id}


@app.get("/rag/status")
def rag_status():
    return {
        "updated_at": rag_store.data.get("updated_at", 0),
        "report": rag_store.data.get("report", {}),
        "counts": {k: len(v) for k, v in (rag_store.data.get("sources") or {}).items()},
    }


@app.post("/rag/refresh")
def rag_refresh():
    return {"report": rag_store.refresh()}


@app.get("/rag/search")
def rag_search(q: str):
    return {"results": rag_store.search(q, limit=5)}

# ---------------------------
# STT (local faster-whisper OR Gemini)
# ---------------------------
@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    stt_provider = get_stt_provider()

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio")

    tmp_in = f"/tmp/jarvis_in_{uuid.uuid4().hex}"
    tmp_wav = f"/tmp/jarvis_in_{uuid.uuid4().hex}.wav"
    tmp_wav_path = tmp_wav
    try:
        with open(tmp_in, "wb") as f:
            f.write(audio_bytes)

        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", tmp_in, "-ac", "1", "-ar", "16000", tmp_wav],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
        except Exception:
            tmp_wav_path = tmp_in

        if stt_provider == "local":
            try:
                text_out = transcribe_local(tmp_wav_path)
                return {"text": text_out}
            except Exception as e:
                logger.exception("Local STT failed")
                raise HTTPException(502, f"Local STT error: {type(e).__name__}: {e}") from e

        if stt_provider == "gemini":
            try:
                text_out = transcribe_gemini(audio_bytes, file.content_type)
                return {"text": text_out}
            except Exception as e:
                msg = str(e)
                if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "STT rate-limited (Gemini free tier). Wait ~40s and try again."},
                        headers={"Retry-After": "40"},
                    )
                logger.exception("Upstream STT failed")
                raise HTTPException(502, f"Upstream STT error: {type(e).__name__}: {e}") from e
    finally:
        for path in {tmp_in, tmp_wav}:
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass

    raise HTTPException(400, f"Unknown STT provider: {stt_provider}")


# ---------------------------
# TTS (local piper)
# ---------------------------
@app.post("/tts")
def tts(payload: TTSIn):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Missing text")

    audio = synthesize_tts(text)
    return Response(content=audio, media_type="audio/wav")
