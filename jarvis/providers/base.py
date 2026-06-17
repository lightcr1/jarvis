from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable

from ..model_router import Tier


@dataclass
class ChatChunk:
    token: str


@dataclass
class ChatResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    provider: str


@dataclass
class ModelInfo:
    id: str
    label: str
    tier: Tier
    input_price_per_mtok_usd: float
    output_price_per_mtok_usd: float
    supports_streaming: bool = True


@runtime_checkable
class AIProvider(Protocol):
    name: str
    supports_streaming: bool

    def list_models(self) -> list[ModelInfo]: ...

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int,
        tier: Tier,
        stream: bool,
    ) -> Iterator[ChatChunk] | ChatResult: ...

    def estimate_cost(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        price_table: dict | None = None,
    ) -> float: ...

    def validate_api_key(self, api_key: str) -> tuple[bool, str]: ...


class BaseProvider:
    """ABC with shared default implementations."""

    name: str = "base"
    supports_streaming: bool = True

    def list_models(self) -> list[ModelInfo]:
        return []

    def estimate_cost(
        self,
        *,
        model: str,
        input_tokens: int,
        output_tokens: int,
        price_table: dict | None = None,
    ) -> float:
        if not price_table:
            return 0.0
        entry = price_table.get(model) or price_table.get(f"{self.name}/{model}")
        if not entry:
            return 0.0
        in_price = float(entry.get("in", 0.0))
        out_price = float(entry.get("out", 0.0))
        return (input_tokens / 1_000_000) * in_price + (output_tokens / 1_000_000) * out_price

    def validate_api_key(self, api_key: str) -> tuple[bool, str]:
        return True, "skipped"

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int,
        tier: Tier,
        stream: bool,
    ) -> Iterator[ChatChunk] | ChatResult:
        raise NotImplementedError
