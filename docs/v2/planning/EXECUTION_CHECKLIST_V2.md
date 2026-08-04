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
- [x] Admin UI panel for policies/playbooks — `PoliciesPage.tsx` (tabbed Policies/Playbooks, condition/action editors, repeatable step cards, execute/resume flow via `OverlayDialog`)

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
- [x] Admin UI panel for calendar/email credentials — `jarvis/api_admin_integrations.py` (`GET /admin/integrations/status`, non-decrypting `list_users_with_credential()` on `IntegrationCredentialStore`) + `IntegrationsPage.tsx`

## Phase 6 — V2.6 Extended System Integrations (backlog, pick-and-choose)

- [x] Personal Cloud Workspace — **code complete, infra setup pending (user-run)**. Connectivity = Tailscale, not a plain LAN/port-forward (target PCs are on a different physical network). `jarvis/workspace/` (target registry, Guacamole `guacamole-auth-json` token signing, WoL-via-optional-relay), `deploy/guacamole/docker-compose.yml` (not started), `WorkspaceScreen.tsx`. **Two things need the user's hands before this is live:** (1) install+auth Tailscale on the JARVIS server and both target PCs, (2) bring up the Guacamole docker-compose stack and set `JARVIS_WORKSPACE_GUACAMOLE_URL`/`JARVIS_WORKSPACE_JSON_SECRET`. Runbook: see below / separate doc. Also flagged: the Guacamole token's PKCS7-padding assumption should be verified against a live instance before real use.
- [ ] Network & security monitoring (needs hardware confirmed)
- [ ] NAS/storage integration (needs brand/model confirmed)
- [ ] Camera/surveillance integration (needs hardware confirmed)
- [ ] Health/biometrics (optional, needs wearable confirmed)
- [ ] Finance (optional, needs CH open-banking API confirmed)
- [ ] Smart car (optional, needs compatible vehicle confirmed)

## Off-roadmap — Personal Cloud Storage (added this session)

Not in the original phase plan — requested directly for a multi-tenant use case
(owner + club/association members + some outside users).

- [x] Per-user file drive (`jarvis/files/`) — folder/file CRUD, streaming upload/download
- [x] Path-traversal hardening (`jarvis/files/path_safety.py`) — independently re-verified
  before commit given the multi-tenant blast radius
- [x] Quota system — default 12GB/user, admin-overridable, extends `user_limits_store.py`;
  storage root path configurable (`JARVIS_USER_FILES_PATH`) so dev (~30GB disk) and
  production (500GB+ disk) run the same code
- [x] Per-folder JARVIS access grants (owner/admin toggle only) — primitive built and
  tested, wired into a chat skill this session (see below)
- [x] Chat/skill integration reading granted-folder contents — found and fixed a real bug
  while wiring this: `try_skill()` calls in `api_auth_chat.py` (both `/chat` and
  `/chat/stream`) never passed `user_id`, so any per-user skill silently saw `user_id=None`
  in production. Fixed, then added `_handle_file_drive_skill` in `assistant_domain.py`
  ("what's in my `<folder>` folder" / "read `<file>` in my `<folder>` folder"), gated on
  `FileService.jarvis_can_access_folder()`. v1 only resolves top-level folders; text/JSON
  files only, 20KB cap. Security invariant verified: a nonexistent folder and an
  existing-but-not-granted folder return the byte-identical denial reply (existence
  non-leak), and access is confirmed non-inherited by child folders.
- [ ] File sharing links — not built, not requested yet

## Off-roadmap — Billing, Self-Service Integrations, Deploy Automation (added 2026-07-31)

Not in the original phase plan — grew out of a prior session's uncommitted WIP
(subscription plans + Proxmox auth rework) plus a run of follow-up requests in
this session.

- [x] Subscription plans — `jarvis/plan_store.py` (catalog: price, AI credit,
  storage, `stripe_price_id`) + `jarvis/plan_service.py` (`assign_plan`,
  `ensure_monthly_grant`, called from both `ai_router.py` preflight and
  `api_auth_chat.py`). Admin CRUD + per-user assignment already existed
  uncommitted from a prior session; committed as-is after verifying it end to end.
- [x] Proxmox self-service — host auth moved from bearer token to
  session+permission (`proxmox.access`/`proxmox.manage`, same prior-session
  WIP), plus a frontend `HostManager` panel directly in `ProxmoxScreen.tsx`
  (backend host CRUD existed with zero UI before this).
- [x] Home Assistant self-service — was env-var-only; now configurable from
  the admin panel via the existing `IntegrationCredentialStore` (same pattern
  `workspace/service.py` already used for RDP/VNC creds), hot-applied via
  `HomeAssistantClient.apply_credentials()` with no restart needed.
- [x] WikiJS fully removed — RAG source, chat intents (`wiki page X`, and the
  legacy "tasks from wiki" natural-language route, superseded by the real
  Tasks feature), config templates, V1 docs/checklist.
- [x] Tasks: due dates + assignee (owner-gated reassignment) + group-based
  sharing — new `jarvis/tasks/share_store.py`, a direct copy of
  `jarvis/files/share_store.py`'s pattern (`tasks.share` permission mirrors
  `files.share`). `TaskService._accessible_task()`/`_visible_tasks()` resolve
  access as owner > assignee (write) > group-share (read/write).
- [x] Stripe payment integration — `jarvis/billing/stripe_client.py` (raw
  HTTP, no SDK — checkout sessions, webhook signature verification, per the
  existing `urllib` convention), `jarvis/api_billing.py`, new `billing.manage`
  permission so a non-admin (e.g. a "Finance" grant) can configure payments
  without full admin access. `POST /webhooks/stripe` handles
  `checkout.session.completed` (assign plan) and `customer.subscription.deleted`
  (unassign) — known gap, documented in the in-app setup guide: renewal
  payments aren't re-verified individually, only cancellation is webhook-driven.
- [x] `deploy_local.sh`/`update_local.sh`/`rollback_local.sh` — the README
  documented a full first-time-bootstrap TLS deploy flow (systemd install,
  self-signed cert, port 443, `/etc/jarvis/config.env`) that was never
  actually built; only the plain-HTTP `install.sh`/`update.sh`/`deploy.sh`
  flow (port 8000, `jarvis.env`) existed and is what the live instance runs.
  Built the missing flow as a genuinely separate, additive path — it refuses
  to silently repurpose a host already running the HTTP scheme without
  confirmation. Closed the 8 previously-failing tests in
  `test_deploy_config_defaults.py`/`test_ops_preparation_assets.py` that were
  checking for this. Not yet drilled against a real host.
- [x] Bug fixes found via live Playwright testing (not from a specific ask —
  found while verifying the above): `PermissionsPage.tsx` crashed on every
  "Save changes" because `GET /admin/permissions/effective/{id}` returns a
  nested context object but the page read it as a flat array; long-lived
  sessions never refreshed `UserCapabilities` after login, so permissions
  granted later (e.g. `billing.manage`) silently didn't unlock UI until
  logout/login — `JarvisApp.tsx` now refreshes capabilities from `/auth/me`
  once per mount.
- [x] Admin IA cleanup — split the "AI Provider" page (which had accumulated
  Plans + Stripe price IDs + storage overage pricing alongside unrelated
  routing/budget settings) into a dedicated "Billing" admin page.

**Known issue, not yet root-caused:** user-reported chat reliability problem —
certain words in a message reliably short-circuit into a canned/deterministic
reply instead of a real answer, and the cloud LLM fallback path doesn't seem
to have real access to local components (it can talk about them, not act on
them). Confirmed `jarvis_engine.py`'s `JarvisEngine.process()` (with its own
"Need clarification." fuzzy-match logic) is dead code — `engine.process()` is
never called from the live `/chat` path, only `engine.learning` is used
elsewhere — so that's not the source. Most likely candidates: `try_skill()`
keyword matching false-positiving on ordinary words before falling through to
RAG/LLM, and/or the LLM fallback path having no function-calling/tool-use
integration with the local skill/action system at all (it's pure text
generation once it's reached). Needs concrete repro messages from the user to
pin down further — see `assistant_domain.py::try_skill()` and
`ai_clients.py`'s system prompt construction as the starting points.

## Phase 7 — V2.7 Interface & Reach (interleaved)

- [x] PWA shell (manifest + service worker, caching only)
- [x] Ambient Orb (`OrbScreen.tsx` voice UI)
- [x] Push notification base (done in Phase 0 — do not rebuild here)
- [x] Ambient Display Mode — `AmbientDisplayScreen.tsx`, fullscreen kiosk route (clock,
  weather, next calendar event, HA/system status), reachable from the nav rail,
  logged-in-only, with a corner exit affordance since it renders before the nav chrome
  mounts. New `GET /weather` endpoint (`jarvis/api_weather.py`) added since weather was
  previously chat-pipeline-only with no HTTP route.
- [x] Multi-device sync — v1 slice, not a full framework: `AlertBroadcaster.broadcast_to_user()`
  (targeted send, `jarvis/api_alerts.py`) + `POST /sync/briefing-seen`
  (`jarvis/api_device_sync.py`) proves live cross-device sync end-to-end for one signal
  (morning-briefing-seen state). Deliberately not generalized into a device registry —
  extend the same pattern later if more signals are needed.
- [ ] Voice Everywhere (multi-speaker routing on existing wakeword engine) — **deferred**.
  Explored and confirmed this is a ground-up build (no device registry, wakeword engine
  hardcoded to a single mic, no speaker-routing concept anywhere in the codebase) that
  can't be meaningfully implemented or tested without a second physical JARVIS
  device/room, which doesn't exist yet. Same bucket as the Phase 6 hardware backlog.
- [ ] Plugin System — **needs its own dedicated design pass before implementation** (per
  the roadmap doc's own note — not started this session, on purpose)

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

### 2026-07-28 (continued) — V2 closeout: 5 remaining buildable features

- Goal for this session: finish everything left in the V2 roadmap that's genuinely
  buildable without external hardware/service specifics — closes out Phase 4's deferred
  admin panel, Phase 5's deferred admin panel, the Personal Cloud Storage chat-skill
  follow-up, and two of Phase 7's four leftovers.
- Deliberately excluded, discussed directly with the user: **Voice Everywhere** (explored
  first — confirmed it's a ground-up build with no device registry, no multi-speaker
  concept anywhere in the codebase, and no second physical JARVIS device to test against;
  same bucket as the Phase 6 hardware backlog) and **Plugin System** (the roadmap doc
  itself flags this as needing its own dedicated design pass — not started here).
- Two Explore passes + one Plan pass in plan mode before writing any code, to verify
  file/line references against the live source rather than working from assumption —
  full plan at the time is preserved in this session's plan-mode artifact.
- Built via 5 background agents across two waves (each in an isolated git worktree
  branched from `v2v2` to avoid concurrent-edit collisions), then merged and integrated
  by hand:
  - **Wave 1** (fully non-overlapping backend files): file-drive JARVIS-access chat
    skill (and the `user_id`-wiring bug fix that made it possible — see below), the
    multi-device sync v1 slice, and Feature 2's backend half (integrations status
    endpoint).
  - **Wave 2**: Policies/Playbooks admin UI, and Integrations admin UI + Ambient Display
    Mode bundled together.
  - Two of five worktree agents initially landed on a stale base commit instead of
    `v2v2`'s tip (a worktree-provisioning defect, not an agent judgment error) — each
    self-corrected via `git reset --hard v2v2` before starting, confirmed clean.
- **Found and fixed a real production bug** while wiring the file-drive skill: both live
  `try_skill()` call sites in `api_auth_chat.py` (`/chat` and `/chat/stream`) never
  passed `user_id`, even though it was already bound in scope at both sites — meaning
  every per-user skill (memory notes, and now file-drive) was silently seeing
  `user_id=None` in real chat traffic before this fix. Added an end-to-end HTTP-layer
  regression test specifically because the existing unit tests wouldn't have caught this
  class of bug (they call `try_skill()` directly, bypassing the router layer where the
  bug actually lived).
- Verified myself after merging all 5 branches: full suite `pytest tests/ -x -q` → 1964
  passed, same 9 pre-existing unrelated failures as before this session (8 missing
  deploy-fixture files, 1 time-of-day-dependent flaky calendar test — reproduced
  independently on the pre-session base commit to confirm neither is a regression).
  `tsc --noEmit` clean. Hand-verified the security-sensitive invariants beyond what the
  automated tests assert: file-drive skill's nonexistent-vs-ungranted-folder denial
  replies are byte-identical (existence non-leak) and grants are confirmed non-inherited
  by child folders; integrations endpoint's response never contains ciphertext/raw
  credential values; targeted broadcast only reaches the intended user's socket(s).
- Also folded in an earlier-session task: added the Personal Cloud Workspace, Personal
  Cloud Storage, `JARVIS_LEARNING_PATH`, and identity-session env vars to
  `config/prod.env.example` (was missing them entirely).
- Branch: work done on new branch `v2v2` (per user's naming preference — this is the
  second round of V2 session work, distinct from the earlier `v2-phase-0-4` branch),
  merged into `main` and pushed to GitHub at the end of this session so the user's
  production box can pull it via the normal `update.sh` flow (`main` is its default
  branch).
- **V2 is now feature-complete** except the two explicitly-deferred Phase 7 items above
  and the hardware-gated Phase 6 backlog (network/security monitoring, NAS, camera,
  health, finance, smart car — all blocked on the user providing device/service specifics).

### 2026-07-31
- See the new "Off-roadmap — Billing, Self-Service Integrations, Deploy Automation"
  section above for the full list; summary here is just the session shape.
- Committed a prior session's uncommitted WIP (subscription plans, Proxmox
  session+permission auth) after independently verifying it end to end — nothing was
  broken, it just hadn't been committed yet.
- Built on top of that: Stripe payment integration (real checkout + webhook flow, not
  just credential storage), the `deploy_local.sh` TLS deploy flow the README had
  described but never had code for, and a Proxmox/HA self-service admin UI.
- Found and fixed two real pre-existing bugs via live Playwright verification (not
  reported by the user first) while checking the above: `PermissionsPage.tsx` crashed
  on every permission save (nested API response read as a flat array), and long-lived
  sessions never refreshed capabilities after login (permissions granted post-login
  silently didn't unlock UI until logout/login).
- Split the "Billing" concerns (Plans, Stripe price IDs, storage overage pricing) out
  of the "AI Provider" admin page into their own page after the user pointed out
  Billing settings were hard to find and asked whether the admin panel needed
  reorganizing.
- **Known open issue, not yet root-caused:** user reports chat reliability problems —
  certain words reliably trigger a canned/deterministic reply instead of a real answer,
  and the cloud LLM fallback doesn't seem to have real access to local components
  (can discuss them, can't act on them). Ruled out `jarvis_engine.py`'s `JarvisEngine`
  fuzzy-matcher (dead code, never called from the live `/chat` path) as the source.
  Needs concrete repro messages from the user before further investigation —
  `assistant_domain.py::try_skill()` keyword false-positives and/or a missing
  function-calling/tool-use bridge between the LLM and the local skill/action system
  are the leading suspects.
- Branch: work done on `workspace-hub` (pre-existing branch name, not chosen this
  session). To be merged into `main` and pushed at the end of this session, same
  pattern as the `v2v2` session before it, so the production box can pull it via the
  normal update flow.
- Immediate next step: get concrete repro messages for the chat reliability issue, then
  scope File sharing links and the Plugin System (the latter needs its own design pass
  per the roadmap's existing note — user asked specifically what it would even be for).

### 2026-08-03 — Verified and closed out prior session's uncommitted WIP
- Found a prior session had already left substantial uncommitted work in the tree
  addressing the 2026-07-31 "known open issue" above: `tool_registry.py` /
  `tool_registry_tools.py` / `tool_orchestrator.py` (a real LLM tool-calling bridge —
  OpenAI + Anthropic function/tool-use, permission + emergency-stop gated, audited,
  falling back to plain `run_once()` for non-tool-capable providers or callers with no
  available tools) plus a pilot registry of four read-only tools (`list_folder`,
  `read_file`, `save_memory_note`, `proxmox_status`). Also uncommitted: File sharing
  links (`link_share_store.py`, PBKDF2-hashed optional password, expiry, public
  token-based download at `/s/:token`) and a new Workspace `OverviewScreen` +
  `CalendarGrid` extraction from `CalendarScreen`.
- This session's job was verification and finishing, not building from scratch: read
  every new/changed file end to end, confirmed wiring (both `/chat` and `/chat/stream`
  call the tool orchestrator; `files.share` permission was already registered via
  `FILES_PERMISSIONS`; frontend routes/icons all resolve), and ran the full suite.
- Found and fixed one real gap: the public share-link download endpoint
  (`POST /public/files/shared/{token}/download`) had no rate limiting, so a
  password-protected link's password was brute-forceable over the network with no
  throttle beyond PBKDF2's own cost. Added the same `_rate.allow(...)` pattern used for
  login attempts (10 attempts / 5 min, keyed by token) — `jarvis/api_files.py`.
- Found and fixed one pre-existing flaky test (not part of the uncommitted WIP):
  `test_block_hours_reports_conflict_without_double_booking` built its conflicting
  fake event as `[now, now+999999s]`, but the skill under test defaults to a fixed
  09:00–10:00 local block for "today" with no daypart — so the test only caught the
  conflict when run before ~10am local time. Fixed to span the full local day instead
  of a `now`-relative window, matching how `_handle_calendar_block` actually resolves
  "today". This was the one recurring failure noted in every prior session's suite run.
- Full suite after fixes: **2152 passed, 0 failed** (backend, `pytest tests/ -q`);
  frontend `tsc --noEmit` clean; Vitest 38/38 passed including the new
  `CalendarGrid.test.ts` and `files.test.ts`.
- Not yet committed — left for the user to review/commit.

### 2026-08-03 (continued) — "Real JARVIS" plan: brand mark, memory, tool write-actions, wakeword signal
- User asked for a from-scratch look at what it'd take to make JARVIS feel like the
  actual Iron-Man JARVIS (not just the tracked V1/V2 checklist), then approved a
  4-phase plan built from direct code verification. All 4 landed this session.
- **Phase 1 — brand mark.** The user pointed at two previously-published design
  artifacts ("J.A.R.V.I.S. — Mark Concepts", "Workspace — Round 2") as the decided
  identity — a Hex Core monogram SVG, not something to invent fresh. Replaced the
  flat-orange placeholder PWA icons and the dead `/favicon.svg` manifest reference
  with the real mark (rendered via `cairosvg`, pixel-exact from the same SVG paths),
  and swapped the plain text "J" badges in `JarvisApp.tsx`/`WorkspaceShell.tsx`/
  `AdminShell.tsx` for the same glyph (`IconJarvisMark` in `jarvis-shared.tsx`).
- **Phase 2 — memory woven into every turn.** `build_system_prompt()` already accepted
  a `notes` param that no caller ever passed — wired `MemoryStore` notes into both
  `/chat` and `/chat/stream` system prompts. Also found `llm_utils.trim_to_budget` was
  defined but never called anywhere — wired it onto the message history sent to the
  LLM (the real unbounded-growth risk, not the already-capped notes list).
- **Phase 3 — tool-calling confirmation gate + first write-capable tools.** Added a
  `confirm` kwarg to `execute_tool()` so WRITE/CRITICAL-risk tools return a
  confirmation-required reply instead of executing immediately; wired the
  already-scaffolded-but-unused `pending_tool_call` columns in `ChatHistoryStore` to
  persist it turn-to-turn. Added `restart_service`, `list_devices`, `control_device`
  to the tool registry (previously 4 read-only pilot tools only).
  - **Found and fixed a real bug while testing this, not reported by the user:** the
    legacy `JarvisEngine` fuzzy-matcher (`jarvis_engine.py`, `engine.process()`) is
    *not* dead code as a prior session's notes assumed — it's still wired into both
    `/chat` and `/chat/stream` as a routing layer, and its fuzzy skill-matching has no
    minimum-score floor, so short/generic replies like bare "yes" get swallowed as an
    unrelated hardcoded skill match (`missing_token` error) instead of ever reaching
    the LLM. This directly breaks a plain "yes" reply to *any* confirmation prompt —
    including the one this phase's own confirmation gate generates — and is very
    likely a major contributor to the still-open 2026-07-31 "certain words reliably
    trigger a canned reply" issue. Root-caused via a manual repro
    (`engine.process("yes", ...)` → non-"cloud" route with no LLM call), not yet
    fixed at the source (that's a separate, larger investigation into
    `registry.match()`'s scoring). Worked around it narrowly for this phase by moving
    the pending-tool-call check to resolve *before* skill/RAG/engine routing runs at
    all, mirroring how `pending_home_assistant_action` was already structured — so
    tool confirmations now bypass the legacy engine entirely, but the engine itself is
    still live and still capable of intercepting other unrelated short phrases.
    **Flagging for the user:** the concrete next step on the long-standing chat
    reliability complaint is almost certainly `jarvis_engine.py::JarvisRegistry.match()`
    needing a minimum-confidence floor before accepting a match, not a "missing
    function-calling bridge" (that bridge — this session's tool-calling work — is now
    built and working; the legacy engine sits in front of it and can still shadow it).
- **Phase 4 — wakeword detection signal, end to end.** Discovered mid-plan (via direct
  code reads, correcting a stale research pass) that the wakeword engine is much
  further along than CLAUDE.md's P0 list said: `OpenWakeWordEngine` is real, started
  at boot, and admin-configurable — only `_on_wakeword_detected()` was a no-op with
  nothing downstream. Added `JarvisStatusHub.notify()` (a one-shot edge-event slot,
  additive to the existing sustained recording/processing/speaking state model),
  wired the callback to call it, threaded the new `last_event` field through
  `/ws/status` → `status.ts` → `OrbScreen.tsx`, which now auto-starts recording on a
  wakeword event when idle (extracted the decision logic into a pure
  `shouldAutoStartOnWakeword()` for unit testing, matching this repo's existing
  pattern of testing extracted pure functions over full component rendering).
  Documented the optional `openwakeword`/`pyaudio` deps in `requirements.txt` and
  updated CLAUDE.md's stale P0 entry — remaining gap is hardware-only (mic + tuning
  on the real target machine, can't be done by an agent).
- Full suite after all 4 phases: **2177 passed, 0 failed** (backend); frontend
  `tsc --noEmit` clean, Vitest 44/44 passed, `npm run build` succeeds and the new
  static assets (`favicon.svg`, regenerated icons) resolve correctly in `dist/`.
- Not yet committed — left for the user to review/commit.
