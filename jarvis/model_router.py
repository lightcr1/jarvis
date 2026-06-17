import re
from enum import Enum


class Tier(str, Enum):
    SIMPLE = "simple"
    MEDIUM = "medium"
    COMPLEX = "complex"


MODELS: dict[str, dict[Tier, str]] = {
    "anthropic": {
        Tier.SIMPLE: "claude-haiku-4-5",
        Tier.MEDIUM: "claude-sonnet-4-6",
        Tier.COMPLEX: "claude-opus-4-8",
    },
    "openai": {
        Tier.SIMPLE: "gpt-4o-mini",
        Tier.MEDIUM: "gpt-4o",
        Tier.COMPLEX: "gpt-4o",
    },
    "gemini": {
        Tier.SIMPLE: "gemini-2.0-flash",
        Tier.MEDIUM: "gemini-2.5-flash",
        Tier.COMPLEX: "gemini-1.5-pro",
    },
    "openrouter": {
        Tier.SIMPLE: "openrouter/free",
        Tier.MEDIUM: "openrouter/free",
        Tier.COMPLEX: "openrouter/free",
    },
    "mistral": {
        Tier.SIMPLE: "mistral-small-latest",
        Tier.MEDIUM: "mistral-medium-latest",
        Tier.COMPLEX: "mistral-large-latest",
    },
    "deepseek": {
        Tier.SIMPLE: "deepseek-chat",
        Tier.MEDIUM: "deepseek-chat",
        Tier.COMPLEX: "deepseek-reasoner",
    },
}

# Preferred fallback order when a provider fails (local is always last resort)
PROVIDER_ORDER: list[str] = ["openrouter", "anthropic", "openai", "gemini", "mistral", "deepseek", "local"]

MAX_TOKENS: dict[Tier, int] = {
    Tier.SIMPLE: 256,
    Tier.MEDIUM: 1024,
    Tier.COMPLEX: 4096,
}

_COMPLEX_RE = re.compile(
    r"\b(explain|analyze|analyse|compare|design|implement|refactor|debug|architecture|"
    r"how does|why does|trade.?off|pros and cons|in depth|detailed|"
    r"write a|create a|build a|generate|code|algorithm|system|infrastructure|"
    r"database|security|optimize|optimise|performance|step by step)\b",
    re.IGNORECASE,
)
_MEDIUM_RE = re.compile(
    r"\b(help me|can you|could you|what is|what are|how to|"
    r"list|summarize|summarise|suggest|recommend|describe|"
    r"difference between|tell me about)\b",
    re.IGNORECASE,
)


def classify_complexity(
    text: str,
    history_len: int = 0,
    voice_mode: bool = False,
) -> Tier:
    t = (text or "").strip()
    word_count = len(t.split())

    if voice_mode and word_count <= 15:
        return Tier.SIMPLE

    if word_count > 150:
        return Tier.COMPLEX

    score = (len(_COMPLEX_RE.findall(t)) * 3) + len(_MEDIUM_RE.findall(t))

    if word_count > 60:
        score += 2

    if history_len >= 10:
        score += 3
    elif history_len >= 4:
        score += 1

    if score >= 6:
        return Tier.COMPLEX
    if score >= 2:
        return Tier.MEDIUM
    return Tier.SIMPLE


def select_model(tier: Tier, provider: str) -> str:
    return MODELS.get(provider, MODELS["openai"]).get(tier, MODELS["openai"][Tier.MEDIUM])


def max_tokens_for(tier: Tier) -> int:
    return MAX_TOKENS[tier]


def should_use_extended_thinking(tier: Tier, provider: str) -> bool:
    return tier == Tier.COMPLEX and provider == "anthropic"
