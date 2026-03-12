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

- [x] RBAC model implemented. (Role + user/group permission resolution + active-user identity checks validated in full suite)
- [x] Group-based permissions implemented. (Membership + permissions APIs validated in admin/authz regression coverage)
- [x] Deny-by-default enforcement active. (Permission-gated engine/chat/admin paths validated in full suite)
- [x] Token/session policy hardened. (Admin APIs require active bearer unlock tokens; revoke/expiry evidence drill added via `scripts/token_lifecycle_drill.py`)
- [x] Audit logs persisted and queryable. (Admin audit API supports filtered reads/counts with full regression coverage)

## Step 3 — Core Assistant Functionality

- [x] GitHub knowledge source productionized. (GitHub RAG refresh now ingests filtered blob content, not path names only)
- [ ] WikiJS removed from V1 critical path.
- [x] Fallback behavior deterministic and tested. (Full automated suite green under `.venv`; chat fallback/history coverage passing)
- [x] Skill execution permission-gated. (Engine/chat/direct skill permission paths covered across admin/authz/engine tests)

## Step 4 — Voice Pipeline

- [ ] Wakeword reliability baseline established.
- [ ] STT quality benchmarks passed.
- [ ] TTS quality benchmarks passed.
- [ ] Voice profiles reviewed for quality/usability.

## Step 5 — Admin Dashboard

- [x] Users tab complete.
- [x] Groups tab complete.
- [x] Permissions tab complete.
- [x] Action logs tab complete.
- [x] Settings tab complete.
- [x] Usage limits controls available.

## Step 6 — Deployment & Operations

- [ ] One-command deploy validated.
- [x] Update flow documented and tested.
- [x] Rollback flow documented and tested.
- [ ] Dev/Test/Prod environment split validated.
- [x] Backup and restore drill completed. (Probe-safe scripted drill added via `scripts/admin_backup_restore_drill.sh`)

## Step 7 — Quality & Release Readiness

- [ ] Manual acceptance pack executed and signed. (`docs/v1/handoff/MANUAL_ACCEPTANCE_V1.md`)
- [x] Core voice workflow tests pass. (Voice chat wakeword paths plus `/stt` and `/tts` endpoint tests green under `.venv`)
- [x] User permission tests pass. (RBAC/admin/authz/chat permission coverage green under `.venv`)
- [x] Dangerous-action confirmation tests pass. (Engine confirmation/emergency-stop regression pack green)
- [x] Fallback behavior tests pass. (Chat fallback/history + engine fallback coverage green)
- [ ] Lower-end hardware performance checks pass.
- [ ] Failure recovery tests pass.

## Step 8 — Launch

- [ ] Release candidate approved.
- [ ] Final changelog and release notes prepared.
- [ ] Monitoring and alerting reviewed.
- [ ] Launch completed.

## Step 1 Artifacts (Created)

- `docs/v1/planning/ROLE_PERMISSION_MATRIX_V1.md`
- `docs/v1/planning/RELEASE_CRITERIA_V1.md`

## Planning Artifacts (Execution Layer)

- `docs/v1/planning/ROADMAP_V1.md`
- `docs/v1/planning/EXECUTION_CHECKLIST_V1.md`
- `docs/v1/planning/ROLE_PERMISSION_MATRIX_V1.md`
- `docs/v1/planning/RELEASE_CRITERIA_V1.md`
- `docs/v1/planning/SPRINT_PLAN_V1.md`


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
- Update (this session): added `scripts/token_lifecycle_drill.py` to capture scripted unlock/revoke/expiry evidence against a live instance and `tests/test_token_lifecycle_drill.py` to pin the drill workflow with a stdlib mock server.
- Update (this session): added `scripts/admin_backup_restore_drill.sh` plus regression coverage so backup/restore evidence can be captured against a probe copy of the configured admin stores without mutating live data.
- Update (this session): runtime authz resolution now normalizes group ids and permission entries so malformed or drifted store data cannot silently expand effective permissions.
- Update (this session): added a repo-local `.venv`, installed `requirements.txt`, and validated the full automated suite successfully with `.venv/bin/python -m unittest discover -s tests -v`.
- Update (this session): default chat/memory/rag persistence paths now fall back safely when `/var/lib/jarvis` is unavailable, so test and constrained-runtime environments no longer fail on startup or chat writes.
- Update (this session): GitHub RAG refresh now fetches filtered text blob content with file/text caps and repo metadata, replacing the previous path-only cache behavior.
- Update (this session): added automated `/stt` and `/tts` endpoint coverage so the voice workflow gate has direct API-level regression evidence.
