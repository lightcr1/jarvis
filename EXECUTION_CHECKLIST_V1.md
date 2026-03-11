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
- [~] Token/session policy hardened. (Admin APIs now require active bearer unlock token)
- [~] Audit logs persisted and queryable. (Admin audit API supports event/role/time-range filters)

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

