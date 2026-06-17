"""Tests for AIRouter — Phase 4 routing, preflight, and finalization."""

import os
import tempfile
import time
import unittest
from pathlib import Path

from jarvis.ai_router import AIRouter, RoutingDecision, PreflightResult
from jarvis.model_router import Tier


# ------------------------------------------------------------------
# Minimal store stubs
# ------------------------------------------------------------------

class _AdminSettings:
    def __init__(self, overrides: dict | None = None):
        self._data = {
            "default_provider": "openrouter",
            "openrouter_enabled": True,
            "usd_to_chf_rate": 1.0,
            "model_prices": {},
            "global_daily_budget_chf": 0.0,
            "global_monthly_budget_chf": 0.0,
            "kill_switch": False,
            "disable_expensive_models": False,
            "expensive_threshold_chf": 0.10,
        }
        if overrides:
            self._data.update(overrides)

    def get(self):
        return {"provider": self._data}


class _ByokStore:
    def __init__(self, keys: dict | None = None):
        self._keys = keys or {}  # {(user_id, provider): "raw_key"}

    def has_key(self, user_id: str, provider: str) -> bool:
        return (user_id, provider) in self._keys

    def get_decrypted_key(self, user_id: str, provider: str) -> str | None:
        return self._keys.get((user_id, provider))


class _UsageLogStore:
    def __init__(self):
        self.logged: list[dict] = []

    def log(self, record: dict) -> None:
        self.logged.append(record)

    def aggregate(self, *, user_id=None, provider=None, model=None, billing_mode=None, since_ts=None, until_ts=None) -> dict:
        total_chf = 0.0
        count = 0
        for r in self.logged:
            if user_id and r.get("user_id") != user_id:
                continue
            if since_ts and r.get("ts", 0) < since_ts:
                continue
            total_chf += float(r.get("estimated_cost_chf") or 0)
            count += 1
        return {"total_cost_chf": total_chf, "request_count": count}


class _CreditStore:
    def __init__(self, balances: dict | None = None):
        self._balances = balances or {}
        self.deductions: list[tuple] = []

    def get_balance(self, user_id: str) -> float:
        return float(self._balances.get(user_id, 0.0))

    def deduct(self, user_id: str, amount: float, *, note: str = "") -> tuple[bool, float]:
        bal = self.get_balance(user_id)
        if amount > bal:
            return False, bal
        new_bal = bal - amount
        self._balances[user_id] = new_bal
        self.deductions.append((user_id, amount, note))
        return True, new_bal


class _UserLimitsStore:
    def __init__(self, limits: dict | None = None):
        self._limits = limits or {}

    def get(self, user_id: str) -> dict:
        return self._limits.get(user_id, {})


class _RateLimiter:
    def __init__(self, allow: bool = True):
        self._allow = allow

    def allow(self, key: str, limit: int = 30, window: float = 60.0) -> bool:
        return self._allow


# Provider stubs
class _StubProvider:
    name = "stub"
    supports_streaming = True

    def create_chat_completion(self, *, model, messages, system_prompt, max_tokens, tier, stream):
        from jarvis.providers.base import ChatChunk, ChatResult
        if stream:
            return iter([ChatChunk("hello"), ChatChunk(" world")])
        return ChatResult(text="hello world", input_tokens=10, output_tokens=5, model=model, provider=self.name)

    def estimate_cost(self, *, model, input_tokens, output_tokens, price_table=None):
        if not price_table:
            return 0.0
        entry = price_table.get(model, {})
        return (input_tokens / 1e6) * float(entry.get("in", 0)) + (output_tokens / 1e6) * float(entry.get("out", 0))

    def list_models(self):
        return []

    def validate_api_key(self, key):
        return True, "ok"


def _make_router(**kwargs) -> AIRouter:
    defaults = dict(
        admin_settings_store=_AdminSettings(),
        provider_factory=lambda name, key: _StubProvider(),
    )
    defaults.update(kwargs)
    return AIRouter(**defaults)


# ------------------------------------------------------------------
# resolve() tests
# ------------------------------------------------------------------

class ResolveTests(unittest.TestCase):
    def setUp(self):
        # Make sure no env keys pollute tests
        for k in ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
            os.environ.pop(k, None)

    def test_resolve_returns_routing_decision(self):
        router = _make_router()
        d = router.resolve(user_id="u1", text="hello")
        self.assertIsInstance(d, RoutingDecision)
        self.assertIsNotNone(d.provider)
        self.assertIsNotNone(d.model)
        self.assertIsInstance(d.tier, Tier)

    def test_no_keys_falls_back_to_local(self):
        router = _make_router()
        d = router.resolve(user_id="u1", text="hello")
        self.assertEqual(d.provider, "local")
        self.assertEqual(d.api_key_source, "local")
        self.assertEqual(d.billing_mode, "local")

    def test_openrouter_key_routes_to_openrouter(self):
        os.environ["OPENROUTER_API_KEY"] = "or-test-key"
        try:
            router = _make_router()
            d = router.resolve(user_id="u1", text="hello")
            self.assertEqual(d.provider, "openrouter")
            self.assertEqual(d.api_key_source, "system")
        finally:
            os.environ.pop("OPENROUTER_API_KEY", None)

    def test_byok_takes_precedence_over_openrouter(self):
        os.environ["OPENROUTER_API_KEY"] = "or-test-key"
        try:
            byok = _ByokStore({("u1", "anthropic"): "sk-byok-key"})
            router = _make_router(byok_store=byok)
            d = router.resolve(user_id="u1", text="hello")
            self.assertEqual(d.provider, "anthropic")
            self.assertEqual(d.api_key_source, "byok")
            self.assertEqual(d.api_key, "sk-byok-key")
        finally:
            os.environ.pop("OPENROUTER_API_KEY", None)

    def test_anthropic_env_key_used_when_no_openrouter(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-key"
        try:
            router = _make_router()
            d = router.resolve(user_id="u1", text="hello")
            self.assertEqual(d.provider, "anthropic")
            self.assertEqual(d.api_key_source, "system")
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_guest_user_always_gets_local_billing(self):
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        try:
            router = _make_router()
            d = router.resolve(user_id=None, text="hello")
            self.assertEqual(d.billing_mode, "local")
        finally:
            os.environ.pop("OPENROUTER_API_KEY", None)

    def test_identified_user_gets_system_billing(self):
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        try:
            router = _make_router()
            d = router.resolve(user_id="u1", text="hello")
            self.assertEqual(d.billing_mode, "system")
        finally:
            os.environ.pop("OPENROUTER_API_KEY", None)

    def test_cost_is_zero_for_local(self):
        router = _make_router()
        d = router.resolve(user_id="u1", text="hello")
        self.assertEqual(d.estimated_cost_usd, 0.0)
        self.assertEqual(d.estimated_cost_chf, 0.0)

    def test_openrouter_disabled_skips_to_direct_key(self):
        os.environ["OPENROUTER_API_KEY"] = "or-key"
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-key"
        try:
            router = _make_router(admin_settings_store=_AdminSettings({"openrouter_enabled": False}))
            d = router.resolve(user_id="u1", text="hello")
            self.assertEqual(d.provider, "anthropic")
        finally:
            os.environ.pop("OPENROUTER_API_KEY", None)
            os.environ.pop("ANTHROPIC_API_KEY", None)


# ------------------------------------------------------------------
# preflight() tests
# ------------------------------------------------------------------

class PreflightTests(unittest.TestCase):
    def _decision(self, cost_chf=0.0, provider="local") -> RoutingDecision:
        return RoutingDecision(
            provider=provider,
            model="test-model",
            tier=Tier.SIMPLE,
            billing_mode="system",
            api_key_source="local",
            api_key=None,
            estimated_cost_usd=cost_chf,
            estimated_cost_chf=cost_chf,
        )

    def test_allowed_by_default(self):
        router = _make_router()
        pf = router.preflight(self._decision(), user_id=None)
        self.assertTrue(pf.allowed)
        self.assertFalse(pf.requires_confirmation)

    def test_kill_switch_blocks_all(self):
        router = _make_router(admin_settings_store=_AdminSettings({"kill_switch": True}))
        pf = router.preflight(self._decision(), user_id=None)
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "kill_switch")

    def test_expensive_models_disabled_blocks_above_threshold(self):
        router = _make_router(admin_settings_store=_AdminSettings({
            "disable_expensive_models": True,
            "expensive_threshold_chf": 0.05,
        }))
        pf = router.preflight(self._decision(cost_chf=0.10), user_id="u1")
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "expensive_models_disabled")

    def test_expensive_models_disabled_allows_cheap(self):
        router = _make_router(admin_settings_store=_AdminSettings({
            "disable_expensive_models": True,
            "expensive_threshold_chf": 0.50,
        }))
        pf = router.preflight(self._decision(cost_chf=0.10), user_id="u1")
        self.assertTrue(pf.allowed)

    def test_rate_limit_blocks(self):
        router = _make_router(rate_limiter=_RateLimiter(allow=False))
        pf = router.preflight(self._decision(), user_id="u1")
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "rate_limit")

    def test_allowed_models_blocks_unlisted(self):
        limits = _UserLimitsStore({"u1": {"allowed_models": ["model-a"]}})
        router = _make_router(user_limits_store=limits)
        d = self._decision()
        # decision.model is "test-model", not in allowed list
        pf = router.preflight(d, user_id="u1")
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "model_not_allowed")

    def test_allowed_models_permits_listed(self):
        limits = _UserLimitsStore({"u1": {"allowed_models": ["test-model"]}})
        router = _make_router(user_limits_store=limits)
        pf = router.preflight(self._decision(), user_id="u1")
        self.assertTrue(pf.allowed)

    def test_daily_budget_blocks_when_exceeded(self):
        usage = _UsageLogStore()
        usage.logged.append({"user_id": "u1", "estimated_cost_chf": 4.95, "ts": int(time.time())})
        limits = _UserLimitsStore({"u1": {"chf_per_day": 5.0}})
        router = _make_router(usage_log_store=usage, user_limits_store=limits)
        pf = router.preflight(self._decision(cost_chf=0.10), user_id="u1")
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "daily_budget_exceeded")

    def test_daily_budget_allows_within_limit(self):
        usage = _UsageLogStore()
        limits = _UserLimitsStore({"u1": {"chf_per_day": 5.0}})
        router = _make_router(usage_log_store=usage, user_limits_store=limits)
        pf = router.preflight(self._decision(cost_chf=0.10), user_id="u1")
        self.assertTrue(pf.allowed)

    def test_insufficient_balance_blocks_credit_mode(self):
        credits = _CreditStore({"u1": 0.05})
        d = RoutingDecision(
            provider="openrouter", model="m", tier=Tier.SIMPLE,
            billing_mode="credit", api_key_source="system", api_key=None,
            estimated_cost_usd=0.10, estimated_cost_chf=0.10,
        )
        router = _make_router(credit_store=credits)
        pf = router.preflight(d, user_id="u1")
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "insufficient_balance")

    def test_sufficient_balance_allows_credit_mode(self):
        credits = _CreditStore({"u1": 1.00})
        d = RoutingDecision(
            provider="openrouter", model="m", tier=Tier.SIMPLE,
            billing_mode="credit", api_key_source="system", api_key=None,
            estimated_cost_usd=0.10, estimated_cost_chf=0.10,
        )
        router = _make_router(credit_store=credits, admin_settings_store=_AdminSettings({
            "expensive_threshold_chf": 0.50,  # above cost, so no confirmation needed
        }))
        pf = router.preflight(d, user_id="u1")
        self.assertTrue(pf.allowed)

    def test_expensive_model_triggers_confirmation(self):
        router = _make_router(admin_settings_store=_AdminSettings({"expensive_threshold_chf": 0.05}))
        pf = router.preflight(self._decision(cost_chf=0.20), user_id="u1", confirmed=False)
        self.assertFalse(pf.allowed)
        self.assertTrue(pf.requires_confirmation)
        self.assertIsNotNone(pf.billing_confirmation)
        self.assertIn("estimated_cost_chf", pf.billing_confirmation)
        self.assertIn("provider", pf.billing_confirmation)
        self.assertIn("model", pf.billing_confirmation)

    def test_confirmed_skips_expensive_check(self):
        router = _make_router(admin_settings_store=_AdminSettings({"expensive_threshold_chf": 0.05}))
        pf = router.preflight(self._decision(cost_chf=0.20), user_id="u1", confirmed=True)
        self.assertTrue(pf.allowed)

    def test_tokens_per_request_returned_as_clamp(self):
        limits = _UserLimitsStore({"u1": {"tokens_per_request": 256}})
        router = _make_router(user_limits_store=limits)
        pf = router.preflight(self._decision(), user_id="u1")
        self.assertTrue(pf.allowed)
        self.assertEqual(pf.clamped_max_tokens, 256)

    def test_global_daily_budget_blocks(self):
        usage = _UsageLogStore()
        usage.logged.append({"estimated_cost_chf": 9.95, "ts": int(time.time())})
        router = _make_router(
            usage_log_store=usage,
            admin_settings_store=_AdminSettings({"global_daily_budget_chf": 10.0}),
        )
        pf = router.preflight(self._decision(cost_chf=0.10), user_id="u1")
        self.assertFalse(pf.allowed)
        self.assertEqual(pf.reason, "global_daily_budget_exceeded")


# ------------------------------------------------------------------
# run_stream() / run_once() tests
# ------------------------------------------------------------------

class RunTests(unittest.TestCase):
    def _decision(self) -> RoutingDecision:
        return RoutingDecision(
            provider="stub", model="stub-model", tier=Tier.SIMPLE,
            billing_mode="system", api_key_source="system", api_key=None,
            estimated_cost_usd=0.0, estimated_cost_chf=0.0,
        )

    def test_run_stream_yields_tokens(self):
        router = _make_router()
        chunks = list(router.run_stream(self._decision(), messages=[], system_prompt="sp"))
        self.assertIn("hello", chunks)
        self.assertIn(" world", chunks)

    def test_run_once_returns_text(self):
        router = _make_router()
        text = router.run_once(self._decision(), messages=[], system_prompt="sp")
        self.assertEqual(text, "hello world")

    def test_run_stream_concatenated_equals_full_reply(self):
        router = _make_router()
        full = "".join(router.run_stream(self._decision(), messages=[], system_prompt="sp"))
        once = router.run_once(self._decision(), messages=[], system_prompt="sp")
        self.assertEqual(full, once)


# ------------------------------------------------------------------
# finalize() tests
# ------------------------------------------------------------------

class FinalizeTests(unittest.TestCase):
    def _decision(self, billing_mode="system", cost_chf=0.0) -> RoutingDecision:
        return RoutingDecision(
            provider="stub", model="stub-model", tier=Tier.SIMPLE,
            billing_mode=billing_mode, api_key_source="system", api_key=None,
            estimated_cost_usd=cost_chf, estimated_cost_chf=cost_chf,
        )

    def test_finalize_logs_usage(self):
        usage = _UsageLogStore()
        router = _make_router(usage_log_store=usage)
        router.finalize(self._decision(), user_id="u1", conversation_id="c1", input_tokens=10, output_tokens=5)
        self.assertEqual(len(usage.logged), 1)
        rec = usage.logged[0]
        self.assertEqual(rec["user_id"], "u1")
        self.assertEqual(rec["conversation_id"], "c1")
        self.assertEqual(rec["input_tokens"], 10)
        self.assertEqual(rec["output_tokens"], 5)
        self.assertEqual(rec["total_tokens"], 15)
        self.assertEqual(rec["request_status"], "ok")

    def test_finalize_logs_error_status(self):
        usage = _UsageLogStore()
        router = _make_router(usage_log_store=usage)
        router.finalize(self._decision(), user_id="u1", conversation_id="c1", input_tokens=0, output_tokens=0, status="error", error="provider_error")
        self.assertEqual(usage.logged[0]["request_status"], "error")
        self.assertEqual(usage.logged[0]["error"], "provider_error")

    def test_finalize_deducts_credit_when_billing_credit(self):
        usage = _UsageLogStore()
        credits = _CreditStore({"u1": 10.0})
        router = _make_router(
            usage_log_store=usage,
            credit_store=credits,
            admin_settings_store=_AdminSettings({
                "usd_to_chf_rate": 1.0,
                "model_prices": {"stub-model": {"in": 1.0, "out": 5.0}},
            }),
        )
        d = self._decision(billing_mode="credit")
        router.finalize(d, user_id="u1", conversation_id="c1", input_tokens=1000, output_tokens=200)
        # cost = (1000/1e6)*1.0 + (200/1e6)*5.0 = 0.001 + 0.001 = 0.002 CHF
        self.assertEqual(len(credits.deductions), 1)
        deducted_user, deducted_amount, _ = credits.deductions[0]
        self.assertEqual(deducted_user, "u1")
        self.assertAlmostEqual(deducted_amount, 0.002, places=5)

    def test_finalize_does_not_deduct_for_system_billing(self):
        credits = _CreditStore({"u1": 10.0})
        router = _make_router(credit_store=credits)
        router.finalize(self._decision(billing_mode="system"), user_id="u1", conversation_id="c1", input_tokens=100, output_tokens=50)
        self.assertEqual(len(credits.deductions), 0)

    def test_finalize_logs_even_with_no_usage_store(self):
        # Should not raise
        router = _make_router(usage_log_store=None)
        router.finalize(self._decision(), user_id="u1", conversation_id="c1", input_tokens=10, output_tokens=5)

    def test_finalize_deducts_zero_cost_skipped(self):
        credits = _CreditStore({"u1": 10.0})
        router = _make_router(credit_store=credits)
        d = self._decision(billing_mode="credit")
        # No price table → cost = 0 → no deduction
        router.finalize(d, user_id="u1", conversation_id="c1", input_tokens=100, output_tokens=50)
        self.assertEqual(len(credits.deductions), 0)


# ------------------------------------------------------------------
# SSE shape regression test (via api_auth_chat + JARVIS_USE_AI_ROUTER)
# ------------------------------------------------------------------

class SSEShapeWithRouterTest(unittest.TestCase):
    """Verify the SSE event shape is preserved when JARVIS_USE_AI_ROUTER=1."""

    def setUp(self):
        import json
        from types import SimpleNamespace
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from jarvis.api_auth_chat import build_auth_chat_router
        from jarvis.router_dependencies import build_auth_chat_deps
        from jarvis.runtime_state import ChatHistoryStore
        from jarvis.rate_limiter import RateLimiter

        os.environ["JARVIS_USE_AI_ROUTER"] = "1"
        os.environ["JARVIS_CHAT_HISTORY_PATH"] = tempfile.mkdtemp()
        # Clear env keys so AIRouter falls back to local (stub via provider_factory)
        for k in ["OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
            os.environ.pop(k, None)

        chat_history = ChatHistoryStore()

        class _StubByok:
            def has_key(self, u, p): return False
            def get_decrypted_key(self, u, p): return None
            def list_masked(self, u): return []
            def delete_key(self, u, p): return False

        class _NoopStore:
            def get(self, *a, **kw): return {}
            def update(self, *a, **kw): return {}

        class _NoopUsage:
            def log(self, r): pass
            def aggregate(self, **kw): return {"total_cost_chf": 0.0}

        class _NoopCredits:
            def get_balance(self, u): return 0.0
            def deduct(self, u, a, **kw): return True, 0.0

        class _NoopLimits:
            def get(self, u): return {}

        class _NoopHub:
            def begin(self, *a, **kw): return "tok"
            def end(self, tok): pass

        class _NoopHA:
            pass

        state = SimpleNamespace(
            ensure_default_admin_seeded=lambda: None,
            user_store=SimpleNamespace(
                list_users=lambda: [],
                find_by_username=lambda u: None,
                get_user=lambda u: None,
            ),
            admin_password_store=SimpleNamespace(verify_password=lambda u, p: False, set_password=lambda u, p: None),
            audit_log=SimpleNamespace(write=lambda e, d: None),
            _issue_token=lambda: SimpleNamespace(token="tok", expires_in_sec=60),
            _token_fingerprint=lambda t: "fp",
            _issue_identity_token=lambda u, r: {"session_token": "sess"},
            user_preferences_store=_NoopStore(),
            _identity_tokens={"test-session": {"user": {"id": "u1", "username": "testuser", "role": "admin"}}},
            require_identity_session=lambda s: {"user": {"id": "u1", "username": "testuser", "role": "admin"}},
            normalize_role=lambda r: r,
            _get_identity_session=lambda t: ({"user": {"id": "u1", "username": "testuser", "role": "admin"}} if t == "test-session" else None),
            _chat_owner_key=lambda s, g: (f"user:u1" if s == "test-session" else "guest:anon", "u1" if s == "test-session" else None),
            chat_history=chat_history,
            rag_store=SimpleNamespace(data={"updated_at": 0, "report": {}, "sources": {}}, refresh=lambda: {}, search=lambda q, limit=5: []),
            wakeword_enabled=lambda: False,
            strip_wakeword=lambda t: (t, True),
            _tokens={},
            is_token_active=lambda toks, t: False,
            resolve_effective_permissions=lambda *a, **kw: set(),
            membership_store=SimpleNamespace(),
            permission_store=SimpleNamespace(),
            home_assistant_service=None,
            status_hub=_NoopHub(),
            try_skill=lambda *a, **kw: None,
            rag_query_from_prompt=lambda t: None,
            select_rag_hits=lambda i, limit=3: [],
            rag_needs_smart_llm=lambda t: False,
            cloud_llm_available=lambda: False,
            format_rag_reply=lambda i, h: "reply",
            rag_llm_answer=lambda t, h: "reply",
            engine=SimpleNamespace(process=lambda *a, **kw: SimpleNamespace(summary="", data={"route": "cloud"})),
            build_context_reply=lambda t: "offline",
            get_provider=lambda: "local",
            local_ai_chat_reply=lambda msgs, sp: "local reply",
            local_ai_stub_reply=lambda t: "stub",
            byok_store=_StubByok(),
            usage_log_store=_NoopUsage(),
            credit_store=_NoopCredits(),
            user_limits_store=_NoopLimits(),
            admin_settings_store=_AdminSettings(),
            get_anthropic=lambda: None,
            get_gemini=lambda: None,
            get_openai=lambda: None,
            gemini_model=lambda: "gemini",
            openai_model=lambda: "gpt",
            openai_temperature=lambda: 0.2,
            openai_max_tokens=lambda: 128,
            SYSTEM_PROMPT="system",
            bearer_token_from_header=lambda a: None,
            os=os,
        )

        app = FastAPI()
        app.include_router(build_auth_chat_router(build_auth_chat_deps(state)))
        self.client = TestClient(app)
        self._json = json

    def tearDown(self):
        os.environ.pop("JARVIS_USE_AI_ROUTER", None)
        os.environ.pop("JARVIS_CHAT_HISTORY_PATH", None)

    def test_stream_done_event_has_required_keys(self):
        resp = self.client.post(
            "/chat/stream",
            json={"text": "hello"},
            headers={"X-Jarvis-Session": "test-session"},
        )
        self.assertEqual(resp.status_code, 200)
        lines = [l for l in resp.text.splitlines() if l.startswith("data: ")]
        self.assertGreater(len(lines), 0)
        last = self._json.loads(lines[-1][6:])
        self.assertEqual(last["type"], "done")
        self.assertIn("reply", last)
        self.assertIn("session_id", last)


if __name__ == "__main__":
    unittest.main()
