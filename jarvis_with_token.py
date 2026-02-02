import os
import base64
import time
import secrets
import subprocess
import re

from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from openai import OpenAI
from google import genai


app = FastAPI(title="Jarvis Backend")

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


def try_skill(text: str) -> str | None:
    t = text.strip().lower()

    # --- READ SKILLS ---
    if t in {"health", "status", "ping jarvis"}:
        return "On it.\nSTATUS\nBackend is healthy.\nRESULT\n/health returns ok.\nNEXT\n"

    if t in {"uptime", "server uptime"}:
        out = run_cmd(["/usr/bin/uptime"])
        return f"On it.\nSTATUS\nReading uptime.\nRESULT\n{out}\nNEXT\n"

    if t in {"disk", "df"}:
        out = run_cmd(["/bin/df", "-h"])
        return f"On it.\nSTATUS\nChecking disk usage.\nRESULT\n{out}\nNEXT\n"

    if t in {"memory", "ram"}:
        out = run_cmd(["/usr/bin/free", "-h"])
        return f"On it.\nSTATUS\nChecking memory.\nRESULT\n{out}\nNEXT\n"

    if t in {"docker", "docker ps"}:
        out = run_cmd(["/usr/bin/sudo", "/usr/bin/docker", "ps"], timeout=12)
        return f"On it.\nSTATUS\nListing containers.\nRESULT\n{out}\nNEXT\n"

    if t.startswith("status "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        out = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "status", service, "--no-pager"], timeout=12)
        return f"On it.\nSTATUS\nChecking service '{service}'.\nRESULT\n{out}\nNEXT\n"

    if t.startswith("logs "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        out = run_cmd(["/usr/bin/sudo", "/bin/journalctl", "-u", service, "-n", "60", "--no-pager"], timeout=12)
        return f"On it.\nSTATUS\nFetching logs for '{service}'.\nRESULT\n{out}\nNEXT\n"

    if t.startswith("ping "):
        host = t.split(" ", 1)[1].strip()
        if not re.fullmatch(r"[a-zA-Z0-9.\-]+", host):
            raise HTTPException(400, "Invalid host")
        out = run_cmd(["/usr/bin/sudo", "/bin/ping", "-c", "2", host], timeout=8)
        return f"On it.\nSTATUS\nPinging {host}.\nRESULT\n{out}\nNEXT\n"

    # --- WRITE SKILLS ---
    if t.startswith("restart "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return f"On it.\nSTATUS\nRestarting '{service}'.\nRESULT\nis-active: {st}\nNEXT\n"

    if t.startswith("stop "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "stop", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return f"On it.\nSTATUS\nStopping '{service}'.\nRESULT\nis-active: {st}\nNEXT\n"

    if t.startswith("start "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "start", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return f"On it.\nSTATUS\nStarting '{service}'.\nRESULT\nis-active: {st}\nNEXT\n"

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
        return {"reply": skill_reply}

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

    return {"reply": out}


# ---------------------------
# STT (Gemini)
# ---------------------------
@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    provider = get_provider()
    if provider != "gemini":
        raise HTTPException(400, "STT currently only supported with Gemini")

    client = get_gemini()
    model = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

    audio_bytes = await file.read()
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

    try:
        resp = client.models.generate_content(
            model=model,
            contents=[
                {
                    "role": "user",
                    "parts": [
                        {"text": "Transcribe this audio to text. Return only the transcript."},
                        {
                            "inline_data": {
                                "mime_type": file.content_type or "audio/wav",
                                "data": audio_b64,
                            }
                        },
                    ],
                }
            ],
        )
        text = (getattr(resp, "text", "") or "").strip()
        return {"text": text}
    except Exception as e:
        raise HTTPException(502, f"Upstream STT error: {type(e).__name__}: {e}")
