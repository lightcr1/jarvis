# Jarvis V1 Execution Checklist

Use this file as the operational tracker while building toward August launch.

## Step 0 — Immediate (This Week)

- [ ] Confirm V1 target date and freeze policy.
- [ ] Confirm product owner + technical owner per workstream.
- [ ] Confirm non-V1 features explicitly deferred.
- [ ] Create weekly release review cadence.

## Step 1 — Governance & Requirements

- [ ] Role matrix approved (`admin`, `standard_user`, `guest_restricted`, `service_system`).
- [ ] Permission matrix approved:
  - [ ] voice command access
  - [ ] device management
  - [ ] calendar/email read
  - [ ] dangerous actions
- [ ] Dangerous-action confirmation policy documented.
- [ ] Emergency stop semantics defined.
- [ ] Privacy rules per user defined.

## Step 2 — Security & Access Implementation

- [~] RBAC model implemented. (Role + user/group permission resolution + active-user identity checks scaffolded)
- [~] Group-based permissions implemented. (Membership + permissions APIs scaffolded)
- [~] Deny-by-default enforcement active. (Permission allowlist validation added in admin policy APIs)
- [~] Token/session policy hardened. (Admin APIs now require active bearer unlock token; unlock tokens now support explicit revoke and expired-token pruning)
- [~] Audit logs persisted and queryable. (Admin audit API supports event/role/time-range filters across `role` + `actor_role` events)

## Step 3 — Core Assistant Functionality

- [ ] GitHub knowledge source productionized.
- [ ] WikiJS removed from V1 critical path.
- [ ] Fallback behavior deterministic and tested.
- [~] Skill execution permission-gated. (Engine/app permission resolution wired, further integration pending)

## Step 4 — Voice Pipeline

- [ ] Wakeword reliability baseline established.
- [ ] STT quality benchmarks passed.
- [ ] TTS quality benchmarks passed.
- [ ] Voice profiles reviewed for quality/usability.

## Step 5 — Admin Dashboard

- [~] Users tab complete. (Backend APIs scaffolded)
- [~] Groups tab complete. (Backend APIs scaffolded)
- [~] Permissions tab complete. (Backend assignments + permissions APIs scaffolded)
- [ ] Action logs tab complete.
- [ ] Settings tab complete.
- [ ] Usage limits controls available.

## Step 6 — Deployment & Operations

- [ ] One-command deploy validated.
- [ ] Update flow documented and tested.
- [ ] Rollback flow documented and tested.
- [ ] Dev/Test/Prod environment split validated.
- [~] Backup and restore drill completed. (backup/restore scripts scaffolded)

## Step 7 — Quality & Release Readiness

- [ ] Core voice workflow tests pass.
- [ ] User permission tests pass.
- [ ] Dangerous-action confirmation tests pass.
- [ ] Fallback behavior tests pass.
- [ ] Lower-end hardware performance checks pass.
- [ ] Failure recovery tests pass.

## Step 8 — Launch

- [ ] Release candidate approved.
- [ ] Final changelog and release notes prepared.
- [ ] Monitoring and alerting reviewed.
- [ ] Launch completed.

## Step 1 Artifacts (Created)

- `ROLE_PERMISSION_MATRIX_V1.md`
- `RELEASE_CRITERIA_V1.md`

## Planning Artifacts (Execution Layer)

- `ROADMAP_V1.md`
- `EXECUTION_CHECKLIST_V1.md`
- `ROLE_PERMISSION_MATRIX_V1.md`
- `RELEASE_CRITERIA_V1.md`
- `SPRINT_PLAN_V1.md`


## Current Session Handoff Snapshot (2026-03-11)

- Branch: `work`
- Focus completed: docs/deploy regression hardening in `tests/test_deploy_config_defaults.py`
- Latest commit at handoff: `b4f8418`
- Validation baseline command: `python -m unittest discover -s tests`
- Current immediate next step: continue April Security + Access hardening evidence and close remaining Step 2 `[~]` items with production-readiness criteria.
- Update (this session): audit role-filter semantics hardened so admin-operation events keyed by `actor_role` are now queryable via `/admin/audit/events` and `/admin/audit/counts` role filters.
- Update (this session): token lifecycle hardening added via `/unlock/revoke` and shared expired-token pruning used by unlock/admin guards.
- Update (this session): token lifecycle edge-case fix shipped for epoch/falsy expiry timestamps (`exp is None` checks) with regression coverage.
- Update (this session): revoke path now requires an active token and prunes expired entries before evaluation.
- Update (this session): `/chat` now treats expired/revoked bearer tokens as missing for sensitive skill gating (no stale-token bypass).
- Update (this session): token store now enforces configurable max-active capacity (`JARVIS_MAX_ACTIVE_TOKENS`) with deterministic oldest-expiry eviction.
- Update (this session): unlock env parsing hardened with safe defaults/minimum clamps for invalid token TTL/capacity values.
- Update (this session): unlock/revoke flows now emit token-lifecycle audit events for issue/failure/revoke/deny outcomes.
- Update (this session): admin-operation audit events now include `actor_user_id` for principal-level attribution (not role-only).
- Update (this session): `/admin/audit/events` and `/admin/audit/counts` now support `actor_user_id` filtering for per-admin investigation queries.
- Update (this session): unlock/revoke audits now include non-secret `token_fingerprint` correlation ids for lifecycle traceability.
- Update (this session): admin audit APIs now support `token_fingerprint` filtering for token-lifecycle investigation queries.
- Update (this session): audit endpoints now validate `token_fingerprint` format (16 lowercase hex) and normalize blank filters.
- Update (this session): audit endpoints now validate `actor_user_id` filter format (`bootstrap` or `usr-[0-9a-f]{12}`).
- Update (this session): audit endpoints now validate `role` filter values against known RBAC roles.
- Update (this session): audit events endpoint now validates `event` filter format (`[a-z0-9_]{1,64}`).
- Update (this session): `/admin/audit/counts` now supports `event` filter for focused aggregation (plus shared event-format validation).
- Update (this session): added `/admin/audit/count` for single-number filtered audit counts (event/role/actor/token filters + validation).
- Update (this session): audit query time filters now reject negative timestamps across events/count/counts endpoints.
- Update (this session): audit endpoints now share a centralized filter normalization/validation helper to avoid drift.
- Update (this session): audit filters now case-normalize `event`/`role`/`token_fingerprint` inputs before validation.
