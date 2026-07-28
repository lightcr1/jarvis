---
name: proactive-intelligence-v2
description: Weekly digest, nightly summary, and proactive-suggestions loops built for V2 Roadmap Phase 1
metadata:
  type: project
---

Built 2026-07-27 alongside [[push-notifications-architecture]] and the AlertEngine pluggable
refactor noted in [[alert-engine-architecture]]. All three new scheduled loops live in
`jarvisappv4.py` and follow the exact `_morning_briefing_loop()` pattern: per-user opt-in
prefs in `user_preferences_store.py`, broadcast via `get_alert_broadcaster().broadcast()`,
started as `asyncio.create_task()` in `_lifespan()`, cancelled on shutdown.

**Weekly digest** (`_weekly_digest_loop`, type `weekly_digest`):
- Prefs: `weekly_digest_enabled` (bool), `weekly_digest_day` (lowercase weekday name,
  default "sunday"), `weekly_digest_time` ("HH:MM", default "18:00").
- `_next_weekly_seconds(day_name, hhmm, now)` — like `_next_briefing_seconds` but also
  matches a weekday.
- Content: current CPU/RAM/disk snapshot (reuses `jarvis.alert_engine._read_cpu_percent` /
  `_read_ram_percent` / `_read_disk_percent` directly — NOT a real historical trend, just a
  point-in-time reading at digest time; true trending would need a metrics history store,
  deliberately deferred), top 5 alerts from `alert_engine.get_history(limit=500)` in the last
  7 days (`_top_alert_events`, critical-first then most-recent), and auto-backup
  success/failure counts from `_auto_backup_log` in the last 7 days.
- `_build_weekly_digest_text(...)` is the pure formatter.

**Nightly summary** (`_nightly_summary_loop`, type `nightly_summary`):
- Prefs: `nightly_summary_enabled` (bool), `nightly_summary_time` ("HH:MM", default "21:00").
- Content: chat activity today (`_count_sessions_active_on` — counts *sessions* touched
  today via `chat_history.list_sessions(f"user:{uid}")`, not raw message count, to avoid
  overcounting long-lived sessions only briefly touched today), alerts fired today (filtered
  from `alert_engine.get_history()`), whether the morning briefing fired today
  (`_briefing_sent_dates: dict[user_id, ISO-date]`, a new in-memory-only dict updated inside
  `_morning_briefing_loop` right after a successful broadcast), and tomorrow's HA calendar
  items via the new shared `_calendar_lines_for_date(items, date_str)` helper (also used by
  `_morning_briefing_loop`, which previously had this logic inlined for "today" — refactored
  to share it).
- `_build_nightly_summary_text(...)` is the pure formatter.

**Proactive suggestions** (`_suggestions_loop`, type `suggestion`, polls every
`JARVIS_SUGGESTIONS_POLL_INTERVAL_SEC` seconds, min/default 6h):
- Core logic lives in `jarvis/proactive_suggestions.py` (pure, no jarvisappv4 imports),
  instantiated once as `suggestion_engine = SuggestionEngine()` in jarvisappv4.py.
- Three heuristics, each independently testable:
  1. `detect_repeated_skill_invocations(learned_replies, threshold=5)` — reads
     `engine.learning.data["learned_replies"]` (the SAME `LearningStore` already populated
     by every real `engine.process()` call in `jarvis_engine.py`; `confidence` on each entry
     IS the repeat-count via `record_success`, no new instrumentation needed).
  2. `IdleResourceTracker` (+ `flatten_proxmox_items(proxmox_health())`) — mirrors
     `AlertEngine`'s threshold-crossed-at pattern: tracks how long each Proxmox VM/container
     has sat at `cpu <= idle_cpu_threshold` (default 0.02) while `status == "running"`;
     fires once `idle_days_threshold` (default 3.0) is exceeded. State lives in the tracker
     instance, keyed by `f"{host_id}:{node}:{vmid}"`.
  3. `detect_backup_failure_streak(log, streak_threshold=3)` — reads the new
     `_auto_backup_log: list[dict]` (`{"ts", "ok"}`, capped at 500, most-recent-last) that
     `_auto_backup_loop` now appends to via `_record_auto_backup_outcome(ok)` after every run.
- `SuggestionEngine.evaluate(...)` composes all three and applies a per-suggestion-key
  cooldown (default 24h, same cooldown idea as `AlertEngine`) so the 6h poll doesn't re-fire
  the same suggestion every cycle. Returns ready-to-broadcast dicts with `type: "suggestion"`,
  `suggestion_id`, `kind`, `message`, `timestamp`.
- Proxmox snapshot is skipped gracefully if `proxmox_health()["configured"]` is False (no
  hosts configured) — same "don't crash if integration absent" pattern as HA entity rules.

**Frontend data plumbing (not a full UI yet):** `useJarvisAlerts()` in
`frontend/src/shared/api/alerts.ts` now also parses `weekly_digest`/`nightly_summary` (into
a `digests: DigestPush[]` array, `dismissDigest(ts)`) and `suggestion` (into `suggestions:
SuggestionEvent[]`, `dismissSuggestion(suggestion_id)`). **No visual card component was
built** — this mirrors the pre-existing `briefings`/`dismissBriefing` state, which was
already returned by the hook but never rendered anywhere in `JarvisApp.tsx` before this
session either. Building the actual dismissible-card UI is the natural next step for
whoever picks up Phase 1 frontend work.

**New user preference fields** (in `user_preferences_store.py`'s `DEFAULT_PREFERENCES` +
`update()`, and mirrored in `frontend/src/shared/api/client.ts`'s `UserPreferences` type):
`weekly_digest_enabled`, `weekly_digest_day`, `weekly_digest_time`,
`nightly_summary_enabled`, `nightly_summary_time`. All default to disabled — there is
currently NO settings UI to turn them on, so in production these loops will iterate over
zero enabled users until a frontend toggle is added (same "add to prefs first, wire settings
UI later" sequencing risk as the digest/summary loops shipping ahead of their UI).
