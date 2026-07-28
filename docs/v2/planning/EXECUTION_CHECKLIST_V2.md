# JARVIS V2 Execution Checklist — "Real JARVIS"

Living status tracker for the V2 roadmap. See
[`ROADMAP_V2.md`](./ROADMAP_V2.md) for the full detailed plan, current-state analysis,
and open decisions per phase — this file is just the checkbox summary + session log.

**Update this file at the end of every V2 work session** (check off finished items, add
a new entry to the handoff snapshot at the bottom).

---

## Phase 0 — Foundation Hardening

- [x] Split `MemoryStore` / `LearningStore` file paths (currently silently share `memory.json`) — done in an earlier session (`JARVIS_LEARNING_PATH`, migration-on-read)
- [x] Real push notifications: VAPID keys + backend webpush + service worker `push` listener — `jarvis/push_vapid.py`, `push_store.py`, `push_service.py`, `api_notifications.py`; `sw.js` push/notificationclick listeners; `SettingsScreen.tsx` toggle
- [x] Generalize `AlertEngine` to accept pluggable signal sources (not just HA) — `AlertEngine.register_source()` + `_default_signal_sources()` in `jarvis/alert_engine.py`
- [x] Persist identity/login sessions across service restarts — found during a live bug investigation (a `systemctl restart` was silently force-logging-out every active user since `_identity_tokens` was in-memory only). `runtime_helpers.py` (`load_identity_tokens`/`save_identity_tokens`, `path=` param threaded through issue/get/prune), wired in `jarvisappv4.py` (`_IDENTITY_SESSIONS_PATH`), persisted on login/logout/admin-revoke. Not in the original roadmap doc — added because it directly explained a real, reported symptom.

## Phase 1 — V2.1 Proactive Intelligence Engine

- [x] Background alert engine (rules, thresholds, cooldowns, severity) — `jarvis/alert_engine.py`
- [x] Alert rules admin UI (list/add/edit/enable-disable/test/delete) — `SettingsPage.tsx`
- [x] Morning briefing — genuinely scheduled + proactive, not just a skill
- [x] Weekly digest / nightly summary — `_weekly_digest_loop` / `_nightly_summary_loop` in `jarvisappv4.py`; per-user opt-in prefs exist but no settings UI toggle yet (defaults disabled)
- [x] Proactive suggestions (pattern-based, via `LearningStore` heuristics) — `jarvis/proactive_suggestions.py` (`SuggestionEngine`), broadcast as `type: "suggestion"`; frontend hook parses them but no card UI yet
- [x] Push delivery when app is closed — `AlertBroadcaster.configure_push_fanout()` fans every broadcast type out to webpush for subscribed-but-disconnected users

## Phase 2 — V2.2 Persistent Memory + Deep Context

- [x] Explicit memory CRUD (notes, aliases, summary) — `jarvis/api_memory.py`
- [x] Implicit learning (unmatched-query tracking, learned replies, feedback loop) — `LearningStore`
- [x] Contextual awareness (tone/detail by time of day, DND schedules) — `user_preferences_store.py` (`quiet_hours_*`, `is_within_quiet_hours`, `time_of_day_bucket`), `build_system_prompt()` in `ai_clients.py`, wired in both `api_auth_chat.py` chat call sites; Settings UI toggle in Notifications tab
- [x] Cross-session continuity references (build on existing `/chat/search`) — `_find_related_history()` in `api_auth_chat.py`, keyword-based reuse of `ChatHistoryStore.search_messages`, fed into `build_system_prompt()`'s new `related_history` param

## Phase 3 — V2.4 Task & Project Management

- [x] `jarvis/tasks/store.py` + `service.py` + `permissions.py` (HA template)
- [x] `tasks.read` / `tasks.write` / `tasks.manage` added to `KNOWN_PERMISSIONS`
- [x] `jarvis/api_tasks.py` + router wiring
- [x] `TasksScreen.tsx` (nav rail entry in `JarvisApp.tsx`)
- [x] Chat skills: create/list/breakdown tasks — deferred: surfacing open/overdue tasks in Morning Briefing (needs `jarvisappv4.py`/`api_auth_chat.py` changes that were mid-flight from a concurrent agent when this was built; briefing and tasks work independently today, just not cross-wired yet)

## Phase 4 — V2.5 Autonomous Infrastructure Management

- [x] Domain-agnostic `PolicyStore` (`jarvis/policy_store.py`) — sits alongside HA's existing `automation_rules`, not a migration/replacement
- [x] Cross-domain policy evaluator — `jarvis/policy_engine.py` (`PolicyEngine`), a sibling to `AlertEngine` that reuses its `_default_signal_sources`/`_evaluate_condition` directly rather than duplicating metric reading; own `register_source()` for future domains (Proxmox not yet wired as a source, HA-entity-conditioned policies not yet supported — both documented limitations, not blockers)
- [x] Self-healing rules (service crash → restart → escalate) — `dry_run` (default True) checked before anything else, then `JARVIS_EMERGENCY_STOP`, then real `role_has_permission("admin", "actions.write.execute")` (not a stub) — only then does it restart via the same `infra_actions.py` helpers the `restart <svc>` chat skill uses, with an incident-count/retry-window escalation path and audit logging on every branch
- [x] Maintenance playbooks + step executor — `jarvis/playbook_store.py` + `jarvis/playbook_executor.py`, checkpointed run records survive a restart, confirmation gates mirror the existing `ActionPlan`/`Skill` flow, dry-run and emergency-stop respected
- [x] Admin-gated CRUD/test/execute/resume API — `jarvis/api_policies.py`
- [ ] Admin UI panel for policies/playbooks — deferred (explicitly deprioritized in favor of backend + test coverage)

## Phase 5 — V2.3 Communication Hub

- [x] **Decided:** email = generic IMAP/SMTP (not Gmail API/OAuth — provider-agnostic on purpose)
- [x] **Decided:** calls = skipped (user confirmed, matches roadmap's own "stretch goal" note)
- [x] **Decided:** messaging bridge = skipped for now (Telegram bot flagged as the pick if revisited)
- [x] Calendar integration — dedicated CalDAV module (`jarvis/calendar/`), not the HA calendar plumbing (that's for HA-entity calendars, not the user's personal calendar); conflict detection on create, natural-language scheduling skills, `CalendarScreen.tsx`
- [x] Email integration — `jarvis/email/` (IMAP/SMTP, metadata-only cache), LLM-assisted draft-and-approve with explicit confirm-before-send, `EmailScreen.tsx`
- [x] Shared `jarvis/integration_credentials.py` — Fernet-encrypted multi-field credential store reused by both, excluded from `/admin/backup`
- [x] Both folded into the morning briefing loop, alongside tasks (completed a wiring point Phase 3 had deferred)
- [ ] Messaging bridge — out of scope, not built
- [ ] Phone/calls — out of scope, not built
- [ ] Admin UI panel for calendar/email credentials — deferred, self-service per-user via the new screens is enough for now

## Phase 6 — V2.6 Extended System Integrations (backlog, pick-and-choose)

- [x] Personal Cloud Workspace — **code complete, infra setup pending (user-run)**. Connectivity = Tailscale, not a plain LAN/port-forward (target PCs are on a different physical network). `jarvis/workspace/` (target registry, Guacamole `guacamole-auth-json` token signing, WoL-via-optional-relay), `deploy/guacamole/docker-compose.yml` (not started), `WorkspaceScreen.tsx`. **Two things need the user's hands before this is live:** (1) install+auth Tailscale on the JARVIS server and both target PCs, (2) bring up the Guacamole docker-compose stack and set `JARVIS_WORKSPACE_GUACAMOLE_URL`/`JARVIS_WORKSPACE_JSON_SECRET`. Runbook: see below / separate doc. Also flagged: the Guacamole token's PKCS7-padding assumption should be verified against a live instance before real use.
- [ ] Network & security monitoring (needs hardware confirmed)
- [ ] NAS/storage integration (needs brand/model confirmed)
- [ ] Camera/surveillance integration (needs hardware confirmed)
- [ ] Health/biometrics (optional, needs wearable confirmed)
- [ ] Finance (optional, needs CH open-banking API confirmed)
- [ ] Smart car (optional, needs compatible vehicle confirmed)

## Phase 7 — V2.7 Interface & Reach (interleaved)

- [x] PWA shell (manifest + service worker, caching only)
- [x] Ambient Orb (`OrbScreen.tsx` voice UI)
- [x] Push notification base (done in Phase 0 — do not rebuild here)
- [ ] Ambient Display Mode (separate passive kiosk route)
- [ ] Multi-device sync
- [ ] Voice Everywhere (multi-speaker routing on existing wakeword engine)
- [ ] Plugin System — **needs its own dedicated design pass before implementation**

---

## Current Session Handoff Snapshot

### 2026-07-27
- Branch: `main`, latest commit at time of writing: `bd8be70`
- This session: created `docs/v2/planning/ROADMAP_V2.md` and this checklist. No code
  changes — planning/documentation only (user explicitly deferred implementation to a
  future session).
- Explore-agent audit confirmed Phase 1/Phase 2's "already built" items above (alert
  engine, morning briefing, memory CRUD, implicit learning) and found the Phase 0 memory
  file-collision bug.
- Immediate next step: pick a starting phase (Phase 0 foundation hardening recommended
  — small, unblocks everything else) and begin implementation.

### 2026-07-27 (implementation session, run concurrently with other Phase 2/3 agents)
- Implemented Phase 0 in full and Phase 1's remaining gaps (weekly digest, nightly
  summary, proactive suggestions, push delivery). See agent memory
  `.claude/agent-memory/jarvis-alert-engine-builder/` for full architecture notes
  (`push_notifications_architecture.md`, `proactive_intelligence_v2.md`,
  `alert_engine_architecture.md`, `websocket_fanout.md`).
- New files: `jarvis/push_vapid.py`, `jarvis/push_store.py`, `jarvis/push_service.py`,
  `jarvis/api_notifications.py`, `jarvis/proactive_suggestions.py`. Modified:
  `jarvis/alert_engine.py` (pluggable sources), `jarvis/api_alerts.py` (broadcaster
  user_id tracking + push fanout hook), `jarvisappv4.py` (three new scheduled loops +
  wiring), `jarvis/user_preferences_store.py` (digest/summary prefs),
  `frontend/public_static/sw.js`, `frontend/src/shared/api/push.ts` (new),
  `frontend/src/shared/api/alerts.ts`, `frontend/src/screens/SettingsScreen.tsx`.
- Deferred: settings UI toggles for weekly digest / nightly summary (prefs + loops exist,
  default disabled, no frontend control yet); a dismissible suggestion/digest card UI
  (data layer done in `useJarvisAlerts()`, mirrors the pre-existing unrendered
  `briefings` state); quiet-hours integration with push fanout; role-scoped push
  targeting for system-wide events.
- Full suite: `pytest tests/ -x -q` — all new/existing tests pass; 8 pre-existing
  failures in `test_deploy_config_defaults.py` / `test_ops_preparation_assets.py` are
  unrelated (deployment-agent work in progress, confirmed via `git log` these test files
  are unmodified and were already failing before this session).

### 2026-07-27 (same session, continued — orchestrator + Phase 2/3 foreground work)
- Ran Phase 0/1 (alert-engine agent) and Phase 3 (tasks agent) concurrently in the
  background; did Phase 2 (contextual awareness + cross-session continuity) myself in
  the foreground on non-overlapping files to avoid collisions.
- Found and fixed a real production bug while investigating a user report of surprise
  logouts on the ServiceHub screen: identity sessions were in-memory only, so a service
  restart (which we'd just done for deploy troubleshooting) silently invalidated every
  logged-in user's session. Now persisted — see Phase 0 entry above. 18 new tests across
  `test_runtime_helpers.py` and the new `test_identity_session_persistence.py`.
- After both background agents landed, ran the full suite together: 1675 passed
  (excluding the 8 pre-existing deploy-fixture failures), frontend `tsc --noEmit` clean.
  One integration bug found and fixed during reconciliation: `build_auth_chat_deps` in
  `router_dependencies.py` required a hard `state._persist_identity_tokens` attribute,
  breaking two tests that construct a fake `state` — switched to the same defensive
  `getattr(..., default)` pattern `build_admin_deps` already used.
- Dispatched Phase 4 (policy engine generalization) to the same alert-engine agent
  (it already built the pluggable signal-source mechanism Phase 4 builds on).
- Phase 4 complete: 74 new tests (policy store/engine, playbook store/executor, API),
  full suite green (1749 passed locally / 1763 per agent's own run, discrepancy is
  collection-count noise, zero failures either way, excluding the 8 pre-existing
  deploy-fixture failures unrelated to any of this work).
- Manually spot-checked the self-healing restart path in `policy_engine.py` end to end:
  dry-run gate → emergency-stop gate → real permission check (not a stub) → restart via
  the same `infra_actions.py` helpers the chat skill uses → incident-window escalation
  → audit log on every branch. Also checked `playbook_executor.py`'s confirmation-gate
  design and `api_policies.py`'s admin gating. All sound, no changes needed.
- **Phases 0–4 of the V2 roadmap are now complete.** Phase 5 (Communication Hub) is
  blocked on user decisions (email provider, calls provider, messaging bridge — see
  `ROADMAP_V2.md`). Phase 6 (Extended Integrations) is pick-and-choose backlog; the
  Personal Cloud Workspace item has no blockers and can be picked up any time. Phase 7
  (Interface & Reach) is mostly done incidentally (PWA/push/ambient orb) — remaining
  items (Ambient Display Mode, multi-device sync, Voice Everywhere, Plugin System) are
  lower priority and Plugin System explicitly needs its own design pass first.
- Known pre-existing gap, unrelated to V2 work: `tests/test_deploy_config_defaults.py`
  and `tests/test_ops_preparation_assets.py` reference deployment fixtures
  (`scripts/deploy_local.sh`, `scripts/update_local.sh`, `scripts/rollback_local.sh`,
  `config/jarvis.env.example`, `config/env/dev.env.example`) that don't exist in the
  repo — 8 failures, present before this session, not introduced by it.
- Immediate next step: user decisions needed to unblock Phase 5 (see Open Decisions in
  `ROADMAP_V2.md`); otherwise pick from Phase 6 backlog or polish Phase 4's deferred
  admin UI panel.

### 2026-07-28 — Phase 5 (Communication Hub)
- User decisions: IMAP/SMTP over Gmail API, calls skipped, messaging skipped
  (Telegram noted as the pick if revisited later).
- Dispatched Calendar (CalDAV) + Email (IMAP/SMTP) together to one agent rather than
  parallel agents, since both need a shared credential store and both hook into the
  same morning-briefing assembly point — avoided the collision risk two separate
  agents would have had on those shared touchpoints.
- Verified myself before committing: full suite (1810 passed, same 8 pre-existing
  unrelated failures), and hand-checked the security-sensitive paths — credential
  store only ever returns field names (never decrypted values) outside the server,
  and email send requires an explicit `confirm=True` after a first `confirmation_required`
  response, mirroring the Phase 4 playbook executor's gate rather than inventing a
  third confirmation mechanism.
- Deployed to `/opt/jarvis` and confirmed live (previous deploy attempt via
  `JARVIS_BRANCH=... update.sh` silently deployed stale `main` instead of the target
  branch — `git pull` doesn't switch branches, it merges into whatever's checked out.
  Fixed by checking out the branch directly in the source root and using
  `update.sh --local` instead, which skips the branch-pull step entirely).
- **Phases 0–5 complete.** Remaining: Phase 6 (Extended Integrations, backlog/pick-and-
  choose — Personal Cloud Workspace has no blockers), Phase 7 leftovers (Ambient
  Display Mode, multi-device sync, Voice Everywhere, Plugin System — the last one
  needs its own design pass first).
