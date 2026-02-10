import base64
from datetime import datetime
import logging
import os
import platform
import re
import secrets
import shutil
import subprocess
import tempfile
import time
import uuid

from fastapi import FastAPI, File, Header, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel

from openai import OpenAI
from google import genai

# Local STT
from faster_whisper import WhisperModel

from proxmox_module import build_router, proxmox_lxc_status, proxmox_vm_status
from jarvis_engine import JarvisEngine, build_registry, SecurityPolicy

app = FastAPI(title="Jarvis Backend")
logger = logging.getLogger("jarvis.audio")

# Static Website
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
    return FileResponse("static/static-v4-tts.html")


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


class ChatOut(BaseModel):
    reply: str
    data: dict | None = None


class UnlockIn(BaseModel):
    passphrase: str


class TTSIn(BaseModel):
    text: str


class UnlockOut(BaseModel):
    token: str
    expires_in_sec: int


@app.get("/health")
def health():
    return {"ok": True}


def _model_status() -> dict:
    base = os.getenv("JARVIS_MODELS_DIR") or "/opt/jarvis/models"
    kinds = ["llm", "stt", "tts"]
    status: dict[str, dict] = {}
    missing: list[str] = []

    for kind in kinds:
        model_dir = os.path.join(base, kind)
        exists = os.path.isdir(model_dir)
        has_files = False
        if exists:
            try:
                has_files = any(os.scandir(model_dir))
            except Exception:
                has_files = False
        ok = exists and has_files
        if not ok:
            missing.append(kind)
        status[kind] = {"path": model_dir, "ok": ok}

    return {
        "base": base,
        "status": status,
        "missing": missing,
        "ready": len(missing) == 0,
        "message": (
            "All model directories populated."
            if not missing
            else "Models missing. Copy files into /opt/jarvis/models/<llm|stt|tts> and restart jarvis-backend."
        ),
    }


@app.get("/models/status")
def models_status():
    return _model_status()



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
    return "openai"


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


def synthesize_tts(text: str) -> bytes:
    piper_bin = os.getenv("PIPER_BIN") or "/usr/local/bin/piper"
    model = os.getenv("PIPER_MODEL") or os.getenv("PIPER_VOICE_MODEL") or ""
    if not model:
        raise HTTPException(500, "PIPER_MODEL not set")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_wav = tmp.name

    try:
        subprocess.run(
            [piper_bin, "--model", model, "--output_file", out_wav],
            input=text,
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


def try_skill(text: str) -> dict[str, object] | None:
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
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} restarted ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("start "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "start", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} started ({st}).", "data": {"service": service, "active": st}}

    if t.startswith("stop "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "stop", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return {"reply": f"On it. {service} stopped ({st}).", "data": {"service": service, "active": st}}

    return None


# ---------------------------
# Chat (Skills -> LLM fallback)
# ---------------------------
@app.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn, authorization: str | None = Header(default=None)):
    text = (payload.text or "").strip()
    if not text:
        return {"reply": "Say that again."}

    token = None
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()

    response = engine.process(text, token)
    summary = response.get("summary", "")
    data = response.get("data", {})
    if data.get("route") != "cloud":
        return {"reply": summary, "data": data}

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

    except Exception as e:
        raise HTTPException(502, f"Upstream error: {type(e).__name__}: {e}")


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
