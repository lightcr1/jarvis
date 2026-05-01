import asyncio
import base64
import os
import re
import subprocess
import tempfile

from fastapi import HTTPException


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


def wakeword_enabled(settings_getter) -> bool:
    configured = os.getenv("JARVIS_WAKEWORD_ENABLED")
    if configured is not None:
        return configured.strip().lower() not in {"0", "false", "no", "off"}
    return bool(settings_getter().get("voice", {}).get("wakeword_enabled", False))


def wakeword_phrase(settings_getter) -> str:
    configured = (os.getenv("JARVIS_WAKEWORD_PHRASE") or "").strip().lower()
    if configured:
        return configured
    return settings_getter().get("voice", {}).get("wakeword_phrase", "hey jarvis")


def strip_wakeword(text: str, phrase: str) -> tuple[str, bool]:
    raw = (text or "").strip()
    lowered = raw.lower()
    if lowered == phrase:
        return "status jarvis", True
    if lowered.startswith(phrase + " "):
        return raw[len(phrase):].strip(), True
    return raw, False


def _synthesize_piper(speak_text: str, logger) -> bytes:
    piper_bin = os.getenv("PIPER_BIN") or "/usr/local/bin/piper"
    model = os.getenv("PIPER_MODEL") or os.getenv("PIPER_VOICE_MODEL") or ""
    if not model:
        raise HTTPException(500, "PIPER_MODEL not set — set PIPER_MODEL in config.env")

    length_scale = os.getenv("PIPER_LENGTH_SCALE") or "1.12"
    noise_scale  = os.getenv("PIPER_NOISE_SCALE")  or "0.55"
    noise_w      = os.getenv("PIPER_NOISE_W")       or "0.75"

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        out_wav = tmp.name
    try:
        subprocess.run(
            [piper_bin, "--model", model, "--output_file", out_wav,
             "--length_scale", str(length_scale),
             "--noise_scale",  str(noise_scale),
             "--noise_w",       str(noise_w)],
            input=speak_text, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=True, timeout=20,
        )
        with open(out_wav, "rb") as fh:
            return fh.read()
    except subprocess.CalledProcessError as exc:
        logger.exception("Piper TTS failed")
        raise HTTPException(502, f"Piper TTS error: {exc.stderr}") from exc
    except FileNotFoundError as exc:
        logger.exception("Piper binary not found")
        raise HTTPException(500, "Piper binary not found") from exc
    except Exception as exc:
        logger.exception("Piper TTS error")
        raise HTTPException(502, f"Piper TTS error: {type(exc).__name__}: {exc}") from exc
    finally:
        try: os.remove(out_wav)
        except Exception: pass


def _synthesize_edge(speak_text: str, logger, voice: str = "") -> tuple[bytes, str]:
    """Returns (audio_bytes, media_type). Uses edge-tts (Microsoft neural TTS, free)."""
    try:
        import edge_tts  # type: ignore[import]
    except ImportError as exc:
        raise HTTPException(500, "edge-tts not installed — run: pip install edge-tts") from exc

    voice = voice.strip() or os.getenv("EDGE_TTS_VOICE") or "en-GB-RyanNeural"
    rate  = os.getenv("EDGE_TTS_RATE")  or "-5%"
    pitch = os.getenv("EDGE_TTS_PITCH") or "-2Hz"

    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        out_mp3 = tmp.name
    try:
        async def _run():
            comm = edge_tts.Communicate(speak_text, voice, rate=rate, pitch=pitch)
            await comm.save(out_mp3)

        asyncio.run(_run())

        # Convert to WAV via ffmpeg if available (keeps media_type consistent)
        out_wav = out_mp3.replace(".mp3", ".wav")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", out_mp3, out_wav],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=10,
            )
            with open(out_wav, "rb") as fh:
                return fh.read(), "audio/wav"
        except Exception:
            # ffmpeg not available — return MP3 directly
            with open(out_mp3, "rb") as fh:
                return fh.read(), "audio/mpeg"
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("edge-tts failed")
        raise HTTPException(502, f"edge-tts error: {type(exc).__name__}: {exc}") from exc
    finally:
        for p in (out_mp3, out_mp3.replace(".mp3", ".wav")):
            try: os.remove(p)
            except Exception: pass


def synthesize_tts(text: str, logger, voice: str = "") -> tuple[bytes, str]:
    """Returns (audio_bytes, media_type). Provider selected by TTS_PROVIDER env var."""
    provider = (os.getenv("TTS_PROVIDER") or "piper").strip().lower()
    speak_text = tts_preprocess_text(text)

    if provider == "edge":
        return _synthesize_edge(speak_text, logger, voice=voice)
    # default: piper (voice param ignored — piper uses model file)
    return _synthesize_piper(speak_text, logger), "audio/wav"


def transcribe_local(audio_path: str, whisper_getter) -> str:
    model = whisper_getter()
    segments, _ = model.transcribe(audio_path, beam_size=1)
    return " ".join([seg.text.strip() for seg in segments]).strip()


def transcribe_gemini(audio_bytes: bytes, content_type: str | None, gemini_getter) -> str:
    client = gemini_getter()
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
