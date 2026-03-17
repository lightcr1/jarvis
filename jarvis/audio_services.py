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


def synthesize_tts(text: str, logger) -> bytes:
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
        with open(out_wav, "rb") as handle:
            return handle.read()
    except subprocess.CalledProcessError as exc:
        logger.exception("TTS process failed")
        raise HTTPException(502, f"TTS error: {exc.stderr}") from exc
    except FileNotFoundError as exc:
        logger.exception("TTS binary not found")
        raise HTTPException(500, "TTS binary not found") from exc
    except Exception as exc:
        logger.exception("TTS failed")
        raise HTTPException(502, f"TTS error: {type(exc).__name__}: {exc}") from exc
    finally:
        try:
            os.remove(out_wav)
        except Exception:
            pass


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
