# Bereich: Billing / Credits

- Zweck: Abrechnung, Credits, Abos, Limits.
- Kern: `jarvis/billing/` (`stripe_client.py`, `permissions.py`),
  `jarvis/credit_store.py`, `jarvis/plan_store.py`, `jarvis/plan_service.py`,
  `jarvis/usage_log_store.py`, `jarvis/user_limits_store.py`.
- API: `jarvis/api_billing.py`; Admin-Deps in `jarvis/router_dependencies.py`.
- **Geschützt (🔒):** `jarvis/*billing*.py`, `jarvis/byok_store.py`,
  `jarvis/credit_store.py`-nahe Abrechnungslogik — nur Vorschlags-PR mit
  „owner review required“. Keine Zahlungen/Käufe (`forbidden_actions` in
  `config/agent-policy.json`).
- Tests: `tests/test_phase5_billing_endpoints.py`,
  `tests/test_e2e_ai_router_billing.py`, `tests/test_signup.py`.
