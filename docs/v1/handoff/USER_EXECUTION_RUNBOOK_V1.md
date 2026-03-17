# Jarvis V1 User Execution Runbook

This file lists the remaining non-human roadmap tasks that must be executed by a user on real infrastructure or target hardware. The repo now contains the scripts, templates, and local automation needed to perform them.

## 1. WikiJS V1 Scope Confirmation

What to decide:
- Confirm that WikiJS is not part of the V1 critical path.
- If keeping that scope, leave `JARVIS_WIKIJS_ENABLED=0` in the active environment file.

How to do it:
1. Open [ROADMAP_V1.md](/home/jarvis/jarvis/docs/v1/planning/ROADMAP_V1.md).
2. Confirm the product decision that GitHub grounding is sufficient for V1 launch.
3. In the active environment config, keep `JARVIS_WIKIJS_ENABLED=0`.
4. Mark `WikiJS removed from V1 critical path` complete in [EXECUTION_CHECKLIST_V1.md](/home/jarvis/jarvis/docs/v1/planning/EXECUTION_CHECKLIST_V1.md).

Evidence to keep:
- The final deployed `config.env`.
- A dated note or commit confirming the scope decision.

## 2. One-Command Deploy Validation

What to run:
```bash
sudo cp config/env/prod.env.example /etc/jarvis/config.env
sudo ./scripts/deploy_local.sh
curl -k https://localhost/health || curl -k https://localhost:443/health
```

How to do it:
1. Use a clean target host or staging VM.
2. Copy [config/env/prod.env.example](/home/jarvis/jarvis/config/env/prod.env.example) into `/etc/jarvis/config.env`.
3. Fill in the real passphrase, allowed targets, and any API keys.
4. Run `sudo ./scripts/deploy_local.sh`.
5. Confirm `jarvis.service` is active and the health endpoint returns `{"ok": true}`.

Evidence to keep:
- Terminal output from `deploy_local.sh`.
- `systemctl status jarvis.service`.
- Successful health-check output.

## 3. Update And Rollback Execution On Real Host

What to run:
```bash
sudo ./scripts/update_local.sh
sudo ./scripts/rollback_local.sh
```

How to do it:
1. Start from an already deployed host.
2. Make a small harmless change in the repo version being deployed.
3. Run `sudo ./scripts/update_local.sh`.
4. Confirm the service still passes the health check.
5. Run `sudo ./scripts/rollback_local.sh`.
6. Confirm the previous release snapshot is restored and the health check still passes.

Evidence to keep:
- The snapshot directory path printed by `update_local.sh`.
- Health-check output after update.
- Health-check output after rollback.
- The generated admin data archive under the release snapshot.

## 4. Dev/Test/Prod Environment Split Validation

Prepared assets:
- [config/env/dev.env.example](/home/jarvis/jarvis/config/env/dev.env.example)
- [config/env/test.env.example](/home/jarvis/jarvis/config/env/test.env.example)
- [config/env/prod.env.example](/home/jarvis/jarvis/config/env/prod.env.example)

How to do it:
1. Create three environment files from those templates.
2. Verify each uses different state paths, ports, and passphrases.
3. Deploy dev, test, and prod separately or inspect the actual environment management system you use.
4. Confirm data written in one environment does not appear in another.

Evidence to keep:
- Final `dev`, `test`, and `prod` config files.
- A short note confirming store paths and ports are unique.
- Screenshots or command output proving each environment starts independently.

## 5. Lower-End Hardware Performance Check

Prepared asset:
- [scripts/benchmark_local.py](/home/jarvis/jarvis/scripts/benchmark_local.py)

What to run:
```bash
python3 scripts/benchmark_local.py --base-url https://127.0.0.1 --iterations 25 --output ./benchmark_report.json
```

How to do it:
1. Run Jarvis on the actual lower-end hardware target.
2. Execute the benchmark script against that live instance.
3. Review `p50` and `p95` for `/health` and `/chat`.
4. Decide whether those numbers meet your release threshold.

Evidence to keep:
- `benchmark_report.json`
- Hardware model / CPU / RAM note
- The threshold you judged as acceptable

## 6. Failure Recovery Execution

Prepared asset:
- [scripts/recovery_drill.sh](/home/jarvis/jarvis/scripts/recovery_drill.sh)

What to run:
```bash
sudo HEALTH_URL=https://127.0.0.1/health RESTART_COMMAND="systemctl restart jarvis.service" ./scripts/recovery_drill.sh ./recovery_drill_report.md
```

How to do it:
1. Run the drill on a real deployed instance.
2. Use the correct `HEALTH_URL` and `RESTART_COMMAND` for that host.
3. Confirm the report is produced and the service becomes healthy again within the timeout.
4. If you want deeper failure modes, repeat with dependency-specific restart commands.

Evidence to keep:
- `recovery_drill_report.md`
- Any additional logs if recovery took longer than expected

## 7. Ops Evidence Drills Already Prepared

Token lifecycle:
```bash
python3 scripts/token_lifecycle_drill.py \
  --base-url https://localhost \
  --passphrase "$JARVIS_PASSPHRASE" \
  --admin-user-id <admin_user_id> \
  --audit-log-path /var/lib/jarvis/audit.log \
  --insecure \
  --report-path ./token_lifecycle_drill_report.md
```

Backup and restore:
```bash
bash scripts/admin_backup_restore_drill.sh ./admin_backup_restore_drill_report.md
```

Keep both reports as launch evidence.

Optional local summary:

```bash
python3 scripts/collect_v1_evidence.py --evidence-dir docs/v1/evidence --output docs/v1/evidence/status.md
python3 scripts/scaffold_v1_evidence.py --output-dir docs/v1/evidence --date 2026-03-15
```

## 8. Checklist Items You Can Mark After Running The Above

After successful execution, update [EXECUTION_CHECKLIST_V1.md](/home/jarvis/jarvis/docs/v1/planning/EXECUTION_CHECKLIST_V1.md):
- `WikiJS removed from V1 critical path`
- `One-command deploy validated`
- `Dev/Test/Prod environment split validated`
- `Lower-end hardware performance checks pass`
- `Failure recovery tests pass`

Do not mark those complete before the real-host evidence exists.
