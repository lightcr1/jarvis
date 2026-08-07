---
name: phase1-frontend-gaps-closed
description: 2026-08-07 session — closed the four remaining deferred gaps in JARVIS's proactive-intelligence system (digest/summary settings UI, card rendering, quiet-hours push suppression, role-scoped broadcast)
metadata:
  type: project
---

Backend for the proactive-intelligence system ([[proactive-intelligence-v2]],
[[push-notifications-architecture]], [[alert-engine-architecture]], [[autonomous-infra-v2-phase4]])
was fully built across earlier 2026-07-27 sessions, but four concrete pieces of
frontend/wiring work were left unfinished. This 2026-08-07 session closed all four. Backend
suite: 2230 passed / 0 failed after the change (`pytest tests/ -x -q`). Frontend: `tsc
--noEmit` clean, `npm run build` clean, `npx vitest run` 48/48 passed.

## Gap 1 — Settings UI for weekly digest / nightly summary

Added to the existing "Briefing" tab panel in `frontend/src/screens/SettingsScreen.tsx`
(`CATS` already had a `briefing` entry with a working `morning_briefing_enabled`/
`morning_briefing_time` pair — extended that same panel rather than adding a new tab).
New rows: Weekly Digest toggle + day `Sel` dropdown (7 weekdays) + time `Field`, Nightly
Summary toggle + time `Field`. No backend changes were needed — `user_preferences_store.py`,
the `/auth/me/preferences` round-trip, and the `_weekly_digest_loop`/`_nightly_summary_loop`
consumers in `jarvisappv4.py` already existed and already read these prefs correctly
(confirmed by reading, not assumed).

## Gap 2 — Render briefing/suggestion/digest cards

`frontend/src/screens/JarvisApp.tsx` previously only rendered the `alerts` array from
`useJarvisAlerts()` as dismissible toast cards; `briefings`/`suggestions`/`digests` were
fetched by the hook but never rendered. Added:
- `NoticeCard` component (icon, accent color, title, message, dismiss handler) — extracted
  from what was previously alert-only inline JSX, now shared by all four card types.
- Auto-dismiss timers: alerts 7s (unchanged), briefings/digests 15s (longer text), suggestions
  10s.
- Icons/colors: briefing = `IconSun`/`J.amber`, digest = `IconBook` (weekly) or `IconMoon`
  (nightly) /`J.amber`, suggestion = `IconZap`/`J.success`, alert = `IconBell`/severity color
  (unchanged).
- All four card arrays render in the same fixed-position bottom-right stack.

## Gap 3 — Quiet hours in push fanout

`jarvis/push_service.py::fanout_push` gained an optional `prefs_store` param. New
`_is_quiet_hours_suppressed(payload, user_id, prefs_store)` reuses
`user_preferences_store.is_within_quiet_hours` (the same helper `api_auth_chat.py` already
uses for in-chat DND) to skip a user's push if they're inside their quiet-hours window —
**except** for `_QUIET_HOURS_EXEMPT_TYPES = {"briefing", "weekly_digest", "nightly_summary"}`,
since those fire at a time the user explicitly configured themselves (suppressing a briefing
the user asked for at 07:00 because "quiet hours" happens to also be enabled would be
backwards). Alerts, suggestions, and policy/playbook events all respect quiet hours. In-app
WebSocket delivery is completely unaffected — only the push-to-closed-app path is suppressed.
Wired via `jarvisappv4.py`'s `_alert_push_fanout(...)` now passing
`prefs_store=user_preferences_store`.

## Gap 4 — Role-scoped push targeting / broadcast scoping

Found and fixed two distinct real bugs while auditing every `broadcast()` vs
`broadcast_to_user()` call site (not just the one named in the task):

1. **Personal content leaking to every connected client.** `_morning_briefing_loop`,
   `_weekly_digest_loop`, `_nightly_summary_loop` in `jarvisappv4.py` all built a payload
   with `"user_id": uid` but called the true `get_alert_broadcaster().broadcast(payload)` —
   which fans out to literally every open `/ws/alerts` socket. The only thing preventing user
   A's browser tab from displaying user B's calendar/email/chat-activity summary was
   client-side filtering (`isForCurrentUser()` in `alerts.ts`). Fixed by switching all three
   to a new `AlertBroadcaster.notify_user(user_id, payload)` method.

2. **Admin ops internals reaching every logged-in user.** `PolicyEngine` (self-healing
   restart/escalation events) and `PlaybookExecutor` (playbook run status/confirmation
   events) were wired with `broadcast_fn=get_alert_broadcaster().broadcast` in
   `jarvisappv4.py` — despite every REST endpoint that manages policies/playbooks
   (`/admin/policies/*`, `/admin/playbooks/*`) being `require_admin_access`-gated. A
   standard_user or guest with an open `/ws/alerts` tab would see `policy_escalation`,
   `playbook_result`, etc. Fixed by adding `AlertBroadcaster.broadcast_to_admins(payload)`
   (scopes WS delivery to sessions whose role is `"admin"`) and rewiring both engines'
   `broadcast_fn` to it.

`AlertBroadcaster` now has four delivery methods with distinct, documented contracts (full
detail in [[websocket_fanout]]): `broadcast` (true broadcast + push), `broadcast_to_user`
(WS-only, for silent sync signals like `briefing_seen`), `notify_user` (WS + push, for real
per-user content), `broadcast_to_admins` (WS-only, role-scoped, no push since push
subscriptions aren't role-tagged). `connect(ws, user_id=None, role=None)` now tracks role in
a parallel `_client_roles` dict; the `/ws/alerts` handler passes
`role=session["user"].get("role")`.

**Also fixed as a side effect:** `AlertEngine`'s owner-scoped custom alert rules
(`owner_user_id` set → routes through `broadcast_to_user_fn`) previously never triggered push
fanout at all when the owner wasn't connected, because `broadcast_to_user` never called the
push hook. Rewiring `broadcast_to_user_fn=get_alert_broadcaster().notify_user` in
`jarvisappv4.py` fixed this too — a user's own custom alert rule now push-notifies them when
offline, same as the built-in default rules already did via the true `broadcast()` path.

**Deliberately left as true `broadcast()`, with reasoning:**
- HA health batch (`type: "alerts"`, plural) — genuinely shared household state.
- Default/unowned alert rules (`owner_user_id is None`) — host-level CPU/RAM/disk health is
  relevant to every logged-in user of a self-hosted single-tenant assistant.
- `_suggestions_loop`'s `suggestion` events — don't carry a `user_id` (the underlying
  `learned_replies` data is engine-global, not per-user) and mix personal-pattern content
  (`repeated_skill`) with infra content (`idle_resource`, `backup_failures`), so neither
  `notify_user` nor `broadcast_to_admins` cleanly fits without deeper `SuggestionEngine`
  changes (per-kind permission filtering). Left as a known limitation, not silently dropped —
  flag this as the natural next scoping target if someone revisits push/broadcast targeting.

## Files touched this session

`frontend/src/screens/SettingsScreen.tsx`, `frontend/src/screens/JarvisApp.tsx`,
`jarvis/push_service.py`, `jarvis/api_alerts.py`, `jarvisappv4.py`,
`tests/test_alert_engine.py`, `tests/test_push_notifications.py`. Did NOT touch
`jarvis/ai_clients.py`/`ai_router.py`/`llm_utils.py`/`model_router.py`/
`providers/openai_compat.py` or their tests — explicitly out of scope (parallel
in-progress work). Changes were left uncommitted per instructions, for review before
committing together.
