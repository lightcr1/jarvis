# V1 Evidence Folder

Hier gehoeren die Nachweise hinein, die lokal nicht ehrlich automatisiert werden koennen.

## Empfohlene Dateien

- `YYYY-MM-DD_deploy_validation.md`
- `YYYY-MM-DD_manual_acceptance_v1.md`
- `YYYY-MM-DD_benchmark_report.json`
- `YYYY-MM-DD_recovery_drill_report.md`
- `YYYY-MM-DD_token_lifecycle_drill_report.md`
- `YYYY-MM-DD_admin_backup_restore_drill_report.md`

## Lokale Zusammenfassung erzeugen

```bash
python3 scripts/collect_v1_evidence.py --evidence-dir docs/v1/evidence --output docs/v1/evidence/status.md
```

Das Skript fasst zusammen, welche Evidenz-Gruppen bereits vorhanden sind und welche fuer V1 noch fehlen.

## Vorlagen erzeugen

```bash
python3 scripts/scaffold_v1_evidence.py --output-dir docs/v1/evidence --date 2026-03-15
```

Vorlagen liegen unter [docs/v1/evidence/templates](/home/jarvis/jarvis/docs/v1/evidence/templates) und helfen beim sauberen Sammeln von Deploy-, Benchmark-, Recovery- und Manual-Acceptance-Notizen.

## Offene V1-Nachweise

- echter Deploy auf Zielhost
- echte Dev/Test/Prod-Trennung
- Wakeword-, STT- und TTS-Qualitaet
- Performance auf Zielhardware
- Recovery-Drill auf echtem Service
- finale manuelle Abnahme

## Lokal bereits abgesichert

- modulare Backend-Router fuer Admin, Auth/Chat, Voice und Frontend-Auslieferung
- Skill-/RAG-Domaenenlogik und Runtime-/Session-Helfer aus dem Entrypoint gezogen
- `91` Python-Tests lokal gruen
- `7` Frontend-Tests lokal gruen
- Produktions-Build des Frontends lokal gruen
