---
name: memory-architecture
description: Schema versioning, atomic writes, per-user data structure, and user_id key format for memory.json
metadata:
  type: project
---

The JARVIS memory subsystem stores data in `memory.json` at `JARVIS_MEMORY_PATH` (default `/var/lib/jarvis/memory.json`).

**Schema version:** `schema_version: 1` in the root. Users are keyed by their `user_id` string (format: `usr-<12 hex chars>`, same as user_store.py).

**JSON structure:**
```json
{
  "schema_version": 1,
  "users": {
    "<user_id>": {
      "notes": [{"id": "<hex uuid>", "text": "...", "created_at": 1234567890}],
      "aliases": {"<alias>": {"target": "...", "created_at": 1234567890}}
    }
  }
}
```

**Atomic writes:** Write to `<path>.tmp` first, then `os.replace()` — never corrupt the main file. The `.tmp` file is always cleaned up after the write. Test confirms it: `assert not os.path.exists(path + ".tmp")`.

**Thread safety:** Single `threading.Lock()` wrapping all read-write operations. No filelock dependency needed since the store is a module-level singleton.

**Note IDs:** `uuid.uuid4().hex` — 32-char hex string without dashes.

**Fallback path:** If `/var/lib/jarvis/` is not writable, falls back to `tempfile.gettempdir()/jarvis/memory.json`.

**Why:** Follows the exact same pattern as `user_store.py` but adds atomicity (user_store uses direct `write_text`, memory_store uses tmp+replace). Atomic writes are critical because notes/aliases are user-facing persistent data.

**How to apply:** When adding new JSON stores, use `MemoryStore` as the reference for atomic writes. `UserStore` is the reference for non-atomic (lower-risk) stores.
