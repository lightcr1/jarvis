# Jarvis V1 Sprint Plan (Execution Layer)

This plan translates the roadmap/checklist into executable sprint work.

## Assumptions

- Target release window remains August.
- Team capacity baseline: 2 backend engineers, 1 frontend engineer, 1 QA/ops (shared).
- Estimates are in **engineering days** (ideal days).

## Sprint 1 — Security Foundation Hardening (2 weeks)

## Goals
- Complete minimum enforceable RBAC behavior across engine/API paths.
- Make audit logs actionable for release evidence.
- Prepare emergency-stop operations protocol.

## Backlog

| ID | Task | Owner | Est. | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| S1-1 | Permission model normalization (`voice`, `write`, `dangerous`) | Backend | 2d | none | Shared permission constants + tests for role fallback behavior. |
| S1-2 | Enforce permission checks on all write/critical paths (engine + direct skills) | Backend | 3d | S1-1 | Deny-by-default for non-admin write/critical paths; tests pass. |
| S1-3 | Audit event schema v1 (`permission_denied`, `confirm_requested`, `emergency_blocked`) | Backend | 2d | S1-1 | JSONL schema documented + emitted for all relevant flows. |
| S1-4 | Emergency stop runbook + validation scenarios | Ops/QA | 2d | S1-2 | Runbook documented; simulation test evidence attached. |
| S1-5 | Security regression test pack (engine-level) | QA/Backend | 2d | S1-2 | Automated suite includes permission + emergency checks. |

## Exit Criteria
- No known write/critical bypass without token+permission.
- Audit logs contain complete trace for denied/confirmed/emergency flows.

---

## Sprint 2 — Admin Operations MVP (2 weeks)

## Goals
- Enable practical administration of users/roles/groups.
- Expose audit visibility to admins.

## Backlog

| ID | Task | Owner | Est. | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| S2-1 | Data model for users/groups/role assignments | Backend | 3d | S1 complete | Persistent store model + migration notes. |
| S2-2 | Admin APIs (`users`, `groups`, `assignments`) | Backend | 4d | S2-1 | CRUD APIs with auth checks and tests. |
| S2-3 | Audit log read/query endpoint (admin only) | Backend | 2d | S1-3 | Filter by event/time/role; access restricted to admin. |
| S2-4 | Admin dashboard skeleton (tabs: Users, Groups, Permissions, Audit) | Frontend | 4d | S2-2 | Navigable UI with API wiring and error states. |
| S2-5 | Permission matrix validation checklist execution | QA | 2d | S2-2/S2-4 | Checklist signed for admin/standard/guest/service scenarios. |

## Exit Criteria
- Admin can create/manage users and inspect audit events via UI/API.
- Role assignment changes affect runtime behavior as expected.

---

## Sprint 3 — Voice & Reliability Gate (2 weeks)

## Goals
- Stabilize voice workflow behavior for V1 acceptance.
- Validate fallback and performance baselines.

## Backlog

| ID | Task | Owner | Est. | Dependencies | Definition of Done |
|---|---|---|---:|---|---|
| S3-1 | Voice permission enforcement validation (`source=voice`) | QA/Backend | 2d | S1 complete | Denied/allowed paths tested with role variants. |
| S3-2 | STT/TTS failure-mode fallback test cases | QA | 2d | none | Simulated failures produce graceful responses. |
| S3-3 | Low-end performance baseline script + report | Ops/QA | 3d | none | P50/P95 latencies captured and compared to threshold. |
| S3-4 | Recovery drills (service restart/failure injection) | Ops | 2d | S1-4 | Recovery evidence logged and attached to release criteria. |
| S3-5 | Final P0 release criteria review pass | Product+QA | 1d | all above | RELEASE_CRITERIA_V1.md marked ready for RC gate. |

## Exit Criteria
- Voice and fallback workflows satisfy release checklist.
- Operations/recovery evidence complete for RC decision.

---

## Risk Register (Immediate)

| Risk | Impact | Mitigation |
|---|---|---|
| Missing dependency access in CI/dev env | Delayed validation | Maintain offline test subset + local stubs and deterministic engine tests. |
| Role bypass via new skill path | Security regression | Add mandatory RBAC test template for each new write/critical skill. |
| Audit volume growth without queryability | Poor incident response | Add indexed audit read endpoint + time range filters in Sprint 2. |
| Scope creep into post-V1 features | Schedule risk | Weekly triage: enforce V1 must-have gate from ROADMAP_V1.md. |

## Weekly Cadence

- **Mon:** Sprint planning + risk review (30 min)
- **Wed:** Mid-sprint checkpoint + blocker triage (20 min)
- **Fri:** Demo + evidence capture against `RELEASE_CRITERIA_V1.md` (30 min)

## Evidence Attachment Convention

Store validation artifacts under:

- `trace.md` (summary links)
- `tests/` for automated test evidence
- runtime logs under configured paths (audit and service logs)

Use naming scheme: `YYYY-MM-DD_<sprint>_<artifact>.md`.
