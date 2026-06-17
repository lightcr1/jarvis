---
name: project-wakeword-architecture
description: Wakeword engine integration: file locations, class names, callback wiring, admin endpoint, and settings schema
metadata:
  type: project
---

## Core files

- `jarvis/wakeword_engine.py` — three engine classes: `NullWakewordEngine`, `SoftwareWakewordEngine`, `OpenWakeWordEngine` + `create_wakeword_engine(settings)` factory + `_is_openwakeword_available() -> bool` helper
- `jarvis/audio_services.py` — `get_wakeword_status(settings_getter) -> dict` returns enabled/engine/phrase/openwakeword_available
- `jarvis/api_admin.py` — `GET /admin/wakeword/status` endpoint (requires admin auth via `require_admin_access`)
- `jarvis/runtime_helpers.py` — `settings_env_summary()` now includes `wakeword_engine` in the voice section; signature has optional `get_wakeword_engine` callable param
- `jarvisappv4.py` — `_get_wakeword_engine_name()` passes engine class name to `_settings_env_summary()`; engine created/started/stopped in `_lifespan`; `_apply_wakeword_settings()` hot-reloads sensitivity on PUT /admin/settings

## Engine lifecycle (jarvisappv4.py)

```python
wakeword_engine = create_wakeword_engine(admin_settings_store.get())
wakeword_engine.start(asyncio.get_event_loop(), _on_wakeword_detected)
# ... on shutdown:
wakeword_engine.stop()
```

## Admin settings schema (admin_settings_store.py voice section)

```json
{
  "wakeword_enabled": false,
  "wakeword_phrase": "hey jarvis",
  "wakeword_engine": "software",  // "software" | "openwakeword" | "none"
  "wakeword_sensitivity": 0.5,
  "stt_provider": "local"
}
```

## Env vars

- `JARVIS_WAKEWORD_ENGINE` — overrides settings: `openwakeword` | `software` | `none`
- `JARVIS_WAKEWORD_ENABLED` — `0/false/no/off` → NullWakewordEngine
- `JARVIS_WAKEWORD_PHRASE` — override phrase for software engine
- `JARVIS_WAKEWORD_SENSITIVITY` — override sensitivity for openwakeword engine
- `JARVIS_WAKEWORD_MODEL_PATH` — custom openwakeword model file path

## OpenWakeWord notes

- `openwakeword` is optional — never in hard requirements.txt (only as a comment)
- `_is_openwakeword_available()` safely returns bool without crashing
- If openwakeword not installed, `create_wakeword_engine` with `engine=openwakeword` falls back to `SoftwareWakewordEngine` with a warning log
- OWW mic loop runs in daemon thread, uses `asyncio.run_coroutine_threadsafe` for callback
- Requires `pyaudio` and `numpy` in addition to `openwakeword`

## Detection callback interface

```python
DetectionCallback = Callable[[], Awaitable[None]]

async def _on_wakeword_detected() -> None:
    logger.debug("Wakeword detected — always-on engine callback fired")
```

## Test patterns

- Use `build_admin_router(deps)` with isolated tempdir stores to test admin endpoints
- Set `JARVIS_ADMIN_SETTINGS_PATH` and `JARVIS_USER_STORE_PATH` in setUp to isolate stores
- For `_is_openwakeword_available` mock: `patch.dict(sys.modules, {"openwakeword": None})` + `reload(jarvis.wakeword_engine)`

**Why:** 
openwakeword is a P0 V1 blocker — the old string-stripping approach wasn't true keyword spotting.

**How to apply:** 
When extending wakeword functionality, always check if openwakeword is installed gracefully. All three engine classes share the same `start(loop, callback) / stop() / is_running()` interface.
