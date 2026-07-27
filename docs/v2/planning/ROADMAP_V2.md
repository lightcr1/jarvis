# JARVIS V2 Roadmap — "Real JARVIS" (Execution Plan)

> V1 ships a reliable assistant. V2 makes it feel like Tony Stark's JARVIS.
> Not just a system that responds — a system that observes, plans, acts, and communicates
> across every dimension of your life. Infrastructure, home, calendar, communication,
> research, finance, health. One brain. Everything connected.

This is the execution-ready version of the vision originally sketched in
`docs/v1/planning/ROADMAP_V1.md`. Every phase below states what's **already built**
(verified against the actual code, not assumed), what's **still missing**, the
**concrete files** to create, and any **open decisions** only the user can make.

Live progress is tracked separately in
[`EXECUTION_CHECKLIST_V2.md`](./EXECUTION_CHECKLIST_V2.md) — update that file, not this one,
as work lands.

---

## V2 Vision

```
[Morning — 07:30]
JARVIS: "Good morning. It is 07:30. Weather is 18°C, partly cloudy.
         You have three meetings today — first one at 10:00 with the team.
         pve-01 triggered a high-memory alert at 03:14, I've already cleared
         the idle containers. One email from your bank flagged as important.
         All systems nominal. Standing by."

[Afternoon]
User: "JARVIS, block two hours Thursday for the API design work and
       push back Friday's standup by 30 minutes."
JARVIS: "Done. Thursday 14:00–16:00 blocked. Friday standup moved to 10:30,
         attendees notified."

[Evening]
JARVIS: "Sir, the front door has been unlocked for 40 minutes.
         Shall I lock it?"
User: "Yes."
JARVIS: "Locked."
```

## V2 Principles

- **Proactive over reactive** — JARVIS speaks when something matters, not only when asked
- **Policy over prompts** — configure once, JARVIS executes continuously and autonomously
- **Audit everything** — every autonomous action logged: what, why, outcome, rollback
- **User stays sovereign** — all automation is opt-in; any action can be reversed or blocked
- **Privacy first** — local processing where possible; nothing leaves the network without explicit config
- **One interface** — not a collection of apps, one coherent system across all domains
- **Graceful degradation** — if one integration fails, everything else keeps working

---

## Architecture template for every new integration

Every new backend integration in the phases below follows the pattern already proven by
`jarvis/home_assistant/`:

| Layer | File | Responsibility |
|---|---|---|
| I/O | `client.py` | Pure HTTP/network calls, swallows errors, zero business logic |
| Persistence | `store.py` | JSON CRUD, self-healing `_load()`, no auth/permission knowledge |
| Policy | `permissions.py` + `risk.py` | Flat permission tuple + static risk/confirmation config |
| Logic | `service.py` | The only layer combining auth, `require_access()`, emergency-stop check, risk gating, audit — every public method takes `user_id`/`role` |
| API | `jarvis/api_<name>.py` | Thin router, `PermissionError → HTTPException(403)` |
| Wiring | `build_<name>_deps()` in `router_dependencies.py` + instantiate + `include_router` in `jarvisappv4.py` | Dependency injection, no globals |
| Permissions | `KNOWN_PERMISSIONS.update(...)` in `permission_store.py` | One-liner per integration |

Secrets (API keys, IMAP/CalDAV credentials) must **not** go into the plaintext
`admin_settings_store.py`. Reuse the Fernet encryption primitives in
`jarvis/secret_crypto.py` (already powering `jarvis/byok_store.py`) for a new
`IntegrationCredentialStore`, and exclude it from `/admin/backup` exports the same way
BYOK keys already are (`api_admin.py:482`).

---

## Phase 0 — Foundation Hardening

Small, high-leverage fixes that unblock every later phase. No new user-facing features.

**Current state:**
- `MemoryStore` (`jarvis/memory_store.py:15`) and `LearningStore`
  (`jarvis/jarvis_engine.py:58`) both default to `/var/lib/jarvis/memory.json` and
  silently overwrite each other's data — **bug, not a design choice**.
- No generic background scheduler exists — `_auto_backup_loop`, `_morning_briefing_loop`,
  and `AlertEngine._loop` are three separate hand-rolled `asyncio.create_task` loops in
  `jarvisappv4.py`. Every new periodic job today means writing another one from scratch.
- PWA shell exists (`frontend/manifest.json`, `frontend/public_static/sw.js`) but the
  service worker only does fetch caching — no `push` event listener, no
  `Notification`/`PushManager` usage in the frontend, no VAPID/webpush code in the
  backend. Real push notifications (phone gets a notification while the app is closed)
  **do not exist**.
- `AlertEngine` is hardcoded to read from `home_assistant_store` as its only signal
  source (`jarvis/alert_engine.py`).

**Build blocks:**
1. Split memory storage: give `LearningStore` its own path (e.g.
   `JARVIS_LEARNING_PATH`, default `/var/lib/jarvis/learning.json`), migrate any
   existing combined file on first read.
2. Real push notifications — VAPID keypair generation + storage, backend webpush send
   helper, `push` + `notificationclick` listeners added to `frontend/public_static/sw.js`,
   subscription endpoint (`POST /notifications/subscribe`) storing per-user push
   subscriptions. This single build satisfies both the V2.1 "delivery" gap below and the
   V2.7 "Full PWA + Mobile Push" item — **build once, don't duplicate in Phase 7**.
3. Refactor `AlertEngine` to accept a list of pluggable signal-source callables instead
   of a hardcoded `home_assistant_store` reference — cheap now, required for Phase 4's
   policy-engine generalization.

**Open decisions:** none — this phase is pure engineering, no external accounts needed.

---

## Phase 1 — V2.1 Proactive Intelligence Engine

**Current state — mostly already built:**
- `jarvis/alert_engine.py` — real rule engine: CPU/RAM/disk thresholds (via `psutil`/
  `/proc`), HA reachability, HA entity state/attributes, `above`/`below`/`equals`/
  `contains` conditions, sustained-duration thresholds, cooldowns, severity, templated
  messages. Runs as an `asyncio` poll loop (default 30s, `JARVIS_ALERT_POLL_INTERVAL`).
- `jarvis/alert_store.py` — `AlertRulesStore`, JSON-persisted, 5 seeded default rules,
  full CRUD.
- `jarvis/api_alerts.py` — full admin REST (`/admin/alerts/rules` CRUD, `/test`,
  `/history`) + `/ws/alerts` WebSocket + `AlertBroadcaster` fan-out.
- Admin UI: `frontend/src/routes/admin/pages/SettingsPage.tsx` has a complete alert-rule
  panel (list/add/edit/enable-disable/test/delete).
- **Morning Briefing is genuinely proactive**, not just a skill: per-user
  `morning_briefing_enabled`/`morning_briefing_time` in `user_preferences_store.py`,
  actually scheduled via `_morning_briefing_loop()` in `jarvisappv4.py`, wakes at the
  configured time, invokes the `briefing` skill, appends HA calendar items, broadcasts a
  `type: "briefing"` message. Also reachable on-demand via `/chat/daily-briefing`.

**Still missing:**
- Weekly digest / nightly summary (roadmap items, not yet built).
- Proactive suggestions (pattern-based recommendations — "you restart nginx every
  Monday", "VM idle 8 days", "3 backups failed silently").
- Real delivery when the app is closed — **solved by Phase 0's push notification build**.

**Build blocks:**
1. Weekly digest + nightly summary: two more scheduled loops following the exact
   `_morning_briefing_loop` pattern (same file, same broadcast mechanism).
2. Proactive suggestions: extend `LearningStore`'s existing pattern-detection
   (`record_query`, `record_success`) with a few concrete heuristics (repeated manual
   skill invocation, VM/container idle duration via existing Proxmox module, backup
   failure streaks via existing `_auto_backup_loop` outcomes) and surface them as
   dismissible cards through the alert broadcaster — no new delivery mechanism needed.

**Open decisions:** none.

---

## Phase 2 — V2.2 Persistent Memory + Deep Context

**Current state — mostly already built:**
- `jarvis/api_memory.py` + `jarvis/memory_store.py` (`MemoryStore`) — full per-user CRUD
  for notes and aliases, `/memory/notes`, `/memory/aliases`, `/memory/summary`,
  `/memory/all` clear. Frontend: `MemoryPanel` in `SettingsScreen.tsx`.
- `jarvis_engine.py`'s `LearningStore` — genuine implicit learning: unmatched-query
  tracking with skill suggestions, confidence-scored learned replies, a thumbs-down
  feedback correction loop, remembered node/vmid defaults, exposed via the `memory show`
  chat command.

**Still missing:**
- Contextual awareness — tone/detail level adapting to time of day, "Do Not Disturb"
  schedules.
- Cross-session continuity references ("last Tuesday you asked about X — here's an
  update").

**Build blocks:**
1. Contextual awareness: hook into the existing Persona Tone settings (already shipped
   in V40) and `user_preferences_store.py` — add a time-of-day/DND lookup that adjusts
   the system prompt tone/verbosity injected in `ai_clients.py`'s JARVIS system prompt
   construction. No new store needed.
2. Cross-session continuity: build on the **existing** `/chat/search` full-text search
   (already in `api_auth_chat.py`) rather than a new memory subsystem — surface relevant
   past messages as LLM context when a query resembles a prior one.

**Open decisions:** none.

---

## Phase 3 — V2.4 Task & Project Management

**Current state — fully greenfield.** No `TaskStore`, no tasks screen, no endpoints.
The only related code is a one-off `remind me in <N> min to <task>` skill
(`assistant_domain.py:871`) and a RAG branch that treats "tasks/todo" keywords as a
WikiJS search (`assistant_domain.py:2539-2582`) — no persistence, no CRUD.
`tasks.manage` is not in `KNOWN_PERMISSIONS`.

This phase is foundational: later phases (Autonomous Planning's plan execution,
the V2.5 policy engine surfacing suggestions as tasks instead of just alerts) build on it.

**Build blocks (HA template, applied fresh):**
1. `jarvis/tasks/store.py` — `TaskStore`, JSON-persisted, per-user task lists with
   status (open/in-progress/done), due dates, priority, optional step breakdown.
2. `jarvis/tasks/service.py` — `TaskService`, auth + permission gated like
   `HomeAssistantService`, methods for create/update/complete/breakdown-via-LLM.
3. `jarvis/tasks/permissions.py` — `tasks.read`, `tasks.write`, `tasks.manage`, merged
   into `KNOWN_PERMISSIONS` in `permission_store.py`.
4. `jarvis/api_tasks.py` + `build_tasks_deps()` in `router_dependencies.py` + mount in
   `jarvisappv4.py`.
5. Frontend: new `TasksScreen.tsx` (or a tab on an existing screen) following the
   existing screen pattern (`useJ()`, `J` design tokens).
6. Chat skills in `assistant_domain.py::try_skill()`: create task, list open tasks,
   "break this down" (LLM-assisted step generation using the existing LLM fallback
   chain), daily surfacing of open/overdue tasks folded into the Morning Briefing.

**Open decisions:**
- Optional external sync (Notion / Linear / GitHub Issues) — **defer**; build the
  built-in `TaskStore` first, only add a sync `client.py` layer if actually wanted later.

---

## Phase 4 — V2.5 Autonomous Infrastructure Management

**Current state:** the automation/policy concept is **not generalized**. HA automation
rules live inside `HomeAssistantStore.automation_rules` (plain CRUD, no evaluation
logic) and are driven entirely by `chat_intents.py`'s NLU-to-HA-action bridge —
entity/area-specific, not domain-agnostic. `alert_engine.py` is architecturally the
closer starting point (rule store + background evaluator + broadcast already exist) but
today only reads from the HA store.

**Build blocks:**
1. Lift `automation_rules` out of `HomeAssistantStore` into a new domain-agnostic
   `PolicyStore` (`jarvis/policy_store.py`), keeping HA automations as one policy type
   among several.
2. Generalize `AlertEngine`'s evaluator (using Phase 0's pluggable signal-source
   refactor) to accept `IF condition THEN action` policies from multiple domains — HA,
   Proxmox (via the existing `proxmox_module.py`), system metrics (already read by
   `alert_engine.py`), later NAS.
3. Self-healing rules (service crash → restart → escalate on repeat failure): first
   concrete policies, executed through the **existing** write-skill machinery
   (`skill_utils.run_cmd` + service restart skill) gated by the existing
   `actions.write.execute` permission — no new execution primitive required.
4. Maintenance playbooks: new `PlaybookStore` + step executor with checkpoints,
   reusing the `ActionPlan`/`Skill` abstraction already defined in `jarvis_engine.py`.
   Each step requires confirmation OR is pre-approved via policy; full audit trail via
   the existing audit log store.

**Open decisions:**
- How aggressive should auto-remediation be by default (dry-run only vs. live action)?
  Recommend defaulting every new policy to dry-run/notify-only until explicitly enabled,
  consistent with the V2 principle "user stays sovereign."

---

## Phase 5 — V2.3 Communication Hub

The largest new external-integration surface — every sub-item needs real accounts/API
credentials, so sequence by complexity and defer anything without a chosen provider.

**Current state:** nothing exists yet for email, messaging, or calls. `calendar.read`/
`calendar.write` and `email.read`/`email.write` are already reserved in
`KNOWN_PERMISSIONS` (unused placeholders) — HA's calendar plumbing
(`home_assistant/store.py` calendar collection, `/home-assistant/calendar/*` endpoints)
is the closest existing analog and should be evaluated for reuse/extension before
building a separate `jarvis/calendar/` module from scratch.

**Build order:**
1. **Calendar** — lowest complexity, permissions already reserved. Decide: extend the
   existing HA calendar plumbing vs. a dedicated Google Calendar/CalDAV `jarvis/calendar/`
   module (HA template). Natural-language scheduling, conflict detection, meeting-prep
   briefing (reuses the Morning Briefing delivery mechanism from Phase 1).
2. **Email** — read/summarize/triage, draft-with-approval, daily briefing folded into
   the existing Morning Briefing. Credentials stored via the reused
   `secret_crypto.py` Fernet pattern.
3. **Messaging** (WhatsApp/Signal/Telegram bridge) and **Phone/Calls** (SIP/Twilio) —
   explicitly deferred until a provider is chosen; no code is worth writing against an
   undecided external API.

**Open decisions (need user input before Phase 5 starts):**
- Email: Gmail API (OAuth, richer but Google-account-coupled) vs. generic IMAP
  (provider-agnostic, simpler auth model)?
- Calls: Twilio/SIPGATE (hosted, fast to integrate) vs. self-hosted Asterisk/FreePBX
  (more private, more ops overhead)?
- Messaging: which bridge (WhatsApp Business API, Signal-CLI, Telegram Bot API) —
  or skip this sub-item entirely for V2?

---

## Phase 6 — V2.6 Extended System Integrations (backlog, pick-and-choose)

Not sequential — each item is independent and only worth scoping in detail once the
user picks it up.

- **Personal Cloud Workspace — early-win candidate.** Already scoped in a prior session:
  Apache Guacamole as a browser-based RDP/VNC gateway behind the existing Cloudflare
  Tunnel, Wake-on-LAN triggered via the existing Proxmox skill before connecting, a new
  "Workspace" screen embedding the session. **No dependency on any other phase** — can be
  pulled forward and built whenever the user wants it, independent of this sequencing.
- Network & Security (SNMP/UniFi/OPNsense, Pi-hole/AdGuard DNS logs) — placeholder,
  needs the user's actual network hardware confirmed.
- Storage & Files (Synology DSM API / TrueNAS API) — placeholder, needs NAS
  brand/model confirmed.
- Security & Surveillance (camera integration) — placeholder, needs camera
  hardware/protocol confirmed.
- Health & Biometrics (optional) — placeholder, needs wearable brand confirmed.
- Finance (optional) — placeholder, needs a Swiss open-banking API confirmed (limited
  bank support in CH — verify availability before scoping further).
- Smart Car (if API available) — placeholder, needs the user to confirm they own a
  compatible vehicle.

---

## Phase 7 — V2.7 Interface & Reach (interleaved, not a blocking phase)

**Current state:**
- PWA shell + Push notifications: **done in Phase 0** (don't rebuild here).
- Ambient Orb: the existing `OrbScreen.tsx` voice UI already covers this — it's not a
  separate always-on ambient display, it's the interactive voice screen.

**Still missing:**
- **Ambient Display Mode** — a genuinely separate, passive, always-on kiosk view
  (clock/weather/next event/status, no interaction) for a dedicated screen — distinct
  from `OrbScreen.tsx`. New lightweight route.
- Multi-device sync — session state shared across devices; moderate lift on top of the
  existing session/WebSocket architecture.
- Voice Everywhere — multi-speaker routing on top of the **already-built** wakeword
  engine (`jarvis/wakeword_engine.py`, `OpenWakeWordEngine`).
- **Plugin System** — explicitly the largest and lowest-priority item. Needs its own
  dedicated design pass (manifest format, sandboxing model, permission declaration) —
  do not start implementation without a separate planning session for this one alone.

---

## Recommended overall sequencing

```
Phase 0 (foundation) → Phase 1 (V2.1 gaps) → Phase 2 (V2.2 gaps)
    → Phase 3 (V2.4 tasks, new) → Phase 4 (V2.5 policy engine)
    → Phase 5 (V2.3 comms — needs provider decisions first)
    → Phase 6 (V2.6 — pick-and-choose anytime, Workspace can jump the queue)
    → Phase 7 (V2.7 — interleaved throughout, Plugin System last)
```
