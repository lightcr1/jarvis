"""
Wakeword detection engines for JARVIS.

Public API:
  create_wakeword_engine(settings: dict) -> WakewordEngine
  set_wakeword_engine(engine: WakewordEngine) -> None  (wires into audio_services)

Engine selection (in priority order):
  1. JARVIS_WAKEWORD_ENABLED=0/false → NullWakewordEngine
  2. JARVIS_WAKEWORD_ENGINE env var (openwakeword | software | none)
  3. settings["voice"]["wakeword_engine"] (same values)
  4. Default: SoftwareWakewordEngine
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
from typing import Awaitable, Callable

logger = logging.getLogger("jarvis.wakeword")

DetectionCallback = Callable[[], Awaitable[None]]


class NullWakewordEngine:
    """No-op engine — used when wakeword detection is disabled."""

    def start(self, loop: asyncio.AbstractEventLoop, callback: DetectionCallback) -> None:
        pass

    def stop(self) -> None:
        pass

    def is_running(self) -> bool:
        return False


class SoftwareWakewordEngine:
    """Post-transcription phrase stripping — not true always-on detection.

    start()/stop() are no-ops; strip() is called by the STT pipeline after
    each transcription to remove the wakeword phrase if present.
    """

    def __init__(self, phrase: str = "hey jarvis") -> None:
        self.phrase = (phrase or "hey jarvis").strip().lower()
        self._running = False

    def strip(self, text: str) -> tuple[str, bool]:
        raw = (text or "").strip()
        lowered = raw.lower()
        if lowered == self.phrase:
            return "status jarvis", True
        if lowered.startswith(self.phrase + " "):
            return raw[len(self.phrase):].strip(), True
        return raw, False

    def start(self, loop: asyncio.AbstractEventLoop, callback: DetectionCallback) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False

    def is_running(self) -> bool:
        return self._running


class OpenWakeWordEngine:
    """Always-on mic keyword spotting using the openwakeword library.

    Runs mic capture in a daemon thread; fires the async detection callback
    via asyncio.run_coroutine_threadsafe when the wakeword is detected above
    the sensitivity threshold. Sensitivity can be updated at runtime without
    restart via the .sensitivity property.
    """

    def __init__(self, model_path: str = "", sensitivity: float = 0.5) -> None:
        self._model_path = model_path
        self._sensitivity = max(0.0, min(1.0, float(sensitivity)))
        self._running = False
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._callback: DetectionCallback | None = None

    @property
    def sensitivity(self) -> float:
        return self._sensitivity

    @sensitivity.setter
    def sensitivity(self, value: float) -> None:
        self._sensitivity = max(0.0, min(1.0, float(value)))

    def start(self, loop: asyncio.AbstractEventLoop, callback: DetectionCallback) -> None:
        self._loop = loop
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._run_mic_loop, daemon=True, name="oww-mic")
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def is_running(self) -> bool:
        return self._running and bool(self._thread and self._thread.is_alive())

    def _run_mic_loop(self) -> None:
        try:
            from openwakeword.model import Model  # type: ignore[import]
        except ImportError:
            logger.warning("openwakeword not installed — OpenWakeWordEngine thread exiting")
            self._running = False
            return

        try:
            import pyaudio  # type: ignore[import]
            import numpy as np  # type: ignore[import]
        except ImportError as exc:
            logger.warning("Missing audio dependency for OpenWakeWordEngine: %s", exc)
            self._running = False
            return

        model_args: dict = {"wakeword_models": [self._model_path]} if self._model_path else {}
        try:
            oww = Model(**model_args, inference_framework="onnx")
        except Exception as exc:
            logger.warning("Failed to load OpenWakeWord model: %s", exc)
            self._running = False
            return

        audio = pyaudio.PyAudio()
        CHUNK = 1280
        try:
            stream = audio.open(
                format=pyaudio.paInt16, channels=1, rate=16000,
                input=True, frames_per_buffer=CHUNK,
            )
        except Exception as exc:
            logger.warning("Failed to open mic for OpenWakeWordEngine: %s", exc)
            audio.terminate()
            self._running = False
            return

        logger.debug("OpenWakeWord mic loop started")
        try:
            while self._running:
                pcm = stream.read(CHUNK, exception_on_overflow=False)
                audio_data = np.frombuffer(pcm, dtype=np.int16)
                predictions = oww.predict(audio_data)
                for model_name, score in predictions.items():
                    if score >= self._sensitivity:
                        logger.debug("Wakeword detected: %s (score=%.3f)", model_name, score)
                        if self._callback and self._loop:
                            asyncio.run_coroutine_threadsafe(self._callback(), self._loop)
                        break
        except Exception as exc:
            logger.warning("OpenWakeWord mic loop error: %s", exc)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
            audio.terminate()
            self._running = False
            logger.debug("OpenWakeWord mic loop stopped")


def _is_openwakeword_available() -> bool:
    try:
        import openwakeword  # type: ignore[import]  # noqa: F401
        return True
    except ImportError:
        return False


def create_wakeword_engine(
    settings: dict,
) -> NullWakewordEngine | SoftwareWakewordEngine | OpenWakeWordEngine:
    enabled_env = os.getenv("JARVIS_WAKEWORD_ENABLED", "").strip().lower()
    if enabled_env in {"0", "false", "no", "off"}:
        return NullWakewordEngine()

    engine_env = os.getenv("JARVIS_WAKEWORD_ENGINE", "").strip().lower()
    engine_cfg = engine_env or settings.get("voice", {}).get("wakeword_engine", "software")

    if engine_cfg == "none":
        return NullWakewordEngine()

    if engine_cfg == "openwakeword":
        return _make_openwakeword_engine(settings)

    phrase = _resolve_phrase(settings)
    if engine_cfg != "software":
        logger.warning("Unknown JARVIS_WAKEWORD_ENGINE=%r — falling back to software", engine_cfg)
    return SoftwareWakewordEngine(phrase=phrase)


def _resolve_phrase(settings: dict) -> str:
    env_phrase = os.getenv("JARVIS_WAKEWORD_PHRASE", "").strip().lower()
    return env_phrase or settings.get("voice", {}).get("wakeword_phrase", "hey jarvis")


def _make_openwakeword_engine(
    settings: dict,
) -> OpenWakeWordEngine | SoftwareWakewordEngine:
    try:
        import openwakeword  # type: ignore[import]  # noqa: F401
    except ImportError:
        logger.warning(
            "JARVIS_WAKEWORD_ENGINE=openwakeword but openwakeword is not installed"
            " — falling back to software mode"
        )
        return SoftwareWakewordEngine(phrase=_resolve_phrase(settings))

    sens_env = os.getenv("JARVIS_WAKEWORD_SENSITIVITY", "").strip()
    sensitivity: float = float(settings.get("voice", {}).get("wakeword_sensitivity", 0.5))
    if sens_env:
        try:
            sensitivity = float(sens_env)
        except ValueError:
            pass

    model_path = os.getenv("JARVIS_WAKEWORD_MODEL_PATH", "").strip()
    return OpenWakeWordEngine(model_path=model_path, sensitivity=sensitivity)
