import os
import base64
import time
import secrets
import subprocess
import re
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Header
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from openai import OpenAI
from google import genai

# Local STT
from faster_whisper import WhisperModel
from fastapi.responses import Response

app = FastAPI(title="Jarvis Backend")

# Static Website
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def root():
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


class ChatOut(BaseModel):
    reply: str


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


# ---------------------------
# Provider + Clients
# ---------------------------
def get_provider() -> str:
    return (os.getenv("LLM_PROVIDER") or "openai").lower().strip()


def get_stt_provider() -> str:
    return (os.getenv("STT_PROVIDER") or "local").lower().strip()  # local|gemini


def get_tts_provider() -> str:
    return (os.getenv("TTS_PROVIDER") or "local").lower().strip()  # local


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

    # READ
    if t in {"health", "status", "ping jarvis"}:
        return "On it. Backend is healthy."

    if t in {"uptime", "server uptime"}:
        out = run_cmd(["/usr/bin/uptime"])
        return f"On it. {out}"

    if t in {"disk", "df"}:
        out = run_cmd(["/bin/df", "-h"])
        return f"On it.\n{out}"

    if t in {"memory", "ram"}:
        out = run_cmd(["/usr/bin/free", "-h"])
        return f"On it.\n{out}"

    if t in {"docker", "docker ps"}:
        out = run_cmd(["/usr/bin/sudo", "/usr/bin/docker", "ps"], timeout=12)
        return f"On it.\n{out}"

    if t.startswith("status "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        out = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "status", service, "--no-pager"], timeout=12)
        return f"On it.\n{out}"

    if t.startswith("logs "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        out = run_cmd(["/usr/bin/sudo", "/bin/journalctl", "-u", service, "-n", "60", "--no-pager"], timeout=12)
        return f"On it.\n{out}"

    if t.startswith("ping "):
        host = t.split(" ", 1)[1].strip()
        if not re.fullmatch(r"[a-zA-Z0-9.\-]+", host):
            raise HTTPException(400, "Invalid host")
        out = run_cmd(["/usr/bin/sudo", "/bin/ping", "-c", "2", host], timeout=8)
        return f"On it.\n{out}"

    # WRITE
    if t.startswith("restart "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "restart", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return f"On it. '{service}' restarted. is-active: {st}"

    if t.startswith("start "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "start", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return f"On it. '{service}' started. is-active: {st}"

    if t.startswith("stop "):
        service = t.split(" ", 1)[1].strip()
        ensure_service_allowed(service)
        run_cmd(["/usr/bin/sudo", "/bin/systemctl", "stop", service], timeout=15)
        st = run_cmd(["/usr/bin/sudo", "/bin/systemctl", "is-active", service], timeout=8)
        return f"On it. '{service}' stopped. is-active: {st}"

    return None


# ---------------------------
# Chat (Skills -> LLM fallback)
# ---------------------------
@app.post("/chat", response_model=ChatOut)
def chat(payload: ChatIn, authorization: str | None = Header(default=None)):
    text = (payload.text or "").strip()
    if not text:
        return {"reply": "Say that again."}

    if is_write_command(text):
        require_token(authorization)

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

    except Exception as e:
        raise HTTPException(502, f"Upstream error: {type(e).__name__}: {e}")


# ---------------------------
# TTS (local piper)
# ---------------------------
@app.post("/tts")
def tts(payload: ChatIn):
    provider = get_tts_provider()
    if provider != "local":
        raise HTTPException(400, "TTS provider not supported")

    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "No text")

    voice = os.getenv("PIPER_VOICE_MODEL") or ""
    if not voice:
        raise HTTPException(500, "PIPER_VOICE_MODEL not set")

    out_wav = f"/tmp/jarvis_tts_{uuid.uuid4().hex}.wav"
    cmd = ["piper", "--model", voice, "--output_file", out_wav]
    try:
        subprocess.run(cmd, input=text.encode("utf-8"), check=True)
        return FileResponse(out_wav, media_type="audio/wav", filename="jarvis.wav")
    except Exception as e:
        raise HTTPException(502, f"TTS error: {type(e).__name__}: {e}")


# ---------------------------
# STT (local faster-whisper OR Gemini)
# ---------------------------
@app.post("/stt")
async def stt(file: UploadFile = File(...)):
    stt_provider = get_stt_provider()

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(400, "Empty audio")

    # Save to temp
    tmp_in = f"/tmp/jarvis_in_{uuid.uuid4().hex}"
    tmp_in_path = tmp_in
    with open(tmp_in_path, "wb") as f:
        f.write(audio_bytes)

    # Convert to wav (whisper likes 16k mono, but ffmpeg will handle)
    tmp_wav = f"/tmp/jarvis_in_{uuid.uuid4().hex}.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in_path, "-ac", "1", "-ar", "16000", tmp_wav],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except Exception:
        # if ffmpeg fails, still try with original file (gemini might accept)
        tmp_wav = tmp_in_path

    # --- LOCAL STT ---
    if stt_provider == "local":
        try:
            model = get_whisper()
            segments, info = model.transcribe(tmp_wav, beam_size=1)
            text_out = " ".join([seg.text.strip() for seg in segments]).strip()
            return {"text": text_out}
        except Exception as e:
            raise HTTPException(502, f"Local STT error: {type(e).__name__}: {e}")

    # --- GEMINI STT ---
    if stt_provider == "gemini":
        client = get_gemini()
        model_name = os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"

        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
        try:
            resp = client.models.generate_content(
                model=model_name,
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
            text_out = (getattr(resp, "text", "") or "").strip()
            return {"text": text_out}
        except Exception as e:
            msg = str(e)
            if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "STT rate-limited (Gemini free tier). Wait ~40s and try again."},
                    headers={"Retry-After": "40"},
                )
            raise HTTPException(502, f"Upstream STT error: {type(e).__name__}: {e}")

    raise HTTPException(400, f"Unknown STT provider: {stt_provider}")

@app.post("/tts")
def tts(payload: TTSIn):
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(400, "Missing text")

    piper_bin = os.getenv("PIPER_BIN") or "/usr/local/bin/piper"
    model = os.getenv("PIPER_MODEL") or "/etc/jarvis/piper/de_DE-thorsten-medium.onnx"
    out_wav = f"/tmp/jarvis_tts_{int(time.time()*1000)}.wav"

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
            audio = f.read()

        return Response(content=audio, media_type="audio/wav")

    except subprocess.CalledProcessError as e:
        raise HTTPException(502, f"TTS error: {e.stderr}")
    except Exception as e:
        raise HTTPException(502, f"TTS error: {type(e).__name__}: {e}")
    finally:
        try:
            os.remove(out_wav)
        except Exception:
            pass
