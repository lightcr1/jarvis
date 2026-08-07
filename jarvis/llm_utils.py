import re


def trim_to_budget(messages: list[dict], budget: int = 4000) -> list[dict]:
    """Drop oldest messages until estimated token count fits within budget (keeps at least 2)."""
    total = sum(len(m.get("content", "")) // 4 for m in messages)
    while total > budget and len(messages) > 2:
        dropped = messages.pop(0)
        total -= len(dropped.get("content", "")) // 4
    return messages


# Some OpenAI-compatible proxy models (notably OpenRouter free-tier reasoning
# models) inline chain-of-thought or a safety-classifier verdict directly in
# message content instead of a separate `reasoning` field. Strip it defensively
# regardless of which underlying model actually gets routed to.
_REASONING_TAGS = ("think", "thinking", "reasoning", "analysis")
_BLOCK_RE = re.compile(
    r"<(?P<tag>" + "|".join(_REASONING_TAGS) + r")>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_SAFETY_PREAMBLE_RE = re.compile(
    r"\A(?:[a-z][\w ]{0,30}safety:\s*\S+\s*\n){1,4}\n*", re.IGNORECASE
)
_OPEN_RE = re.compile(r"<(?:" + "|".join(_REASONING_TAGS) + r")>", re.IGNORECASE)
_CLOSE_RE = re.compile(r"</(?:" + "|".join(_REASONING_TAGS) + r")>", re.IGNORECASE)
_MAX_OPEN_TAG_LEN = max(len(f"<{t}>") for t in _REASONING_TAGS)


def strip_reasoning_artifacts(text: str) -> str:
    if not text:
        return text
    cleaned = _BLOCK_RE.sub("", text)
    cleaned = _SAFETY_PREAMBLE_RE.sub("", cleaned)
    return cleaned.strip()


class ReasoningStreamFilter:
    """Incrementally strips <think>-style reasoning blocks from a token
    stream, tolerating tags split across chunk boundaries."""

    def __init__(self) -> None:
        self._buffer = ""
        self._in_block = False

    def feed(self, token: str) -> str:
        self._buffer += token
        out = []
        while True:
            if self._in_block:
                m = _CLOSE_RE.search(self._buffer)
                if not m:
                    return "".join(out)
                self._buffer = self._buffer[m.end():]
                self._in_block = False
                continue
            m = _OPEN_RE.search(self._buffer)
            if not m:
                keep_from = max(0, len(self._buffer) - _MAX_OPEN_TAG_LEN)
                out.append(self._buffer[:keep_from])
                self._buffer = self._buffer[keep_from:]
                return "".join(out)
            out.append(self._buffer[:m.start()])
            self._buffer = self._buffer[m.end():]
            self._in_block = True

    def flush(self) -> str:
        remainder = "" if self._in_block else self._buffer
        self._buffer = ""
        return remainder
