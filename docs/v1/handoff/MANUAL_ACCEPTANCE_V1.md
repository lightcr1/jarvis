# Jarvis V1 Manual Acceptance Pack

This file contains the tests that cannot be closed by automation alone.

Use it as the human sign-off artifact for the remaining V1 roadmap items.

## How To Use

1. Run the automated suite first:

```bash
.venv/bin/python -m unittest
cd frontend && npm run test:run && npm run build && cd ..
```

2. Execute the manual scenarios below on the target environment.
3. Record pass/fail, notes, timestamps, and operator initials inline.
4. Save the completed copy as a dated artifact, for example:

```text
2026-03-12_manual_acceptance_v1.md
```

---

## Section A: Security Walkthrough

Purpose: close the remaining human-review part of the April security baseline.

### A1. Dangerous Action Denial Matrix

Preconditions:
- Jarvis running
- At least one `admin`, one `standard_user`, one `guest_restricted`
- Audit log path known

Steps:
1. As `guest_restricted`, attempt a dangerous action such as service restart or another critical skill.
2. Confirm the response is denied clearly.
3. Confirm an audit event exists for the denial.
4. Repeat as `standard_user`.
5. Repeat as `admin` and confirm the system requests confirmation rather than executing immediately.

Expected:
- `guest_restricted` denied
- `standard_user` denied
- `admin` receives confirmation flow
- Audit evidence exists for each path

Result: `PASS / FAIL`
Notes:

### A2. Emergency Stop Validation

Steps:
1. Enable emergency stop.
2. Attempt one write action.
3. Attempt one dangerous action.
4. Attempt one read-only action.
5. Disable emergency stop.
6. Repeat a previously blocked write action.

Expected:
- Write and dangerous actions blocked
- Read-only action still works
- Audit events show block reason
- Action works again after emergency stop is cleared

Result: `PASS / FAIL`
Notes:

### A3. Token Lifecycle Evidence

Steps:
1. Run:

```bash
python3 scripts/token_lifecycle_drill.py \
  --base-url https://localhost:8000 \
  --passphrase "$JARVIS_PASSPHRASE" \
  --admin-user-id <admin_user_id> \
  --audit-log-path <audit_log_path> \
  --insecure \
  --report-path ./token_lifecycle_drill_report.md
```

2. Review generated report.
3. Confirm revoke denial and audit correlation are understandable to a human reviewer.

Expected:
- Report generated
- All drill steps pass
- Audit trail is sufficient for incident reconstruction

Result: `PASS / FAIL`
Notes:

---

## Section B: Voice Workflow Acceptance

Purpose: close the June voice quality and device-readiness gates that require human hearing and UX judgment.

### B1. Wakeword Reliability

Steps:
1. Enable wakeword.
2. In a quiet room, speak the wakeword 10 times.
3. In moderate background noise, speak the wakeword 10 times.
4. Speak 10 near-miss phrases that should not trigger it.

Expected thresholds:
- Quiet room trigger success: `>= 9/10`
- Moderate noise trigger success: `>= 7/10`
- False positives on near-miss phrases: `<= 1/10`

Result: `PASS / FAIL`
Measured quiet success:
Measured noisy success:
Measured false positives:
Notes:

### B2. STT Comprehension Quality

Steps:
1. Dictate 10 short commands.
2. Dictate 5 mixed technical phrases containing terms like `PVE`, `API`, `VMID`, or service names.
3. Dictate 5 free-form natural language questions.

Expected:
- No catastrophic transcription failures
- Technical terms are transcribed well enough to be actionable
- Misheard output remains understandable and recoverable

Result: `PASS / FAIL`
Notes:

### B3. TTS Quality Review

Steps:
1. Test both candidate TTS voices.
2. Listen to 10 short replies and 5 longer replies.
3. Include responses containing acronyms and command names.

Judge:
- Naturalness
- Clarity
- Fatigue over repeated listening
- Pronunciation of technical terms
- Persona fit for Jarvis

Expected:
- At least one voice is acceptable for daily use
- No recurring pronunciation issue that blocks usability

Chosen voice:
Result: `PASS / FAIL`
Notes:

### B4. STT/TTS Failure Handling

Steps:
1. Make STT unavailable and attempt a voice request.
2. Make TTS unavailable and attempt a voice response.
3. Restore services and retry.

Expected:
- Failure message is understandable
- App does not hang or crash
- Recovery after service restoration is clean

Result: `PASS / FAIL`
Notes:

---

## Section C: GitHub Knowledge Productionization

Purpose: close the remaining core-assistant roadmap item that needs content quality judgment.

### C1. GitHub Ingestion Sanity

Preconditions:
- `GITHUB_REPO` configured
- `GITHUB_BRANCH` configured

Steps:
1. Refresh GitHub knowledge source.
2. Ask 5 questions whose answers are known to exist in the repo.
3. Ask 3 questions that are not answered by the repo.

Expected:
- Repo-backed answers are grounded and relevant
- Out-of-scope questions do not hallucinate grounded repo facts
- Failure mode is clear when answer is unavailable

Result: `PASS / FAIL`
Notes:

### C2. Grounding Quality Check

Steps:
1. Pick 3 repo-backed responses.
2. Compare each response manually to the source file or README section.
3. Check whether the answer is materially accurate and not misleading.

Expected:
- No material contradiction between answer and source
- Summary may compress but must not distort meaning

Result: `PASS / FAIL`
Notes:

---

## Section D: Operations And Recovery

Purpose: close the July operations gates that require real-environment execution.

### D1. Deploy Reproducibility

Steps:
1. Start from a clean host or clean VM snapshot.
2. Run the documented deployment flow.
3. Confirm service starts, UI loads, and health endpoint works.

Expected:
- Deployment succeeds without undocumented manual fixes
- Final state matches README expectations

Result: `PASS / FAIL`
Host / VM:
Notes:

### D2. Backup And Restore Drill

Steps:
1. Run:

```bash
bash scripts/admin_backup_restore_drill.sh ./admin_backup_restore_drill_report.md
```

2. Review report.
3. Confirm the produced artifact is sufficient for ops sign-off.

Expected:
- Report generated
- All drill steps pass

Result: `PASS / FAIL`
Notes:

### D3. Update And Rollback

Steps:
1. Perform an update on a staging instance.
2. Verify health and key user flows.
3. Roll back to the previous known-good version.
4. Verify health and key user flows again.

Expected:
- Update path works or fails in a controlled way
- Rollback restores working state
- No silent config corruption

Result: `PASS / FAIL`
Notes:

### D4. Recovery Drill

Steps:
1. Restart the Jarvis service during normal use.
2. Simulate one transient dependency failure.
3. Confirm user-visible recovery behavior.
4. Confirm service health after dependency restoration.

Expected:
- Service comes back cleanly
- Failure is visible and understandable
- Recovery is possible without manual data repair

Result: `PASS / FAIL`
Notes:

---

## Section E: Performance

Purpose: close the lower-end hardware gate.

### E1. Low-End Hardware Baseline

Target hardware:
- CPU:
- RAM:
- Storage:

Steps:
1. Measure 20 text-only requests.
2. Measure 10 voice requests.
3. Record rough P50 and P95 latency.
4. Note any UI stalls or audio lag.

Expected:
- Latency acceptable for intended V1 usage
- No repeated hangs or runaway resource usage

Text P50:
Text P95:
Voice P50:
Voice P95:
Result: `PASS / FAIL`
Notes:

---

## Section F: Admin UX Review

Purpose: capture the remaining May admin-UI work that automation cannot meaningfully judge.

### F1. Admin Usability Pass

Steps:
1. Create a user.
2. Create a group.
3. Assign user to group.
4. Grant a permission.
5. Inspect audit logs.
6. Change a user role.
7. Delete created test data.

Judge:
- Is each task possible without CLI?
- Are errors understandable?
- Are dangerous changes visually clear?
- Is audit visibility good enough for admin use?

Expected:
- Admin can complete core management tasks from UI
- No task requires hidden system knowledge

Result: `PASS / FAIL`
Notes:

---

## Final Sign-Off

Security sign-off: `PASS / FAIL`
Voice sign-off: `PASS / FAIL`
Operations sign-off: `PASS / FAIL`
Performance sign-off: `PASS / FAIL`
Admin UX sign-off: `PASS / FAIL`

Release recommendation: `GO / NO-GO`

Reviewer:
Date:
Notes:
