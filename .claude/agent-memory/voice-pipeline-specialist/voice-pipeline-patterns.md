---
name: voice-pipeline-patterns
description: TTS voice preference wiring, identity session field names, STT retry patterns, and test setup for voice API tests
metadata:
  type: project
---

## TTS Voice Preference Wiring

Preference stored as `tts_voice` in `user_preferences_store.py` (`DEFAULT_PREFERENCES["tts_voice"] = ""`).

Flow: SettingsScreen voice picker → immediate PUT `/auth/me/preferences` → `UserPreferencesStore.update()` → GET session reads `tts_voice` → POST `/tts` endpoint resolves voice from either:
1. `payload.voice` (body field, explicit override — e.g., for preview before save)
2. `user_preferences_store.get(user_id)["tts_voice"]` (stored preference)
3. `EDGE_TTS_VOICE` env var (server default, inside `_synthesize_edge`)

**Bug fixed (V35):** `api_voice.py` was reading `session.get("user_id", "")` but the identity session dict returned by `_get_identity_session` has structure `{"token": ..., "user": {"id": ..., ...}, "role": ...}`. Correct access is `session["user"]["id"]`.

## Identity Session Structure

`_identity_tokens` dict: `{token: {"user_id": ..., "role": ..., "exp": ...}}`

`_get_identity_session()` returns: `{"token": ..., "user": user_dict, "role": ...}`
— `user_dict` comes from `user_store.get_user(session["user_id"])` and includes `id`, `username`, `role`, `enabled`.

## TTSIn Model

`TTSIn` has `text: str` and `voice: str = ""`. Body voice overrides stored preference.

## STT Retry Pattern (frontend)

`transcribeAudio` in `chat.ts` retries up to 2 attempts with 1.5s backoff. Breaks immediately on 429 (rate limit) or 400 (bad request). On final failure, throws `SttError` with `kind` in `"network" | "timeout" | "rate_limit" | "server"`.

`OrbScreen.tsx` catches `SttError` and calls `showToast()` with a human-readable message before setting `orbState = 'error'`.

## Test Setup for Voice API Tests

To test session-based voice preference lookup, must:
1. Set `JARVIS_USER_STORE_PATH` and `JARVIS_USER_PREFERENCES_PATH` env vars to temp paths
2. Reinitialize `jarvisappv4.user_store = UserStore()` and `jarvisappv4.user_preferences_store = UserPreferencesStore()`
3. Create a real user via `app.user_store.create_user()`
4. Seed `_identity_tokens[token] = {"user_id": ..., "role": ..., "exp": time.time() + 3600}`

The `_get_identity_session` validates the user exists and is enabled in `user_store`, so test tokens must have a real seeded user.

Patch target for synthesize_tts: `jarvisappv4.synthesize_tts` — signature is `(text: str, voice: str | None = None)`. The api_voice.py calls it as `synthesize_tts(text, voice)` positionally.

**Why:** Discovered while fixing the voice preference wiring bug. The test pattern is non-obvious because the stores are initialized at module level in jarvisappv4 and must be reinitialized per test with temp paths.
