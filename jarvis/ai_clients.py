import os

from fastapi import HTTPException
from google import genai
from openai import OpenAI
from faster_whisper import WhisperModel

_openai_client: OpenAI | None = None
_gemini_client: genai.Client | None = None
_whisper: WhisperModel | None = None

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S from Iron Man. "
    "Speak concise, confident, technical. "
    "Start responses like 'On it.' or 'Understood.' (vary it). "
    "Then ONE short sentence. No explanations unless explicitly asked or necessary."
)


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
    model_name = os.getenv("WHISPER_MODEL") or "small"
    compute = os.getenv("WHISPER_COMPUTE") or "int8"
    if _whisper is None:
        _whisper = WhisperModel(model_name, device="cpu", compute_type=compute)
    return _whisper
