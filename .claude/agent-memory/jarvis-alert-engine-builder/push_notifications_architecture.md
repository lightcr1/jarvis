---
name: push-notifications-architecture
description: Real webpush notification pipeline — VAPID keys, subscription store, send helper, fanout wiring
metadata:
  type: project
---

Built 2026-07-27 as V2 Roadmap Phase 0 (`docs/v2/planning/ROADMAP_V2.md`), satisfying both
the Phase 0 gap and the Phase 7 "Full PWA + Mobile Push" item — built once, not duplicated.

**Files:**
- `jarvis/push_vapid.py` — `get_vapid_keys() -> {"public_key", "private_key", "subject"}`.
  Reads `JARVIS_VAPID_PUBLIC_KEY`/`JARVIS_VAPID_PRIVATE_KEY` env vars first; if either is
  missing, generates a keypair via `py_vapid.Vapid().generate_keys()` and persists it to
  `/var/lib/jarvis/vapid_keys.json` (env override `JARVIS_VAPID_KEYS_PATH`) so it survives
  restarts. Keys are raw urlsafe-base64 strings (no PEM), module-level cached — call
  `reset_cache_for_tests()` in tests. `JARVIS_VAPID_SUBJECT` (default
  `mailto:admin@localhost`) becomes the `sub` claim.
- `jarvis/push_store.py` — `PushSubscriptionStore`, JSON-backed at
  `/var/lib/jarvis/push_subscriptions.json` (env `JARVIS_PUSH_SUBSCRIPTIONS_PATH`), follows
  the `user_preferences_store.py` pattern exactly. Schema: `{"subscriptions": {user_id:
  [{"endpoint", "keys": {"p256dh", "auth"}, "created_at"}]}}`. `add()` dedupes by endpoint.
  `remove_by_endpoint(user_id, endpoint)` is the pruning hook called when a push send comes
  back 404/410.
- `jarvis/push_service.py` — `send_web_push(subscription, notification, vapid_keys) ->
  bool | None` wraps `pywebpush.webpush()` (added to `requirements.txt`); returns `None` on
  404/410 (caller should delete the subscription), `False` on other failures, `True` on
  success. `build_push_payload(event) -> {"title", "body", "tag", "ts"}` maps each broadcast
  `type` (alert/briefing/weekly_digest/nightly_summary/suggestion) to notification text.
  `fanout_push(payload, connected_user_ids, push_store, vapid_keys, send_fn=send_web_push)`
  is the orchestrator: broadcast-style payloads (no `user_id` key) go to every subscribed
  user not in `connected_user_ids`; user-scoped payloads (have `user_id`) go only to that
  user if they're not connected. Runs `send_fn` via `run_in_executor` since `pywebpush` is
  synchronous/requests-based.
- `jarvis/api_notifications.py` — `build_notifications_router(deps)`: `GET
  /notifications/vapid-public-key` (no auth — it's a public key), `POST
  /notifications/subscribe` (session auth, body `{endpoint, keys: {p256dh, auth}}`, audited
  as `notifications.subscribed`), `DELETE /notifications/subscribe?endpoint=...` (session
  auth, audited as `notifications.unsubscribed`). No new `KNOWN_PERMISSIONS` entry needed —
  same auth tier as `/memory/*` and `/auth/me/preferences` (identity session only, not a
  write-skill action, so `block_write_if_unauthorized`/emergency-stop doesn't apply, matching
  how preference writes are already handled).

**Wiring in `jarvisappv4.py`:** `push_subscription_store = PushSubscriptionStore()`
instantiated alongside other stores. `get_alert_broadcaster().configure_push_fanout(fn)` is
set once, right after `alert_engine` is constructed — `fn` closes over
`push_subscription_store` and calls `push_service.fanout_push(...)`. `build_notifications_deps()`
in `router_dependencies.py` supplies `vapid_keys` as a plain dict (evaluated once at
router-build time, since keys are cached after first call) rather than a `LiveRef`.

**Frontend:**
- `frontend/public_static/sw.js` — added `push` (calls `self.registration.showNotification`)
  and `notificationclick` (focuses/opens a window) listeners.
- `frontend/src/shared/api/push.ts` — `isPushSupported()`, `subscribeToPush()` (requests
  `Notification` permission, fetches the VAPID public key, calls
  `pushManager.subscribe()`, POSTs to `/notifications/subscribe`),
  `unsubscribeFromPush()`, `getPushSubscriptionStatus()`. Needed
  `urlBase64ToUint8Array(...) as BufferSource` cast for TS 5.7+'s generic `Uint8Array` typing
  vs. the DOM `PushSubscriptionOptionsInit.applicationServerKey` type.
- Wired into `frontend/src/screens/SettingsScreen.tsx`'s existing Notifications tab — new
  "Push Notifications" toggle row next to the pre-existing "In-app alerts" toggle, gated on
  `isPushSupported()`. Local component state only (`pushSupported`/`pushEnabled`/`pushBusy`/
  `pushError`), not persisted as a `UserPreferences` field — the subscription itself (stored
  server-side per user) is the source of truth.

**2026-08-07 update — quiet hours wired into `fanout_push` (V2 Phase 1 gap closure, see
[[phase1_frontend_gaps_closed]]):** `fanout_push(..., prefs_store: object | None = None)` new
optional param. `_is_quiet_hours_suppressed(payload, user_id, prefs_store)` in
`push_service.py` skips a user's push if `prefs_store.get(user_id)["quiet_hours_enabled"]`
is true and `is_within_quiet_hours(...)` (reused directly from `user_preferences_store.py`,
same helper `api_auth_chat.py::_context_mode_for_prefs` already used for in-chat DND) says
the current time falls inside their window — **unless** the event `type` is in
`_QUIET_HOURS_EXEMPT_TYPES = {"briefing", "weekly_digest", "nightly_summary"}**, since those
fire at a time the user explicitly chose themselves (suppressing them would defeat their own
schedule). Alerts, suggestions, and policy/playbook events all respect quiet hours. Wired in
`jarvisappv4.py`'s `_alert_push_fanout` via `prefs_store=user_preferences_store`. In-app
WebSocket delivery is untouched by this — only the push-to-closed-app path is suppressed.

**Deferred / open decisions:**
- No role-scoping on push targets: broadcast-style events (alerts, suggestions) still go to
  every subscribed user, not just admins — `PushSubscriptionStore` doesn't track role, and
  role-tagging push subscriptions would be a bigger schema change. The 2026-08-07 pass DID
  add role-scoped delivery for policy/playbook admin-ops events, but WS-only (see
  `broadcast_to_admins` in [[websocket_fanout]]) — deliberately no push fanout for those
  since there's no role info to filter subscriptions by.
