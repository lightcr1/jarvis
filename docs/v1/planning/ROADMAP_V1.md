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

> V1 ships a reliable assistant. V2 makes it feel like Tony Stark's JARVIS.
> Not just a system that responds — a system that observes, plans, acts, and communicates
> across every dimension of your life. Infrastructure, home, calendar, communication,
> research, finance, health. One brain. Everything connected.

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

Every part of that exchange is a V2 feature. None of it requires the user to ask twice.

---

## V2.1 — Proactive Intelligence Engine

The foundation of everything. Without this, JARVIS is a chatbot. With it, JARVIS is alive.

### Background Alert Engine
- Permanent background monitoring process — never sleeps, never polls on a timer
- Event-stream architecture: HA WebSocket push, Proxmox event log, syslog tail
- Configurable rule engine: threshold, duration, cooldown, severity, action
- Built-in rules:
  - CPU sustained >90% for >5 min → alert + optional auto-action
  - RAM >85% → alert
  - Disk >90% → alert + suggest cleanup
  - VM/container down → alert + optional auto-restart
  - Service down → alert + auto-restart with retry limit
  - Door/window open >N minutes → alert
  - Motion detected in restricted zone → alert + camera snapshot
  - Network device offline → alert
- Admin UI: full rule editor — create, edit, enable/disable, dry-run
- Delivery: WebSocket to frontend, TTS if voice active, push notification to phone

### Scheduled Intelligence
- Daily briefing at user-defined time — JARVIS speaks first, unprompted
  - Weather, calendar overview, system status, overnight alerts, important messages
- Weekly digest: resource trends, top events, what JARVIS did autonomously
- Nightly summary: what happened today, what needs attention tomorrow

### Proactive Suggestions
- Pattern-based recommendations from observed behavior
  - "You restart nginx every Monday — should I automate that?"
  - "Your VM lab-01 has been idle 8 days — suspend it?"
  - "Three backups failed silently this week — investigate?"
- Suggestions surfaced in chat + dismissible notification card

---

## V2.2 — Persistent Memory + Deep Context

### Long-Term Memory Store
- JARVIS remembers everything you tell it to, and learns what you don't
- Explicit: "Remember I prefer 20°C in the office" → stored, applied automatically
- Implicit: learns from behavior — which VMs you use, what time you work, what you ignore
- Named aliases: "my main server" = pve-01, "the lab" = specific VM group
- People: "my manager" = name + contact info, "the team" = group definition
- Memory UI in Settings: view, edit, delete any stored memory

### Contextual Awareness
- Knows time of day, day of week, upcoming events, recent activity
- Adapts tone and detail level accordingly
  - Morning: detailed briefing mode
  - Night: minimal, quiet, no non-urgent alerts
  - Pre-meeting: surfaces agenda, relevant files, prior notes
- Respects "Do Not Disturb" schedules

### Cross-Session Continuity
- Full conversation history persists and is searchable
- JARVIS can reference prior context: "Last Tuesday you asked about X — here's an update"
- Task continuity: "You were working on the API migration — here's where it stood"

---

## V2.3 — Communication Hub

Tony's JARVIS handles all communication. JARVIS V2 does the same.

### Email
- Read, summarize, and triage incoming email (Gmail / IMAP)
- Priority inbox: JARVIS surfaces what matters, buries what doesn't
- Drafting: "Reply to Lukas and tell him Thursday works"
  → JARVIS drafts, shows for approval, sends on confirmation
- Autonomous actions: auto-archive newsletters, flag invoices, forward specific senders
- Daily email briefing: "3 important emails, 12 newsletters archived, 1 flagged for action"

### Calendar & Scheduling
- Full read/write access to calendar (Google Calendar / CalDAV)
- Natural language scheduling: "Block 2 hours Thursday afternoon for deep work"
- Smart conflict detection: "You have a meeting at 15:00 — that overlaps, move it?"
- Meeting prep: 10 minutes before any meeting, JARVIS briefs agenda + attendees + context
- Travel-aware scheduling: "Journey to Zurich takes 45 min — blocked buffer before 09:00 meeting"
- Recurring plan creation: "Set up a weekly review every Friday at 16:00"
- Attendee coordination: can send calendar invites and rescheduling requests on your behalf

### Phone & Calls (V2 stretch goal)
- JARVIS answers calls when you're unavailable: "He's unavailable — can I take a message?"
- Voicemail transcription: voice → text, summarized and surfaced in inbox
- Outbound call initiation: "Call Lukas" → JARVIS dials via VoIP (SIP/WebRTC)
- Call screening: known contacts pass through, unknown filtered or queued
- Integration: SIP server (Asterisk/FreePBX) or VoIP API (Twilio, SIPGATE)

### Messaging
- Read and send messages via configured integrations (WhatsApp, Signal, Telegram via bridge)
- "Send a message to [contact] saying I'll be 10 minutes late"
- JARVIS can hold holding responses: "I'll let them know you'll reply shortly"

---

## V2.4 — Autonomous Planning & Work

The most ambitious part. JARVIS doesn't just answer — it works.

### Task & Project Management
- Full task system: create, assign, track, complete
- "JARVIS, I need to migrate the database by Friday — break it down"
  → JARVIS creates a step-by-step plan, estimates time, tracks progress
- Integrations: Notion, Linear, GitHub Issues, or built-in JARVIS task store
- Daily: surfaces open tasks, what's overdue, what can be done now
- Proactive: "You have 2 hours free before the meeting — your highest priority task is X"

### Research & Information Gathering
- "Research the best self-hosted CI tools and summarize the top 3"
  → JARVIS searches, reads, synthesizes, delivers a structured summary
- Topic monitoring: "Keep an eye on news about Cloudflare tunnel updates"
  → JARVIS checks periodically, surfaces relevant changes
- Competitive/technical watch: monitors GitHub releases, blog posts, documentation changes
  for projects you care about

### Autonomous Document Work
- Draft documents on request: reports, meeting notes, proposals, emails
- "Write a summary of last week's system events as a PDF report"
- "Turn these bullet points into a proper README"
- Summarize long documents: paste or link → JARVIS reads and gives key points

### Plan Execution
- JARVIS can execute multi-step plans autonomously with checkpoints
  - "Deploy the new backend version" → pull → test → snapshot → deploy → verify → report
  - "Clean up the Proxmox cluster" → list idle VMs → suspend candidates → archive snapshots → report
- Each step requires confirmation OR is pre-approved via policy
- Full audit trail: what was done, what was skipped, what failed and why

---

## V2.5 — Autonomous Infrastructure Management

### Self-Healing Systems
- Services crash → JARVIS detects, restarts, notifies, escalates if retry fails
- VM down → attempt restart, if fails → notify + suggest action
- Disk full → auto-prune Docker images / old logs based on policy
- Certificate expiry → alert 30 days before, optionally auto-renew (Let's Encrypt)
- Backup failure → alert + retry + escalate

### Policy Engine
- User-defined automation rules with full power
  ```
  IF  disk_usage(pve-01) > 90%
  AND last_prune > 7 days ago
  THEN prune_docker_images(pve-01)
  AND  notify("Pruned X GB from pve-01")
  ```
- Policies stored in `policies.json`, editable in admin UI
- Dry-run mode: simulate what JARVIS would have done without acting
- All policy executions audited with full context

### Multi-Step Maintenance Workflows
- Pre-built playbooks: maintenance mode, backup-and-upgrade, disaster recovery
- Custom playbooks: define trigger → steps → rollback → notify
- "Prepare pve-01 for maintenance" → stops VMs → snapshots → notifies → waits → confirms

### Infrastructure Awareness
- Dependency map: which services depend on which VMs, containers, databases
- Impact analysis: "If I take down lab-vm-02, these 3 services go down"
- Capacity planning: trend analysis → "At current growth, disk fills in ~18 days"

---

## V2.6 — Extended System Integrations

### Personal Cloud Workspace
- Browser-based remote desktop embedded in JARVIS (Apache Guacamole)
- Connect to home PC from anywhere via Cloudflare Tunnel
- Wake-on-LAN: JARVIS powers on home PC before you connect
- "Workspace" screen: one click to your full desktop, from anywhere in the world

### Network & Security
- Router/switch/AP monitoring (SNMP, UniFi API, OPNsense API)
- DNS log integration (Pi-hole / AdGuard): query trends, blocked threats
- Bandwidth per device: who's using what, anomaly detection
- VPN: who's connected, session duration, disconnect on demand
- Intrusion detection: unusual traffic patterns → alert

### Storage & Files
- NAS integration (Synology DSM API / TrueNAS API)
  - Storage pool health, volume usage, SMART status
  - Backup job status and failure alerts
  - File search: "Find the deployment script I wrote last month"
- Cloud storage sync status (if configured)

### Security & Surveillance
- Camera integration: motion events, snapshot on trigger
- "Show me the front door camera" → JARVIS returns live snapshot
- Alert with snapshot: "Motion detected at 02:30 — [image]"
- Door/window sensor history and timeline

### Health & Biometrics (optional)
- Wearable integration (Garmin, Apple Health via export, Fitbit)
- Sleep summary in morning briefing: "You slept 6h 20min, 2 interruptions"
- Activity tracking: steps, workouts surfaced in daily summary
- JARVIS adapts behavior based on sleep quality (quieter if poor sleep detected)

### Finance (optional)
- Bank account overview via open banking API (if available in region)
- Spending alerts: unusual transaction → immediate notification
- Monthly summary: "You spent CHF 340 on food delivery in May — up 20%"
- Bill tracking: upcoming payments surfaced in weekly briefing

### Smart Car (if API available)
- Vehicle status: charge level, range, door lock status, location
- "Is my car locked?" → instant answer
- Alert on low charge if trip planned next morning
- Integration: Tesla API, VW/Skoda, BMW ConnectedDrive, etc.

---

## V2.7 — Interface & Reach

### Full PWA + Mobile Push Notifications
- Push notifications to phone even when app is closed
- Tap notification → opens JARVIS directly to relevant context
- Critical alerts bypass Do Not Disturb (configurable)

### Ambient Display Mode
- Dedicated always-on screen (Raspberry Pi + monitor or old tablet)
- Shows: clock, weather, next event, system status, latest alert
- No interaction needed — pure passive awareness
- Night mode: minimal display, dimmed, clock only

### Multi-Device Sync
- Session state shared across phone, desktop, dedicated screen
- Start a conversation on phone, continue on desktop
- Notifications dismissed on one device clear on all

### Voice Everywhere
- Wake-word detection on always-on device ("Hey JARVIS")
- JARVIS responds on nearest active speaker
- Conversation mode: multi-turn voice without re-triggering wake word

### Plugin System
- Third-party skill packs installable without code changes
- Plugin manifest: skills, permissions requested, UI tabs, background tasks
- Sandboxed execution — plugins cannot access data beyond declared permissions
- Plugin store (long-term community goal)

---

## V2 Principles

- **Proactive over reactive** — JARVIS speaks when something matters, not only when asked
- **Policy over prompts** — configure once, JARVIS executes continuously and autonomously
- **Audit everything** — every autonomous action logged: what, why, outcome, rollback
- **User stays sovereign** — all automation is opt-in; any action can be reversed or blocked
- **Privacy first** — local processing where possible; nothing leaves the network without explicit config
- **One interface** — not a collection of apps, one coherent system across all domains
- **Graceful degradation** — if one integration fails, everything else keeps working

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
