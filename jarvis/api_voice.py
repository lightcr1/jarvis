import os

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response

from .api_models import TTSIn
from .router_dependencies import LiveRef


def build_voice_router(deps: dict) -> APIRouter:
    router = APIRouter()

    def current(name: str):
        value = deps[name]
        return value.get() if isinstance(value, LiveRef) else value

    @router.post("/stt")
    async def stt(
        file: UploadFile = File(...),
        x_jarvis_session: str | None = Header(default=None),
        x_jarvis_mode: str | None = Header(default=None),
    ):
        if (x_jarvis_mode or "").strip().lower() == "orb":
            deps["require_identity_session"](x_jarvis_session)
        stt_provider = deps["get_stt_provider"]()

        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(400, "Empty audio")

        tmp_in = f"/tmp/jarvis_in_{deps['uuid4_hex']()}"
        tmp_wav = f"/tmp/jarvis_in_{deps['uuid4_hex']()}.wav"
        tmp_wav_path = tmp_wav
        try:
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

        raise HTTPException(400, f"Unknown STT provider: {stt_provider}")

    @router.post("/tts")
    def tts(payload: TTSIn):
        text = (payload.text or "").strip()
        if not text:
            raise HTTPException(400, "Missing text")

        audio = current("synthesize_tts")(text)
        return Response(content=audio, media_type="audio/wav")

    return router
