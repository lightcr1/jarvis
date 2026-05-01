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
