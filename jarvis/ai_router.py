"""AIRouter — unified provider resolution, preflight checks, and usage tracking.

Provider precedence:
  1. BYOK key (user owns a key for a specific provider)
  2. OpenRouter default (OPENROUTER_API_KEY set + openrouter_enabled)
  3. Direct env key (ANTHROPIC_API_KEY / OPENAI_API_KEY / etc.)
  4. Local fallback

Feature-flagged in api_auth_chat.py via JARVIS_USE_AI_ROUTER=1.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Iterator

from .model_router import Tier, classify_complexity, select_model, max_tokens_for

_ENV_KEYS: dict[str, str] = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "mistral": "MISTRAL_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}

_PROVIDER_ORDER = ["openrouter", "anthropic", "openai", "gemini", "mistral", "deepseek"]


@dataclass
class RoutingDecision:
    provider: str
    model: str
    tier: Tier
    billing_mode: str            # "system" | "credit" | "local"
    api_key_source: str          # "byok" | "system" | "local"
    api_key: str | None          # decrypted; NEVER log or return this
    estimated_cost_usd: float
    estimated_cost_chf: float
    clamped_max_tokens: int | None = None


@dataclass
class PreflightResult:
    allowed: bool
    reason: str | None
    requires_confirmation: bool
    billing_confirmation: dict | None
    clamped_max_tokens: int | None
    decision: RoutingDecision


def _day_start(ts: int) -> int:
    return (ts // 86400) * 86400


def _month_start(ts: int) -> int:
    import datetime as _dt
    d = _dt.datetime.utcfromtimestamp(ts)
    return int(_dt.datetime(d.year, d.month, 1).timestamp())


class AIRouter:
    """Central routing hub for all LLM calls.

    Inject real stores for production; inject lightweight stubs for tests.
    Provider calls use the jarvis.providers package; inject provider_factory
    to override for tests (maps provider name → AIProvider instance).
    """

    def __init__(
        self,
        *,
        byok_store=None,
        usage_log_store=None,
        credit_store=None,
        user_limits_store=None,
        admin_settings_store=None,
        build_context_reply=None,
        provider_factory=None,    # dict[str, AIProvider] or callable(name, api_key) → AIProvider
        rate_limiter=None,        # jarvis.rate_limiter.RateLimiter instance
    ):
        self._byok = byok_store
        self._usage = usage_log_store
        self._credits = credit_store
        self._limits = user_limits_store
        self._settings = admin_settings_store
        self._fallback = build_context_reply or (lambda t: "Standing by.")
        self._provider_factory = provider_factory
        self._rate = rate_limiter

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def resolve(
        self,
        *,
        user_id: str | None,
        role: str = "guest_restricted",
        text: str,
        history_len: int = 0,
        voice_mode: bool = False,
    ) -> RoutingDecision:
        ps = self._provider_settings()
        tier = classify_complexity(text, history_len=history_len, voice_mode=voice_mode)
        provider, api_key, src = self._resolve_provider(user_id, ps)
        model = select_model(tier, provider)
        max_tok = max_tokens_for(tier)
        cost_usd = self._estimate_cost_usd(provider, model, text, max_tok, ps)
        cost_chf = cost_usd * float(ps.get("usd_to_chf_rate") or 0.90)

        # Guests always get local; identified users get system budget
        if provider == "local":
            billing_mode = "local"
        elif not user_id:
            billing_mode = "local"
        else:
            billing_mode = "system"

        return RoutingDecision(
            provider=provider,
            model=model,
            tier=tier,
            billing_mode=billing_mode,
            api_key_source=src,
            api_key=api_key,
            estimated_cost_usd=cost_usd,
            estimated_cost_chf=cost_chf,
        )

    def preflight(
        self,
        decision: RoutingDecision,
        *,
        user_id: str | None,
        confirmed: bool = False,
    ) -> PreflightResult:
        ps = self._provider_settings()

        def _block(reason: str) -> PreflightResult:
            return PreflightResult(
                allowed=False,
                reason=reason,
                requires_confirmation=False,
                billing_confirmation=None,
                clamped_max_tokens=decision.clamped_max_tokens,
                decision=decision,
            )

        def _ok(clamp=None) -> PreflightResult:
            return PreflightResult(
                allowed=True,
                reason=None,
                requires_confirmation=False,
                billing_confirmation=None,
                clamped_max_tokens=clamp,
                decision=decision,
            )

        # 1. Kill switch
        if ps.get("kill_switch"):
            return _block("kill_switch")

        # 2. Expensive models disabled globally
        threshold = float(ps.get("expensive_threshold_chf") or 0.10)
        if ps.get("disable_expensive_models") and decision.estimated_cost_chf > threshold:
            return _block("expensive_models_disabled")

        now = int(time.time())
        limits = self._limits.get(user_id) if (user_id and self._limits) else {}

        # 3. Per-user rate limit
        if self._rate and user_id:
            rpm = int(limits.get("requests_per_min") or 30)
            if not self._rate.allow(f"ai_router:{user_id}", limit=rpm, window=60.0):
                return _block("rate_limit")

        # 4. Per-user allowed_models
        allowed_models: list = limits.get("allowed_models") or []
        if allowed_models and decision.model not in allowed_models:
            return _block("model_not_allowed")

        # 5. Per-user tokens/request clamp
        tokens_cap = int(limits.get("tokens_per_request") or 0)
        clamp = tokens_cap if tokens_cap > 0 else None

        # 6. Per-user CHF/day + CHF/month spend limits
        if user_id and self._usage:
            chf_per_day = float(limits.get("chf_per_day") or 0)
            chf_per_month = float(limits.get("chf_per_month") or 0)
            if chf_per_day > 0:
                spent_day = self._usage.aggregate(user_id=user_id, since_ts=_day_start(now))
                if spent_day["total_cost_chf"] + decision.estimated_cost_chf > chf_per_day:
                    return _block("daily_budget_exceeded")
            if chf_per_month > 0:
                spent_month = self._usage.aggregate(user_id=user_id, since_ts=_month_start(now))
                if spent_month["total_cost_chf"] + decision.estimated_cost_chf > chf_per_month:
                    return _block("monthly_budget_exceeded")

        # 7. Per-user expensive-models-per-day
        exp_per_day = int(limits.get("expensive_models_per_day") or 0)
        if exp_per_day > 0 and decision.estimated_cost_chf > threshold and user_id and self._usage:
            today_exp = self._usage.aggregate(user_id=user_id, since_ts=_day_start(now), billing_mode="system")
            # Count entries above threshold — not perfect but good enough
            expensive_today = today_exp.get("expensive_request_count", 0)
            if expensive_today >= exp_per_day:
                return _block("expensive_models_daily_limit")

        # 8. System-wide global daily/monthly budget
        global_daily = float(ps.get("global_daily_budget_chf") or 0)
        global_monthly = float(ps.get("global_monthly_budget_chf") or 0)
        if self._usage:
            if global_daily > 0:
                sys_day = self._usage.aggregate(since_ts=_day_start(now))
                if sys_day["total_cost_chf"] + decision.estimated_cost_chf > global_daily:
                    return _block("global_daily_budget_exceeded")
            if global_monthly > 0:
                sys_month = self._usage.aggregate(since_ts=_month_start(now))
                if sys_month["total_cost_chf"] + decision.estimated_cost_chf > global_monthly:
                    return _block("global_monthly_budget_exceeded")

        # 9. Hard-stop at zero balance (credit mode)
        if decision.billing_mode == "credit" and user_id and self._credits:
            balance = self._credits.get_balance(user_id)
            if balance < decision.estimated_cost_chf:
                return _block("insufficient_balance")

        # 10. Expensive-model confirmation (unless already confirmed)
        if decision.estimated_cost_chf > threshold and not confirmed:
            balance = self._credits.get_balance(user_id) if (self._credits and user_id) else 0.0
            return PreflightResult(
                allowed=False,
                reason="confirmation_required",
                requires_confirmation=True,
                billing_confirmation={
                    "provider": decision.provider,
                    "model": decision.model,
                    "estimated_cost_chf": round(decision.estimated_cost_chf, 6),
                    "balance_chf": round(balance, 4),
                },
                clamped_max_tokens=clamp,
                decision=decision,
            )

        return _ok(clamp)

    def run_stream(
        self,
        decision: RoutingDecision,
        *,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> Iterator[str]:
        max_tok = decision.clamped_max_tokens or max_tokens or max_tokens_for(decision.tier)
        provider = self._get_provider(decision.provider, decision.api_key)
        from .providers.base import ChatChunk
        result = provider.create_chat_completion(
            model=decision.model,
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tok,
            tier=decision.tier,
            stream=True,
        )
        for chunk in result:
            if isinstance(chunk, ChatChunk):
                yield chunk.token
            else:
                yield str(chunk)

    def run_once(
        self,
        decision: RoutingDecision,
        *,
        messages: list[dict],
        system_prompt: str,
        max_tokens: int | None = None,
    ) -> str:
        max_tok = decision.clamped_max_tokens or max_tokens or max_tokens_for(decision.tier)
        provider = self._get_provider(decision.provider, decision.api_key)
        result = provider.create_chat_completion(
            model=decision.model,
            messages=messages,
            system_prompt=system_prompt,
            max_tokens=max_tok,
            tier=decision.tier,
            stream=False,
        )
        return getattr(result, "text", str(result))

    def finalize(
        self,
        decision: RoutingDecision,
        *,
        user_id: str | None,
        conversation_id: str | None,
        input_tokens: int,
        output_tokens: int,
        status: str = "ok",
        error: str | None = None,
    ) -> None:
        ps = self._provider_settings()
        price_table = ps.get("model_prices") or {}
        usd_to_chf = float(ps.get("usd_to_chf_rate") or 0.90)
        provider_inst = self._get_provider(decision.provider, None)
        cost_usd = provider_inst.estimate_cost(
            model=decision.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            price_table=price_table,
        )
        cost_chf = cost_usd * usd_to_chf
        if self._usage:
            self._usage.log({
                "user_id": user_id,
                "conversation_id": conversation_id,
                "provider": decision.provider,
                "model": decision.model,
                "billing_mode": decision.billing_mode,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "estimated_cost_usd": round(cost_usd, 8),
                "estimated_cost_chf": round(cost_chf, 8),
                "request_status": status,
                "error": error,
            })
        if decision.billing_mode == "credit" and user_id and self._credits and cost_chf > 0:
            self._credits.deduct(user_id, cost_chf, note=f"{decision.provider}/{decision.model}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _provider_settings(self) -> dict:
        if self._settings:
            s = self._settings.get() if callable(self._settings.get) else self._settings.get
            if callable(s):
                s = s()
            return (s or {}).get("provider") or {}
        return {}

    def _resolve_provider(
        self, user_id: str | None, ps: dict
    ) -> tuple[str, str | None, str]:
        # 1. BYOK — user's own key for any provider
        if user_id and self._byok:
            for p in _PROVIDER_ORDER:
                if self._byok.has_key(user_id, p):
                    key = self._byok.get_decrypted_key(user_id, p)
                    if key:
                        return p, key, "byok"

        # 2. OpenRouter default
        if ps.get("openrouter_enabled", True):
            or_key = os.getenv("OPENROUTER_API_KEY")
            if or_key:
                return "openrouter", or_key, "system"

        # 3. Direct env keys in priority order
        for p in ["anthropic", "openai", "gemini", "mistral", "deepseek"]:
            env = _ENV_KEYS.get(p, "")
            val = os.getenv(env)
            if val:
                return p, val, "system"

        # 4. Local fallback
        return "local", None, "local"

    def resolve_system_fallback(
        self, original_decision: RoutingDecision
    ) -> "RoutingDecision | None":
        """Return a fallback decision using system env keys (skipping BYOK).

        Used when the primary provider fails at runtime (quota, auth, etc.).
        Returns None if no system provider is available or if the original was
        already a system/local provider (avoid infinite retry loops).
        """
        if original_decision.api_key_source != "byok":
            return None
        ps = self._provider_settings()
        if ps.get("openrouter_enabled", True):
            or_key = os.getenv("OPENROUTER_API_KEY")
            if or_key:
                return self._make_decision("openrouter", or_key, "system", ps)
        for p in ["anthropic", "openai", "gemini", "mistral", "deepseek"]:
            val = os.getenv(_ENV_KEYS.get(p, ""))
            if val:
                return self._make_decision(p, val, "system", ps)
        return None

    def _make_decision(
        self, provider: str, api_key: str | None, src: str, ps: dict
    ) -> RoutingDecision:
        from .model_router import Tier as _Tier, select_model as _sel, max_tokens_for as _mt
        tier = _Tier.SIMPLE
        model = _sel(tier, provider)
        max_tok = _mt(tier)
        cost_usd = self._estimate_cost_usd(provider, model, "", max_tok, ps)
        cost_chf = cost_usd * float(ps.get("usd_to_chf_rate") or 0.90)
        billing = "local" if provider == "local" else "system"
        return RoutingDecision(
            provider=provider, model=model, tier=tier,
            billing_mode=billing, api_key_source=src, api_key=api_key,
            estimated_cost_usd=cost_usd, estimated_cost_chf=cost_chf,
        )

    def _estimate_cost_usd(
        self, provider: str, model: str, text: str, max_tokens: int, ps: dict
    ) -> float:
        if provider == "local":
            return 0.0
        price_table = ps.get("model_prices") or {}
        # Estimate ~input_tokens from text length, ~output = max_tokens/2
        est_input = max(1, len(text) // 4)
        est_output = max_tokens // 2
        inst = self._get_provider(provider, None)
        return inst.estimate_cost(
            model=model,
            input_tokens=est_input,
            output_tokens=est_output,
            price_table=price_table,
        )

    def _get_provider(self, name: str, api_key: str | None):
        if self._provider_factory is not None:
            if isinstance(self._provider_factory, dict):
                return self._provider_factory[name]
            return self._provider_factory(name, api_key)
        from .providers import get_provider_instance
        return get_provider_instance(name, api_key=api_key)
