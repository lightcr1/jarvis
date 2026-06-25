# Jarvis V1 Roadmap (Target: August Launch)

This roadmap is focused on a **stable first usable release**.

## Product Principles for V1

- Ship a reliable assistant before shipping a perfect assistant.
- Prefer privacy-first and local-first behavior where possible.
- Enforce security and permission checks by default.
- Keep integrations narrow and robust for V1.

## Scope Categories

## 1) Must be in V1

### Knowledge & Reasoning
- Use **GitHub** as the primary knowledge implementation for V1.
- De-prioritize WikiJS RAG for V1 until reliability is proven.
- Keep deterministic skill-first routing with safe fallback.

### Security & Access
- Role model implemented and enforced:
  - `admin`
  - `standard_user`
  - `guest_restricted`
  - `service_system`
- Permission checks before every sensitive action.
- Dangerous-action confirmation flow required.
- Emergency stop / action disable switch.
- Audit logs for action execution and permission decisions.

### User & Admin Management
- User and group management.
- Permission assignment model.
- Admin dashboard with at least:
  - users
  - groups
  - permissions
  - action logs
  - key settings

### Voice & Assistant Core
- Reliable voice loop (wakeword/stt/assistant/tts).
- Better STT fallback behavior and error handling.
- Better TTS quality with at least two curated voices (if quality threshold met).

### Operations & Reliability
- Easy deployment path.
- Update + rollback strategy.
- Environment separation (`dev`, `test`, `prod`).
- Config management conventions.
- Backup and restore concept.

### Quality Gates
- Release criteria defined and measurable.
- Tests for:
  - core voice workflows
  - user permissions
  - dangerous-action confirmations
  - fallback behavior
  - recovery after failure
  - lower-end hardware performance baseline

## 2) Nice to have for V1.x

- Higher-quality multi-voice persona tuning.
- Initial cross-device sync primitives.
- Enhanced admin analytics (quota/usage insights).
- Extended smart-home onboarding reliability.

## 3) Future only (Post-V1)

- Full autonomous home-device provisioning at scale.
- Native full-feature apps across device classes.
- Telephony/call features.
- Multi-method auth suite (MFA, SSH-key/device auth, federated login).
- Long-horizon autonomous self-learning loops with strict policy controls.

---

# V2 Roadmap — "Real JARVIS" (Target: 2027)

> V2 transforms JARVIS from a reactive assistant into a proactive, autonomous system manager —
> the closest thing to Iron Man's JARVIS in a real home/lab environment.
> V1 ships a reliable assistant. V2 makes it feel alive.

## V2 Vision

JARVIS should observe, think, and act — without being asked. It knows what's happening across
every connected system, surfaces what matters, and takes pre-authorized actions autonomously.
The user sets policy once; JARVIS executes continuously.

---

## V2.1 — Proactive Intelligence

### Alert Engine (P0)
The core of "real JARVIS". A background rule engine that monitors all connected systems and
pushes alerts proactively — without the user asking.

- Configurable alert rules stored in `admin_settings.json`: thresholds, cooldowns, severity levels
- System resource alerts: CPU sustained >90%, RAM >85%, disk >90%, load spike
- Home Assistant state alerts: door left open, motion at unusual hours, thermostat deviation
- Proxmox alerts: VM down, storage critically full, node unreachable
- Admin UI section for managing alert rules (enable/disable, edit thresholds)
- `/ws/alerts` WebSocket delivers alerts to frontend in real time
- Voice delivery: JARVIS speaks alerts aloud when voice mode is active

### Morning Briefing + Scheduled Reports
- Daily briefing at configurable time: weather, calendar, system status, overnight alerts
- Weekly summary: resource trends, alert frequency, top actions taken
- JARVIS initiates these — user doesn't need to ask

### Proactive Suggestions
- "Sir, you have 3 services that haven't been restarted in 30 days."
- "Disk on pve-01 is at 88% — should I archive old backups?"
- Based on observed patterns, not hardcoded rules

---

## V2.2 — Persistent Memory + Context

### Long-Term Memory
- JARVIS remembers preferences, habits, and feedback across sessions
- "Remember that I prefer temperatures at 20°C" → stored, applied automatically
- Named aliases: "my server" = pve-01, "the office" = room entity X
- Memory UI in Settings: view, edit, delete what JARVIS knows

### Contextual Awareness
- JARVIS knows time of day, day of week, recent activity
- Adapts behavior: quieter at night, more detailed in the morning
- Notices patterns: "You usually restart nginx on Mondays — should I automate that?"

### Session Continuity
- Conversation context survives restarts
- JARVIS can reference things said in previous sessions: "Last week you mentioned..."

---

## V2.3 — Autonomous Action + Policy Engine

### Pre-authorized Autonomous Actions
- User defines action policies: "If disk > 90%, automatically prune old Docker images"
- "If front door is open after midnight, send alert and lock it"
- Policy editor in admin UI with dry-run mode before enabling

### Multi-Step Workflows
- "Prepare for maintenance": stop services → snapshot VM → notify → wait for confirmation
- "Morning routine": check all systems → summarize → set thermostat → turn on office lights
- Workflow builder: trigger + condition + action chain + rollback step

### Autonomous Recovery
- VM crashes → JARVIS detects, attempts restart, reports outcome
- Service goes down → auto-restart with retry limit and escalation alert
- All autonomous actions audited with reason, outcome, rollback option

---

## V2.4 — Expanded System Coverage

### Personal Cloud Workspace
- Browser-based remote desktop (Apache Guacamole) embedded in JARVIS
- Connect to home PC or Proxmox VM desktop from anywhere via Cloudflare Tunnel
- Wake-on-LAN: JARVIS can power on the home PC before connecting
- "Workspace" screen in the frontend

### Network & Infrastructure
- Network device monitoring: switches, APs, routers (SNMP or API)
- DNS query log integration (Pi-hole / AdGuard)
- Bandwidth usage by device
- VPN status and connected clients

### Extended Integrations
- NAS (Synology/TrueNAS): storage overview, backup jobs, alerts
- Security cameras: motion event feed, snapshot on alert
- Smart car (if API available): location, charge status, door lock
- Calendar deep integration: schedule-aware assistant behavior

### Multi-Instance / Multi-Location
- JARVIS instances in different locations (home, lab, cloud) sharing state
- Federated alerts: one instance monitors, all instances informed

---

## V2.5 — Interface & Experience

### Full PWA + Mobile Push
- Push notifications via Service Worker: alerts delivered to phone even when app is closed
- Mobile-optimized voice interface
- Offline-capable for status reads cached from last sync

### Ambient Display Mode
- Always-on status display for a dedicated screen (Raspberry Pi + monitor)
- Shows: time, weather, system status, latest alert, next calendar event
- No interaction needed — pure ambient awareness

### Plugin System
- Third-party skill packs installable without code changes
- Plugin manifest format: skills, permissions, UI tabs
- Community skill registry (long-term)

---

## V2 Principles

- **Proactive over reactive** — JARVIS speaks first when something matters
- **Policy over prompts** — set rules once, JARVIS executes continuously
- **Audit everything** — every autonomous action logged with full context and rollback
- **User stays in control** — all automation is opt-in, all actions are reversible or gated
- **Privacy first** — no data leaves the local network without explicit config

---

## Timeline (Step-by-Step)

## March (now): Scope Freeze + Architecture Baseline (1–2 weeks)

1. Freeze V1 backlog and explicitly cut non-V1 features.
2. Define cloud vs local execution policy.
3. Define role/permission matrix.
4. Define release criteria and acceptance tests.

**Exit criteria:** Signed-off V1 scope + architecture decision record.

### Current state marker (March 2026)

- ✅ Scope/architecture artifacts are in repo (`docs/v1/planning/ROADMAP_V1.md`, `docs/v1/planning/EXECUTION_CHECKLIST_V1.md`, `docs/v1/planning/RELEASE_CRITERIA_V1.md`, `docs/v1/planning/ROLE_PERMISSION_MATRIX_V1.md`, `docs/v1/planning/SPRINT_PLAN_V1.md`).
- [x] Security/access baseline is implemented and regression-validated locally (RBAC helpers, admin APIs, audit store, token + identity guard, modular router coverage, `91` Python tests green plus `7` frontend tests green).
- [x] Admin operations baseline is implemented locally (users/groups/assignments/permissions APIs, dashboard UI, backup/restore scripts, update/rollback flow, integrity checks).
- [x] Post-V1 Home-Assistant foundation is scaffolded inside Jarvis (`docs/v1/planning/HOME_ASSISTANT_FOUNDATION_PLAN.md`, dedicated backend domain, permissions, risk model, initial API/UI shell).
- ➡️ Next roadmap focus: remaining V1 execution work outside local automation: voice-quality sign-off on target hardware, deploy/update/rollback execution evidence, environment-split validation, and performance/recovery evidence.

## April: Security + Access Foundation (3–4 weeks)

1. Implement RBAC core.
2. Add permission checks to sensitive endpoints/actions.
3. Implement action confirmation + emergency stop.
4. Add audit/action logging pipeline.

**Exit criteria:** Security baseline functional end-to-end.

## May: Admin UX + Core UI stabilization (3–4 weeks)

1. Build admin dashboard core tabs.
2. Improve chat and orb UX consistency.
3. Add usage limits and observability basics.

**Exit criteria:** Admin can operate users/permissions/logs without CLI.

## June: Voice quality + Device readiness baseline (4 weeks)

1. STT reliability pass.
2. TTS quality pass and voice profile selection.
3. Wakeword optimization baseline for cross-device readiness.

**Exit criteria:** Robust conversational loop under realistic conditions.

## July: Integration hardening + Release candidate (4 weeks)

1. GitHub knowledge ingestion hardening.
2. Reliability pass for assistant actions + fallback.
3. Backup/restore/rollback drills.
4. Full regression + performance checks.

**Exit criteria:** Release candidate approved.

## August: Launch window (1–2 weeks)

1. Bugfix-only sprint.
2. Final release tests and documentation.
3. Controlled rollout and monitoring.

**Exit criteria:** V1 shipped.
