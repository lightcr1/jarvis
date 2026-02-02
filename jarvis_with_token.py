import base64
from datetime import datetime
import logging
import os
import platform
import re
import secrets
import shutil
import subprocess
import time

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from openai import OpenAI
from google import genai


app = FastAPI(title="Jarvis Backend")
logger = logging.getLogger("jarvis.audio")

# Static Website
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/index.html")


# --- Clients / State ---
_openai_client: OpenAI | None = None
_gemini_client: genai.Client | None = None
_tokens: dict[str, float] = {}  # token -> expires_epoch


# ---------------------------
# Models
# ---------------------------
class ChatIn(BaseModel):
    text: str


class ChatOut(BaseModel):
    reply: str
    data: dict | None = None


class UnlockIn(BaseModel):
    passphrase: str


class UnlockOut(BaseModel):
    token: str
    expires_in_sec: int


@app.get("/health")
def health():
    return {"ok": True}


# ---------------------------
# Provider + Clients
# ---------------------------
def get_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "openai").lower().strip()


def get_openai() -> OpenAI:
    global _openai_client
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(500, "OPENAI_API_KEY not set")
    if _openai_client is None:
        _openai_client = OpenAI(api_key=api_key, timeout=15.0, max_retries=1)
    return _openai_client


def get_gemini() -> genai.Client:
    global _gemini_client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(500, "GEMINI_API_KEY not set")
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


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
    # erweitern: "jellyfin", "grafana-server", ...
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


def transcribe_gemini(audio_bytes: bytes, content_type: str | None) -> str:
    client = get_gemini()
    model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    resp = client.models.generate_content(
        model=model,
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


def try_skill(text: str) -> dict[str, object] | None:
    t = text.strip().lower()

    # --- READ SKILLS ---
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
            "restart|start|stop <service>",
            "system status",
            "time and date",
            "hostname",
        ]
        reply = "On it. Available skills: " + ", ".join(overview) + "."
        return {"reply": reply, "data": {"skills": overview}}

    # --- WRITE SKILLS ---
    if t.startswith("restart "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} restarted ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("stop "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "stop", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} stopped ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("start "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "start", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} started ({st}).", "data": {"service": service, "active": st}}

    return None


# ---------------------------
# Chat (Skills -> LLM fallback)
# ---------------------------
@app.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn, authorization: str | None = Header(default=None)):
    text = (payload.text or "").strip()
    if not text:
        return {"reply": "Say that again."}

    # Write only after unlock
    if is_write_command(text):
        require_token(authorization)

    # 1) Try deterministic skills first (no LLM)
    skill_reply = try_skill(text)
    if skill_reply is not None:
        return skill_reply

    provider = get_provider()

    try:
        if provider == "gemini":
            client = get_gemini()
            model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

            resp = client.models.generate_content(
                model=model,
                contents=[
                    {"role": "user", "parts": [{"text": f"{SYSTEM_PROMPT}\n\nUser: {text}"}]},
                ],
            )
            out = (getattr(resp, "text", "") or "").strip()
            return {"reply": out or "On it. (No output returned.)"}

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
        return {"reply": (resp.choices[0].message.content or "").strip()}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(502, f"Upstream error: {type(e).__name__}: {e}")


# ---------------------------
# Command (Skills only, optional)
# ---------------------------
@app.post("/command", response_model=ChatOut)
def command(payload: ChatIn, authorization: str | None = Header(default=None)):
    text = (payload.text or "").strip()
    if not text:
        return {"reply": "Say that again."}

    # Write only after unlock
    if is_write_command(text):
        require_token(authorization)

    out = try_skill(text)
    if out is None:
        return {"reply": "Understood. No matching command."}

    return out


# ---------------------------
# STT (Gemini)
# ---------------------------
@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    provider = get_provider()
    if provider != "gemini":
        raise HTTPException(400, "STT currently only supported with Gemini")

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio")

    try:
        text = transcribe_gemini(audio_bytes, file.content_type)
        return {"text": text}
    except Exception as e:
        logger.exception("Upstream STT failed")
        raise HTTPException(502, f"Upstream STT error: {type(e).__name__}: {e}") from e
