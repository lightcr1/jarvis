import os

from fastapi import APIRouter, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, Response

from .api_models import TTSIn
from .rate_limiter import _rate
from .router_dependencies import LiveRef
from .user_preferences_store import JARVIS_VOICES


def build_voice_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    @router.get("/api/tts/voices")
    def tts_voices():
        return {"voices": JARVIS_VOICES}

    @router.post("/stt")
    async def stt(
        file: UploadFile = File(...),
        request: Request = None,
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_mode: str | None = Header(default=None),
    ):
        rl_key = x_jarvis_session or (request.client.host if request and request.client else "anon")
        if not _rate.allow(f"stt:{rl_key}", limit=30, window=60.0):
            raise HTTPException(429, "Rate limit exceeded — too many transcription requests.")
        status_token = current("status_hub").begin("recording", source="voice", mode=(x_jarvis_mode or "").strip().lower())
        if (x_jarvis_mode or "").strip().lower() == "orb":
            deps["require_identity_session"](x_jarvis_session)
        stt_provider = deps["get_stt_provider"]()

        audio_bytes = await file.read()
        tmp_in = ""
        tmp_wav = ""
        try:
            if not audio_bytes:
                raise HTTPException(400, "Empty audio")

            tmp_in = f"/tmp/jarvis_in_{deps['uuid4_hex']()}"
            tmp_wav = f"/tmp/jarvis_in_{deps['uuid4_hex']()}.wav"
            tmp_wav_path = tmp_wav
            with open(tmp_in, "wb") as handle:
                handle.write(audio_bytes)

            try:
                current("subprocess").run(
                    ["ffmpeg", "-y", "-i", tmp_in, "-ac", "1", "-ar", "16000", tmp_wav],
                    stdout=current("subprocess").DEVNULL,
                    stderr=current("subprocess").DEVNULL,
                    check=True,
                )
            except Exception:
                tmp_wav_path = tmp_in

            if stt_provider == "local":
                try:
                    text_out = current("transcribe_local")(tmp_wav_path)
                    return {"text": text_out}
                except Exception as exc:
                    current("logger").exception("Local STT failed")
                    raise HTTPException(502, f"Local STT error: {type(exc).__name__}: {exc}") from exc

            if stt_provider == "gemini":
                try:
                    text_out = current("transcribe_gemini")(audio_bytes, file.content_type)
                    return {"text": text_out}
                except Exception as exc:
                    msg = str(exc)
                    if "RESOURCE_EXHAUSTED" in msg or "429" in msg:
                        return JSONResponse(
                            status_code=429,
                            content={"detail": "STT rate-limited (Gemini free tier). Wait ~40s and try again."},
                            headers={"Retry-After": "40"},
                        )
                    current("logger").exception("Upstream STT failed")
                    raise HTTPException(502, f"Upstream STT error: {type(exc).__name__}: {exc}") from exc
        finally:
            for path in {tmp_in, tmp_wav}:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass
            current("status_hub").end(status_token)

        raise HTTPException(400, f"Unknown STT provider: {stt_provider}")

    @router.post("/tts")
    def tts(
        payload: TTSIn,
        request: Request = None,
        x_jarvis_session: str | None = Header(default=None),
    ):
        text = (payload.text or "").strip()
        if not text:
            raise HTTPException(400, "Missing text")
        rl_key = x_jarvis_session or (request.client.host if request and request.client else "anon")
        if not _rate.allow(f"tts:{rl_key}", limit=60, window=60.0):
            raise HTTPException(429, "Rate limit exceeded — too many TTS requests.")

        # Explicit voice in the request body takes priority; fall back to stored user preference
        voice = (payload.voice or "").strip()
        if not voice:
            session = deps.get("get_identity_session") and deps["get_identity_session"](x_jarvis_session)
            if session:
                user_id = (session.get("user") or {}).get("id", "")
                user_prefs_store = current("user_preferences_store")
                if user_id and user_prefs_store:
                    voice = user_prefs_store.get(user_id).get("tts_voice", "") or ""

        status_token = current("status_hub").begin("speaking", source="voice", mode="tts")
        try:
            result = current("synthesize_tts")(text, voice)
            if isinstance(result, tuple):
                audio, media_type = result
            else:
                audio, media_type = result, "audio/wav"
            return Response(content=audio, media_type=media_type)
        finally:
            current("status_hub").end(status_token)

    return router
