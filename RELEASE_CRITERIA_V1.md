# Jarvis V1 Release Criteria

This document defines objective release gates for the August V1 launch.

## Release Decision Rule

V1 is releasable only if **all P0 criteria pass** and no open blocker defects remain.

## P0 Criteria (Must Pass)

## 1) Security & Access

- RBAC enforced on all sensitive actions.
- Permission checks validated for chat, voice, and API execution paths.
- Dangerous actions require explicit confirmation.
- Emergency stop blocks non-read actions.
- Audit log coverage includes action request, decision, and execution outcome.

**Evidence required**
- Automated tests for positive/negative permission paths.
- Manual security walkthrough report for top 10 dangerous actions.

## 2) Core Assistant Reliability

- Assistant responds reliably in text mode under normal load.
- Fallback chain behaves deterministically (skill -> safe fallback -> model fallback).
- GitHub knowledge ingestion/update flow works as documented.

**Evidence required**
- Integration tests for fallback behavior.
- Staging runbook output for knowledge refresh workflow.

## 3) Voice Workflow Stability

- End-to-end voice workflow (wakeword/stt/assistant/tts) passes acceptance scenarios.
- STT and TTS failure handling returns graceful fallback messages.

**Evidence required**
- Voice acceptance test checklist with pass/fail status.
- Error-injection test logs for STT/TTS outages.

## 4) Operations & Recovery

- Deployment procedure reproducible from clean environment.
- Update and rollback tested.
- Backup and restore validated.
- Dev/test/prod environment boundaries documented and enforced.

**Evidence required**
- Dry-run logs for deploy/update/rollback/restore.
- Environment configuration checklist signed.

## 5) Performance & Resilience

- Acceptable response times on target lower-end hardware profile.
- Service recovers cleanly after process restart and transient dependency failure.

**Evidence required**
- Performance benchmark report (P50/P95 latency).
- Recovery test report.

---

## Acceptance Scenario Pack (Minimum)

1. Guest user tries dangerous action -> denied + logged.
2. Standard user attempts out-of-scope device change -> denied + logged.
3. Admin executes dangerous action -> confirm required -> success + logged.
4. Emergency stop enabled -> dangerous and write actions blocked.
5. Voice command without permission -> denied with clear user feedback.
6. Knowledge query from GitHub source -> successful grounded answer.
7. STT service unavailable -> graceful fallback path.
8. Rollback after failed update -> service restored.

---

## Exit Artifacts Required Before Launch

- Signed release checklist (`EXECUTION_CHECKLIST_V1.md`).
- Completed manual acceptance pack (`MANUAL_ACCEPTANCE_V1.md` or dated copy).
- Security sign-off (RBAC + audit + emergency stop).
- Performance sign-off on target hardware class.
- Operations sign-off for deploy/update/rollback/backup/restore.
- Release notes and rollback plan published.
