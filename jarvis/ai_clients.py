import os
import json
import urllib.error
import urllib.request
from typing import Generator

from fastapi import HTTPException
from google import genai
from openai import OpenAI
from faster_whisper import WhisperModel

_openai_client: OpenAI | None = None
_gemini_client: genai.Client | None = None
_anthropic_client = None
_whisper: WhisperModel | None = None

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S. — Just A Rather Very Intelligent System — "
    "the AI backbone of a private smart home and infrastructure network. "
    "Speak with calm authority and dry wit. Be concise and precise."
)


def build_system_prompt(
    user_name: str | None = None,
    voice_mode: bool = False,
    location: str | None = None,
    notes: list[str] | None = None,
    persona_tone: str = "formal",
) -> str:
    name_line = f" Address the user as '{user_name}'." if user_name else ""
    context_parts = []
    if location:
        context_parts.append(f"User location: {location}.")
    if notes:
        context_parts.append(f"User's personal notes: {'; '.join(notes[:10])}.")
    context_line = ("\n\nPERSONAL CONTEXT: " + " ".join(context_parts)) if context_parts else ""
    voice_line = (
        "\n\nVOICE MODE: This response will be spoken aloud by text-to-speech. "
        "Use absolutely NO markdown formatting — no asterisks, no hashtags, no backticks, no bullet points, no numbered lists. "
        "Write for speech only. Keep to one or two sentences maximum."
    ) if voice_mode else ""
    tone_line = (
        "\n\nTONE ADJUSTMENT: Adopt a slightly warmer, more conversational tone — still precise, but less terse."
    ) if persona_tone == "casual" else ""
    return (
        "You are J.A.R.V.I.S. — Just A Rather Very Intelligent System — the personal AI of this "
        "household and infrastructure network. You embody the JARVIS from the Iron Man films: calm, "
        "precise, witty, and comprehensively knowledgeable. You answer any question on any topic "
        "with the quiet confidence of someone who already knows the answer."
        f"{name_line}\n\n"
        "TONE: Confident and brief. For questions and conversation, answer directly without preamble. "
        "For actions and commands, open with a short acknowledgment ('On it.', 'Of course.', "
        "'Right away.', 'Naturally.') — vary it, never repeat the same opener twice in a row. "
        "Dry wit is welcome when appropriate. No padding, no filler, no apologies.\n\n"
        "FORMAT: Default to one or two sentences. For technical data (status, metrics, lists), use "
        "compact formatting. Only expand when the user explicitly asks for detail.\n\n"
        "SCOPE: You handle home automation (lights, climate, sensors), server infrastructure "
        "(Proxmox VMs, containers), system controls, and knowledge retrieval — but you are also a "
        "general intelligence. Answer questions about history, science, sports, culture, current "
        "events, and anything else directly, as JARVIS would. Never claim a topic is outside your "
        "domain or redirect the user elsewhere.\n\n"
        "CONSTRAINTS: Never identify yourself as a language model or AI assistant. "
        "Never say 'I cannot' — find a way or be direct about what is needed. "
        "Never break character."
        f"{context_line}"
        f"{voice_line}"
        f"{tone_line}"
    )
def get_provider() -> str:
    configured = (os.getenv("LLM_PROVIDER") or "").lower().strip()
    if configured:
        return configured
    if os.getenv("ANTHROPIC_API_KEY"):
        return "anthropic"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if (os.getenv("LOCAL_LLM_ENABLED") or "").strip() in {"1", "true", "yes", "on"}:
        return "local"
    return "openai"


def get_local_model_dir() -> str:
    return os.getenv("LOCAL_LLM_MODEL_DIR") or "/var/lib/jarvis/local-ai/models"


def get_local_base_url() -> str:
    return (
        os.getenv("LOCAL_LLM_BASE_URL")
        or os.getenv("OLLAMA_HOST")
        or "http://127.0.0.1:11434"
    ).rstrip("/")


def get_local_default_model() -> str:
    return (os.getenv("LOCAL_LLM_DEFAULT_MODEL") or "").strip()


def get_local_backend() -> str:
    configured = (os.getenv("LOCAL_LLM_BACKEND") or "").strip().lower()
    if configured in {"ollama", "llama_cpp", "auto"}:
        return configured
    return "auto"


def _local_http_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="ignore") if exc.fp else exc.reason
        raise HTTPException(exc.code, f"Local AI HTTP error: {details or exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(502, f"Local AI unreachable: {exc.reason}") from exc
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(502, f"Local AI invalid JSON: {exc}") from exc


def _flatten_messages(messages: list[dict[str, str]], system_prompt: str) -> str:
    lines = [system_prompt.strip(), ""]
    for item in messages:
        role = str(item.get("role") or "user").strip().lower()
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        speaker = "Assistant" if role == "assistant" else "User"
        lines.append(f"{speaker}: {content}")
    lines.append("Assistant:")
    return "\n".join(lines)


def _call_ollama(base_url: str, model: str, text: str) -> str:
    payload = {
        "model": model,
        "prompt": text,
        "system": SYSTEM_PROMPT,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        },
    }
    data = _local_http_json(f"{base_url}/api/generate", payload)
    reply = (data.get("response") or "").strip()
    if not reply:
        raise HTTPException(502, "Local AI returned an empty Ollama response")
    return reply


def _call_ollama_chat(base_url: str, model: str, messages: list[dict[str, str]], system_prompt: str) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        },
    }
    data = _local_http_json(f"{base_url}/api/chat", payload)
    message = data.get("message") or {}
    reply = (message.get("content") or "").strip()
    if not reply:
        raise HTTPException(502, "Local AI returned an empty Ollama chat response")
    return reply


def _call_llama_cpp_openai(base_url: str, model: str, text: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.3,
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        "stream": False,
    }
    data = _local_http_json(f"{base_url}/v1/chat/completions", payload)
    choices = data.get("choices") or []
    if not choices:
        raise HTTPException(502, "Local AI returned no choices")
    message = choices[0].get("message") or {}
    reply = (message.get("content") or "").strip()
    if not reply:
        raise HTTPException(502, "Local AI returned an empty chat completion")
    return reply


def _call_llama_cpp_openai_chat(base_url: str, model: str, messages: list[dict[str, str]], system_prompt: str) -> str:
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "temperature": 0.3,
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        "stream": False,
    }
    data = _local_http_json(f"{base_url}/v1/chat/completions", payload)
    choices = data.get("choices") or []
    if not choices:
        raise HTTPException(502, "Local AI returned no choices")
    message = choices[0].get("message") or {}
    reply = (message.get("content") or "").strip()
    if not reply:
        raise HTTPException(502, "Local AI returned an empty chat completion")
    return reply


def _call_llama_cpp_completion(base_url: str, text: str) -> str:
    prompt = f"{SYSTEM_PROMPT}\n\nUser: {text}\nAssistant:"
    payload = {
        "prompt": prompt,
        "temperature": 0.3,
        "n_predict": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        "stop": ["User:"],
    }
    data = _local_http_json(f"{base_url}/completion", payload)
    reply = (data.get("content") or "").strip()
    if not reply:
        raise HTTPException(502, "Local AI returned an empty completion")
    return reply


def _call_llama_cpp_completion_chat(base_url: str, messages: list[dict[str, str]], system_prompt: str) -> str:
    prompt = _flatten_messages(messages, system_prompt)
    payload = {
        "prompt": prompt,
        "temperature": 0.3,
        "n_predict": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        "stop": ["User:"],
    }
    data = _local_http_json(f"{base_url}/completion", payload)
    reply = (data.get("content") or "").strip()
    if not reply:
        raise HTTPException(502, "Local AI returned an empty completion")
    return reply


def local_ai_chat_reply(messages: list[dict[str, str]], system_prompt: str = SYSTEM_PROMPT) -> str:
    model_dir = get_local_model_dir()
    model_hint = get_local_default_model()
    model_exists = os.path.isdir(model_dir) and any(os.scandir(model_dir))
    base_url = get_local_base_url()
    backend = get_local_backend()

    if not model_hint:
        return "Understood. Local AI is enabled, but LOCAL_LLM_DEFAULT_MODEL is not set."

    if backend == "auto":
        backend = "ollama" if ("11434" in base_url or "ollama" in base_url.lower()) else "llama_cpp"

    try:
        if backend == "ollama":
            return _call_ollama_chat(base_url, model_hint, messages, system_prompt)
        if backend == "llama_cpp":
            if model_exists:
                try:
                    return _call_llama_cpp_openai_chat(base_url, model_hint, messages, system_prompt)
                except HTTPException:
                    return _call_llama_cpp_completion_chat(base_url, messages, system_prompt)
            return _call_llama_cpp_openai_chat(base_url, model_hint, messages, system_prompt)
        return f"Understood. Unsupported local backend '{backend}'."
    except HTTPException as exc:
        if not model_exists and backend == "llama_cpp":
            return (
                "Understood. Local AI could not reach the llama.cpp server, and no local model files were "
                f"found in {model_dir} (default={model_hint}). Detail: {exc.detail}"
            )
        return f"Understood. Local AI request failed. Detail: {exc.detail}"


def local_ai_stub_reply(text: str) -> str:
    return local_ai_chat_reply([{"role": "user", "content": text}], SYSTEM_PROMPT)


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


def get_anthropic():
    global _anthropic_client
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise HTTPException(500, "ANTHROPIC_API_KEY not set")
    if _anthropic_client is None:
        import anthropic as _sdk
        _anthropic_client = _sdk.Anthropic(api_key=api_key)
    return _anthropic_client


def anthropic_stream_reply(
    messages: list[dict],
    system_prompt: str,
    tier,
) -> Generator[str, None, None]:
    """Stream reply from Anthropic with prompt caching and tier-appropriate params.

    - Haiku (simple): no thinking, no effort (Haiku 4.5 does not support effort)
    - Sonnet (medium): effort=medium, no thinking
    - Opus (complex): adaptive thinking, effort=high, no sampling params
    """
    from .model_router import Tier, select_model, max_tokens_for

    client = get_anthropic()
    model = select_model(tier, "anthropic")
    max_tokens = max_tokens_for(tier)

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "system": [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
    }

    if tier == Tier.COMPLEX:
        kwargs["thinking"] = {"type": "adaptive"}
        kwargs["output_config"] = {"effort": "high"}
    elif tier == Tier.MEDIUM:
        kwargs["output_config"] = {"effort": "medium"}
    # Haiku (SIMPLE): no extra params — effort errors on Haiku 4.5

    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            yield text


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
