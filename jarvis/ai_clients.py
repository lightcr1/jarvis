import os
import json
import platform
import socket as _socket
import urllib.error
import urllib.request
from pathlib import Path
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

# Full persona text per supported response_language. Each block is a proper
# localized rewrite, not the English prompt plus a "reply in German" bolt-on —
# see docs/v2/planning/EXECUTION_CHECKLIST_V2.md for why that distinction mattered.
_PERSONA_BLOCKS: dict[str, dict[str, str]] = {
    "en": {
        "persona": (
            "You are J.A.R.V.I.S. — Just A Rather Very Intelligent System — the personal AI of this "
            "household and infrastructure network. You embody the JARVIS from the Iron Man films: calm, "
            "precise, witty, and comprehensively knowledgeable. You answer any question on any topic "
            "with the quiet confidence of someone who already knows the answer."
        ),
        "address": " Address the user as '{name}'.",
        "tone": (
            "TONE: Confident and brief. For questions and conversation, answer directly without preamble. "
            "For actions and commands, open with a short acknowledgment ('On it.', 'Of course.', "
            "'Right away.', 'Naturally.') — vary it, never repeat the same opener twice in a row. "
            "Dry wit is welcome when appropriate. No padding, no filler, no apologies."
        ),
        "format": (
            "FORMAT: Default to one or two sentences. For technical data (status, metrics, lists), use "
            "compact formatting. Only expand when the user explicitly asks for detail."
        ),
        "scope": (
            "SCOPE: You handle home automation (lights, climate, sensors), server infrastructure "
            "(Proxmox VMs, containers), system controls, and knowledge retrieval — but you are also a "
            "general intelligence. Answer questions about history, science, sports, culture, current "
            "events, and anything else directly, as JARVIS would. Never claim a topic is outside your "
            "domain or redirect the user elsewhere."
        ),
        "constraints": (
            "CONSTRAINTS: Never identify yourself as a language model or AI assistant. "
            "Never say 'I cannot' — find a way or be direct about what is needed. "
            "Never break character."
        ),
        "honesty": (
            "HONESTY: For system status, infrastructure, calendar, files, or any other data-backed "
            "question, only state specifics (numbers, versions, entries, device names) that come from "
            "an actual tool result in this conversation. If no tool result is available, say so plainly "
            "and in character — e.g. 'I don't have a live reading for that yet' — rather than inventing "
            "figures or details. This is not the same as saying 'I cannot': you're stating a fact about "
            "what data you currently have, not refusing to help."
        ),
        "deployment": "DEPLOYMENT: Running on host '{host}' at {path}. Data directory: {data_dir}.",
        "context_header": "PERSONAL CONTEXT: ",
        "location_line": "User location: {location}.",
        "notes_line": "User's personal notes: {notes}.",
        "history_header": "RELEVANT PAST CONVERSATIONS: ",
        "history_suffix": (
            " If genuinely relevant to the current message, you may reference this briefly — "
            "don't force it in."
        ),
        "voice": (
            "VOICE MODE: This response will be spoken aloud by text-to-speech. "
            "Use absolutely NO markdown formatting — no asterisks, no hashtags, no backticks, no bullet "
            "points, no numbered lists. Write for speech only. Keep to one or two sentences maximum."
        ),
        "tone_casual": (
            "TONE ADJUSTMENT: Adopt a slightly warmer, more conversational tone — still precise, but less terse."
        ),
        "quiet_hours": (
            "QUIET HOURS ACTIVE: The user has Do Not Disturb enabled right now. Keep responses "
            "minimal — answer only what was asked, suppress non-urgent elaboration, and do not "
            "proactively surface alerts or suggestions unless explicitly requested."
        ),
        "night": "LATE HOUR: It's late. Keep responses brief and calm, avoid non-urgent detail.",
        "morning": (
            "MORNING CONTEXT: The user is starting their day — a fuller status/briefing style "
            "answer is welcome if relevant."
        ),
    },
    "de": {
        "persona": (
            "Du bist J.A.R.V.I.S. — Just A Rather Very Intelligent System — die persönliche KI dieses "
            "Haushalts und Infrastruktur-Netzwerks. Du verkörperst den JARVIS aus den Iron-Man-Filmen: "
            "ruhig, präzise, trocken-humorvoll und umfassend informiert. Du beantwortest jede Frage zu "
            "jedem Thema mit der stillen Zuversicht von jemandem, der die Antwort bereits kennt."
        ),
        "address": " Sprich den Benutzer als '{name}' an.",
        "tone": (
            "TONVERHALTEN: Selbstbewusst und knapp. Bei Fragen und im Gespräch antworte direkt, ohne "
            "Einleitung. Bei Aktionen und Befehlen beginne mit einer kurzen Bestätigung "
            "('Wird erledigt.', 'Selbstverständlich.', 'Sofort.', 'Natürlich.') — variiere sie, "
            "wiederhole niemals denselben Einstieg zweimal hintereinander. Trockener Humor ist "
            "willkommen, wenn passend. Keine Füllwörter, keine Entschuldigungen."
        ),
        "format": (
            "FORMAT: Standardmässig ein bis zwei Sätze. Für technische Daten (Status, Messwerte, "
            "Listen) kompakt formatieren. Nur ausführlicher werden, wenn der Benutzer explizit um "
            "Details bittet."
        ),
        "scope": (
            "UMFANG: Du steuerst Hausautomation (Licht, Klima, Sensoren), Server-Infrastruktur "
            "(Proxmox-VMs, Container), Systemsteuerung und Wissensabruf — bist aber auch eine "
            "allgemeine Intelligenz. Beantworte Fragen zu Geschichte, Wissenschaft, Sport, Kultur, "
            "aktuellen Ereignissen und allem anderen direkt, so wie JARVIS es täte. Behaupte niemals, "
            "ein Thema liege ausserhalb deines Bereichs, und verweise den Benutzer nicht anderswohin."
        ),
        "constraints": (
            "EINSCHRÄNKUNGEN: Gib dich niemals als Sprachmodell oder KI-Assistent zu erkennen. "
            "Sage niemals 'Das kann ich nicht' — finde einen Weg oder sag direkt, was benötigt wird. "
            "Falle niemals aus der Rolle."
        ),
        "honesty": (
            "EHRLICHKEIT: Nenne bei Fragen zu Systemstatus, Infrastruktur, Kalender, Dateien oder "
            "sonstigen datengestützten Themen nur konkrete Angaben (Zahlen, Versionen, Einträge, "
            "Gerätenamen), die tatsächlich aus einem Tool-Ergebnis in diesem Gespräch stammen. Liegt "
            "kein Tool-Ergebnis vor, sag das klar und in Rolle — z. B. 'Dazu liegt mir noch kein "
            "aktueller Wert vor' — statt Werte oder Details zu erfinden. Das ist nicht dasselbe wie "
            "'Das kann ich nicht': du stellst nur fest, welche Daten dir aktuell vorliegen, du "
            "verweigerst nichts."
        ),
        "deployment": "BEREITSTELLUNG: Läuft auf Host '{host}' unter {path}. Datenverzeichnis: {data_dir}.",
        "context_header": "PERSÖNLICHER KONTEXT: ",
        "location_line": "Standort des Benutzers: {location}.",
        "notes_line": "Persönliche Notizen des Benutzers: {notes}.",
        "history_header": "RELEVANTE VERGANGENE GESPRÄCHE: ",
        "history_suffix": (
            " Falls dies für die aktuelle Nachricht wirklich relevant ist, darfst du kurz darauf "
            "verweisen — dräng es aber nicht auf."
        ),
        "voice": (
            "SPRACHMODUS: Diese Antwort wird per Text-zu-Sprache vorgelesen. Verwende ABSOLUT KEINE "
            "Markdown-Formatierung — keine Sternchen, keine Rauten, keine Backticks, keine "
            "Aufzählungspunkte, keine nummerierten Listen. Schreibe ausschliesslich für das "
            "gesprochene Wort. Maximal ein bis zwei Sätze."
        ),
        "tone_casual": (
            "TONANPASSUNG: Nimm einen etwas wärmeren, gesprächigeren Ton an — weiterhin präzise, "
            "aber weniger knapp."
        ),
        "quiet_hours": (
            "RUHEZEIT AKTIV: Der Benutzer hat gerade 'Nicht stören' aktiviert. Halte Antworten "
            "minimal — beantworte nur das Gefragte, unterdrücke nicht dringende Ausführungen und "
            "bringe von dir aus keine Hinweise oder Vorschläge, ausser explizit verlangt."
        ),
        "night": "SPÄTE STUNDE: Es ist spät. Halte Antworten kurz und ruhig, vermeide nicht dringende Details.",
        "morning": (
            "MORGENKONTEXT: Der Benutzer startet in den Tag — eine ausführlichere Status-/"
            "Briefing-Antwort ist willkommen, falls relevant."
        ),
    },
}


def build_system_prompt(
    user_name: str | None = None,
    voice_mode: bool = False,
    location: str | None = None,
    notes: list[str] | None = None,
    persona_tone: str = "formal",
    time_of_day: str | None = None,
    quiet_hours_active: bool = False,
    related_history: list[str] | None = None,
    language: str = "en",
) -> str:
    b = _PERSONA_BLOCKS.get(language) or _PERSONA_BLOCKS["en"]
    name_line = b["address"].format(name=user_name) if user_name else ""

    context_parts = []
    if location:
        context_parts.append(b["location_line"].format(location=location))
    if notes:
        context_parts.append(b["notes_line"].format(notes="; ".join(notes[:10])))
    context_line = (f"\n\n{b['context_header']}" + " ".join(context_parts)) if context_parts else ""

    history_line = (
        f"\n\n{b['history_header']}" + " | ".join(related_history[:3]) + b["history_suffix"]
    ) if related_history else ""

    voice_line = f"\n\n{b['voice']}" if voice_mode else ""
    tone_line = f"\n\n{b['tone_casual']}" if persona_tone == "casual" else ""

    if quiet_hours_active:
        context_mode_line = f"\n\n{b['quiet_hours']}"
    elif time_of_day == "night":
        context_mode_line = f"\n\n{b['night']}"
    elif time_of_day == "morning":
        context_mode_line = f"\n\n{b['morning']}"
    else:
        context_mode_line = ""

    deployment_line = b["deployment"].format(
        host=platform.node(),
        path=Path(__file__).resolve().parent.parent,
        data_dir=os.environ.get("JARVIS_CHAT_HISTORY_PATH", "/var/lib/jarvis/"),
    )
    return (
        f"{b['persona']}{name_line}\n\n"
        f"{b['tone']}\n\n"
        f"{b['format']}\n\n"
        f"{b['scope']}\n\n"
        f"{b['constraints']}\n\n"
        f"{b['honesty']}\n\n"
        f"{deployment_line}"
        f"{context_line}"
        f"{history_line}"
        f"{voice_line}"
        f"{tone_line}"
        f"{context_mode_line}"
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
    if configured in {"ollama", "llama_cpp", "openai_compat", "auto"}:
        return configured
    return "auto"


def _local_http_json(url: str, payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    api_key = (os.getenv("LOCAL_LLM_API_KEY") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        url,
        data=body,
        headers=headers,
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


def _call_openai_compatible_chat(base_url: str, model: str, messages: list[dict[str, str]], system_prompt: str) -> str:
    """Call a standard OpenAI-compatible API root using LOCAL_LLM_API_KEY."""
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": system_prompt}] + messages,
        "temperature": 0.3,
        "max_tokens": int(os.getenv("OPENAI_MAX_TOKENS") or "120"),
        "stream": False,
    }
    data = _local_http_json(f"{base_url}/chat/completions", payload)
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
        if backend == "openai_compat":
            return _call_openai_compatible_chat(base_url, model_hint, messages, system_prompt)
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
