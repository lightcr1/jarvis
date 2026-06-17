# AI Provider System

JARVIS routes all LLM chat through a unified **AI Router** that selects the best available provider, enforces per-user spending limits, logs every request, and manages a CHF credit system. This document covers the full stack: provider abstraction, routing algorithm, BYOK encryption, usage logging, credits/ledger, limits, and the kill switch.

---

## Architecture Overview

```
/chat  /chat/stream
      │
      ▼
  AIRouter.resolve()          ← mode → tier → provider precedence
      │
      ▼
  AIRouter.preflight()        ← 10 sequential gates (kill switch … balance)
      │
  ┌───┴──────────────────────────────────────┐
  │ allowed                                  │ blocked / confirmation required
  ▼                                          ▼
  Provider.create_chat_completion()        HTTP "done" event with
  (stream or single-shot)                  billing_blocked / billing_confirmation
      │
      ▼
  AIRouter.finalize()
      ├── UsageLogStore.log()              ← always, even on error
      └── CreditStore.deduct()            ← only when billing_mode = "credit"
```

All existing deterministic skills, HA intents, and RAG paths are untouched — the router only executes when the engine returns `route=cloud`.

---

## Provider Abstraction

### Base interfaces (`jarvis/providers/base.py`)

| Type | Purpose |
|---|---|
| `AIProvider` Protocol | Duck-type interface for provider classes |
| `BaseProvider` ABC | Base class with default `estimate_cost()` |
| `ChatChunk` | Single streaming token chunk |
| `ChatResult` | Complete non-streaming response + token counts |
| `ModelInfo` | Model metadata: id, label, tier, in/out price per 1M tokens |

### Concrete providers

| Module | Provider | SDK |
|---|---|---|
| `anthropic_provider.py` | Anthropic | `anthropic` SDK; adaptive thinking on Opus, effort-medium on Sonnet |
| `openai_provider.py` | OpenAI | `openai` SDK |
| `gemini_provider.py` | Google Gemini | `google-genai` SDK |
| `local_provider.py` | Local (Ollama/llama.cpp) | HTTP to `LOCAL_LLM_BASE_URL` |
| `openrouter_provider.py` | OpenRouter | `openai` SDK with `base_url=https://openrouter.ai/api/v1` |
| `mistral_provider.py` | Mistral | OpenAI-compatible thin subclass |
| `deepseek_provider.py` | DeepSeek | OpenAI-compatible thin subclass |

OpenRouter, Mistral, and DeepSeek all subclass `OpenAICompatibleProvider` — a thin wrapper that sets `base_url` and forwards calls to the `openai` SDK.

### Model tiers (`jarvis/model_router.py`)

| Tier | Intent | Example models |
|---|---|---|
| `SIMPLE` | Short factual / voice queries | Haiku 4.5, GPT-4o-mini, Gemini Flash |
| `MEDIUM` | Standard conversation | Sonnet 4.6, GPT-4o, Gemini 2.0 |
| `COMPLEX` | Deep reasoning / code | Opus 4.8, GPT-4o (full), Gemini 2.5 Pro |

`classify_complexity(text, history_len, voice_mode)` returns the appropriate tier.

---

## Routing Algorithm (`jarvis/ai_router.py`)

### Mode → Tier mapping

| Mode | Tier selected |
|---|---|
| `auto-cheap` | SIMPLE (forced) |
| `auto-balanced` | `classify_complexity()` result |
| `auto-best` | COMPLEX (forced) |
| specific model id | Validated against `allowed_models`; tier from price table |

### Provider precedence

`_resolve_provider()` walks this ordered list and uses the **first match**:

1. **BYOK key** — user has stored an encrypted key for a provider (any provider in the supported list)
2. **OpenRouter default** — `OPENROUTER_API_KEY` is set **and** `openrouter_enabled=True` in admin settings
3. **Direct env keys** — `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `MISTRAL_API_KEY`, `DEEPSEEK_API_KEY`
4. **Local fallback** — `LOCAL_LLM_ENABLED=1` (Ollama / llama.cpp)

If nothing is available, `build_context_reply()` runs as an offline stub.

### Billing modes

| Mode | When | Credits charged |
|---|---|---|
| `system` | Provider key comes from server env | No |
| `byok` | Provider key comes from user's BYOK store | No |
| `credit` | Future: dedicated credit-billing plan | Yes — deducted from balance |
| `local` | Local provider in use | No |

---

## BYOK — Bring Your Own Key

### Storage

User API keys are stored in `ByokKeyStore` (`jarvis/byok_store.py`), a JSON file at `JARVIS_BYOK_STORE_PATH`. Keys are **never stored in plaintext** — see Encryption Scheme below.

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/auth/me/keys` | List masked keys for the current user |
| `PUT` | `/auth/me/keys/{provider}` | Store/replace a key (encrypted at rest, returns masked only) |
| `DELETE` | `/auth/me/keys/{provider}` | Remove a key |
| `GET` | `/admin/users/{id}/keys` | Admin: list which providers a user has keys for (masked, never decrypted) |

Supported provider names: `openrouter`, `openai`, `anthropic`, `gemini`, `mistral`, `deepseek`.

### Encryption Scheme

JARVIS uses **Fernet symmetric encryption** (`cryptography.fernet.Fernet`) exclusively for BYOK API keys.

#### Master key

```
JARVIS_SECRET_KEY=<32-byte urlsafe-base64 Fernet key>
```

Generate one:
```python
from cryptography.fernet import Fernet
print(Fernet.generate_key().decode())
```

This key is the single secret that protects all stored BYOK API keys. Store it securely; treat it with the same care as a database password.

#### Ciphertext format

Every encrypted secret is stored with a scheme prefix tag:
```
fernet:v1:<base64-fernet-token>
```

The `fernet:v1:` prefix allows future migration to other schemes without breaking existing records. Code in `secret_crypto.py` always checks for this prefix before decrypting.

#### What is encrypted

Only BYOK API keys are encrypted with Fernet. General application data (settings, user profiles, audit logs) is **not** encrypted.

#### Masking

`mask_secret(plaintext)` returns a display-safe string: first 3 chars + `...` + last 4 chars (`sk-...abcd`). Short strings return `"****"`. Masking is the **only** form of a key that ever leaves the backend.

#### Rotation

If `JARVIS_SECRET_KEY` is rotated:
- All previously stored keys become unreadable (Fernet `InvalidToken`)
- `decrypt_secret()` raises `SecretDecryptionError` — callers surface this as HTTP 422 "key invalid, please re-enter"
- The application **never crashes** on a bad key; it asks the user to re-enter

#### Backup exclusion

BYOK keys are **deliberately excluded from `GET /admin/backup`**. After a restore, users must re-enter their API keys. This is a security trade-off: a leaked backup file does not expose API keys.

---

## Usage Logging (`jarvis/usage_log_store.py`)

Append-only JSONL at `JARVIS_USAGE_LOG_PATH`. Every router request (success or error) writes one record:

| Field | Type | Description |
|---|---|---|
| `ts` | int | Unix timestamp |
| `user_id` | str | Requesting user (or `null` for guest) |
| `conversation_id` | str | Chat session id |
| `provider` | str | Provider used (openrouter, openai, …) |
| `model` | str | Model id |
| `billing_mode` | str | `system`, `byok`, `credit`, `local` |
| `input_tokens` | int | Estimated input tokens |
| `output_tokens` | int | Estimated output tokens |
| `total_tokens` | int | Sum |
| `estimated_cost_usd` | float | Pre-conversion cost |
| `estimated_cost_chf` | float | Cost in CHF (using `usd_to_chf_rate`) |
| `request_status` | str | `ok` or `error` |
| `error` | str \| null | Error description when status = error |

The usage log is **not included in backups** (high-volume append-only file).

### API

`GET /admin/usage?user_id=&provider=&days=7` returns:
```json
{
  "aggregate": { "request_count": N, "total_tokens": N, "total_cost_chf": N.N },
  "daily_buckets": [ { "date": "YYYY-MM-DD", "cost_chf": N.N, "requests": N } ],
  "recent": [ ... ]
}
```

---

## Credits & Ledger (`jarvis/credit_store.py`)

Per-user CHF balance with a complete ledger. Stored at `JARVIS_CREDIT_STORE_PATH`.

### Operations

| Method | Description |
|---|---|
| `get_balance(user_id)` | Current balance (0.0 if never topped up) |
| `top_up(user_id, amount_chf, *, note, actor)` | Add funds; creates `topup` ledger entry |
| `deduct(user_id, amount_chf, *, note)` | Deduct funds; returns `(ok, new_balance)`; refuses if insufficient |
| `list_ledger(user_id, limit)` | Recent ledger entries in reverse-chronological order |

`deduct()` uses a `threading.Lock` to prevent race conditions under concurrent requests.

### Ledger entry schema

```json
{
  "id": "cr-<hex>",
  "user_id": "usr-0001",
  "type": "topup | deduction",
  "amount_chf": 5.00,
  "balance_after": 15.00,
  "note": "initial load",
  "created_at": 1749600000
}
```

### Admin endpoints

| Method | Path | Description |
|---|---|
| `POST` | `/admin/credits/topup` | Add CHF to a user's balance |
| `GET` | `/admin/credits/{user_id}` | View balance + ledger |

Credits and user limits **are included in `GET /admin/backup`** and restored by `POST /admin/backup/restore`.

---

## Per-User Limits (`jarvis/user_limits_store.py`)

Stored at `JARVIS_USER_LIMITS_STORE_PATH`. Defaults are merged on read so the file stays sparse.

| Field | Default | Description |
|---|---|---|
| `chf_per_day` | `0.0` | Max spend per calendar day (0 = unlimited) |
| `chf_per_month` | `0.0` | Max spend per rolling 30 days (0 = unlimited) |
| `tokens_per_request` | `0` | Max tokens per single request (0 = unlimited) |
| `requests_per_min` | `30` | Rate limit per minute |
| `expensive_models_per_day` | `0` | Max expensive-model requests per day (0 = unlimited) |
| `allowed_models` | `[]` | Whitelist of model ids; empty = all allowed |

`PUT /admin/users/{id}/limits` updates limits for a user (admin only, audited).

---

## Preflight Gates (`AIRouter.preflight`)

Gates are evaluated in order. The **first failure** stops evaluation and returns the appropriate block reason.

| # | Gate | Block condition |
|---|---|---|
| 1 | Kill switch | `provider.kill_switch = True` |
| 2 | Expensive models disabled | `disable_expensive_models=True` and model is expensive |
| 3 | Rate limit | Requests per minute exceeded |
| 4 | Allowed models | Model not in user's `allowed_models` list |
| 5 | Tokens per request | Clamps `max_tokens` if over limit (non-blocking) |
| 6 | CHF per day | User's daily spend >= `chf_per_day` limit |
| 7 | CHF per month | User's monthly spend >= `chf_per_month` limit |
| 8 | Global daily budget | System-wide daily cost >= `global_daily_budget_chf` |
| 9 | Global monthly budget | System-wide monthly cost >= `global_monthly_budget_chf` |
| 10 | Expensive confirmation | `estimated_cost_chf > expensive_threshold_chf` and not confirmed |

When gate 10 triggers, the response carries `data.billing_confirmation` with provider, model, estimated cost, and balance. The user confirms by resending the request with the `X-Jarvis-Confirm: billing` HTTP header.

---

## Kill Switch

```
# admin settings
provider.kill_switch = true
```

When enabled, **all cloud LLM routes are blocked** instantly. Skill routes, HA intents, and RAG keyword-only replies continue to work. The kill switch is reflected in the preflight as gate 1 — no provider call is made.

Toggle via `PUT /admin/settings` with `{"provider": {"kill_switch": true}}`.

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `JARVIS_SECRET_KEY` | Yes (for BYOK) | Fernet master key for encrypting user API keys |
| `OPENROUTER_API_KEY` | — | Default cloud provider key |
| `OPENAI_API_KEY` | — | Direct OpenAI key (fallback) |
| `ANTHROPIC_API_KEY` | — | Direct Anthropic key (fallback) |
| `GEMINI_API_KEY` | — | Direct Gemini key (fallback) |
| `MISTRAL_API_KEY` | — | Direct Mistral key (fallback) |
| `DEEPSEEK_API_KEY` | — | Direct DeepSeek key (fallback) |
| `JARVIS_USE_AI_ROUTER` | — | Default `1`; set `0` to disable router (offline fallback only) |
| `JARVIS_BYOK_STORE_PATH` | — | Path for BYOK key store JSON (default: `/var/lib/jarvis/byok.json`) |
| `JARVIS_CREDIT_STORE_PATH` | — | Path for credit store JSON |
| `JARVIS_USER_LIMITS_STORE_PATH` | — | Path for user limits JSON |
| `JARVIS_USAGE_LOG_PATH` | — | Path for usage JSONL log |

---

## Security Notes

- API keys are **never** returned in any API response — only masked display strings (`sk-...abcd`)
- API keys are **never** logged — audit events record only provider name and user id
- Admins **cannot** retrieve raw user API keys — only masked presence
- `JARVIS_SECRET_KEY` is used **exclusively** for BYOK key encryption; no other data is encrypted with it
- BYOK keys are excluded from backups — a leaked backup does not expose provider credentials
- The usage log intentionally records `estimated_cost_usd/chf` rather than actual billed amounts — actual billing is between the user and the provider
