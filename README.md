# J.A.R.V.I.S

Lokaler Text- und Voice-Assistant mit Skill-Engine, RBAC/Admin-Bereich, Proxmox-Integration, GitHub-RAG und optionalem Cloud-LLM-Fallback.

## Status

- Automatischer Repo-Stand ist aktuell konsistent.
- Der lokale Teststand ist gruen: `87` Python-Tests mit `.venv/bin/python -m unittest`.
- Zusaetzlich ist das Frontend gruen: `7` Vitest-Tests und ein erfolgreicher Produktions-Build.
- Die noch offenen V1-Punkte sind keine lokalen Code-Luecken mehr, sondern echte Betriebs- und Qualitaetsnachweise auf Zielhardware.

## Repo-Struktur

```text
.
|- jarvisappv4.py              Schlanker FastAPI-App-Entrypoint
|- jarvis/                     Backend-Paket mit Routern, Engine, Stores und Hilfsmodulen
|- frontend/                   React-/TypeScript-SPA fuer Chat, Orb und Dashboard
|- static/                     Legacy-Static-Dateien und Fallback-Artefakte
|- scripts/                    Deploy-, Update-, Recovery- und Ops-Skripte
|- tests/                      Automatisierte Regressionstests
|- config/                     Beispiel-Konfigurationen
|- systemd/                    Service-Units
`- docs/
   |- README.md                Doku-Uebersicht
   |- archive/                 Alte Quelldokumente
   `- v1/
      |- planning/             Roadmap, Checklisten, Release-Kriterien
      |- handoff/              Runbooks und manuelle Abnahme
      `- evidence/             Ablage fuer echte V1-Nachweise
```

## Schnellstart lokal

### 1. Umgebung vorbereiten

```bash
python3 -m venv .venv
. .venv/bin/activate
.venv/bin/python -m pip install -r requirements.txt
cp config/env/dev.env.example .env.local
```

Das Frontend lebt in `frontend/`. Fuer lokale UI-Arbeit:

```bash
cd frontend
npm install
npm run build
cd ..
```

Die API-Routen sind inzwischen modular im Backend-Paket organisiert:

- `jarvis/frontend_routes.py` fuer SPA-Auslieferung und Legacy-Redirects
- `jarvis/api_admin.py` fuer Admin-API
- `jarvis/api_auth_chat.py` fuer Auth, Unlock, Chat, Sessions und RAG
- `jarvis/api_voice.py` fuer STT/TTS
- `jarvis/assistant_domain.py` fuer Skill- und RAG-Domaenenlogik
- `jarvis/runtime_helpers.py` fuer Session-, Token-, Audit- und Seeding-Helfer
- `jarvis/router_dependencies.py` fuer die Live-Dependency-Schicht zwischen `jarvisappv4.py` und den Routern

Danach mindestens diese Werte setzen:

```env
JARVIS_PASSPHRASE=change-me
ALLOWED_TARGETS=local
```

Die App liest Umgebungsvariablen. Fuer einen einfachen lokalen Start kannst du die Werte direkt exportieren:

```bash
set -a
source .env.local
set +a
```

### 2. Server starten

```bash
.venv/bin/python -m uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000
```

Danach erreichbar unter:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/chat`
- `http://127.0.0.1:8000/orb`
- `http://127.0.0.1:8000/dashboard/login`

## Sauberes Setup fuer einen echten Host

### Voraussetzungen

- `bash`
- `python3`
- `systemd`
- `rsync`
- `openssl`
- optional fuer SST: `node`, `npm`

### Empfohlenes Deployment

```bash
sudo cp config/env/prod.env.example /etc/jarvis/config.env
sudo ./scripts/deploy_local.sh
```

Das Deployment erledigt in einem Lauf:

1. Repo nach `/opt/jarvis` synchronisieren
2. virtuelle Umgebung unter `/opt/jarvis/.venv` erstellen
3. Python-Abhaengigkeiten installieren
4. Frontend unter `/opt/jarvis/frontend` bauen
5. `/etc/jarvis/config.env` vorbereiten
6. TLS-Dateien erzeugen, falls noetig
7. `jarvis.service` installieren und starten
8. Healthcheck und Admin-Dateninitialisierung ausfuehren

Pruefen:

```bash
systemctl status jarvis.service
curl -k https://localhost/health || curl -k https://localhost:443/health
```

## Konfiguration

Zentrale Datei:

- `/etc/jarvis/config.env`

Vorlagen:

- `config/jarvis.env.example`
- `config/env/dev.env.example`
- `config/env/test.env.example`
- `config/env/prod.env.example`

Wichtige Basiswerte:

```env
JARVIS_PASSPHRASE=change-me
ALLOWED_TARGETS=local,web01
COOLDOWN_RESTART_SECONDS=60
COOLDOWN_CRITICAL_SECONDS=90
JARVIS_ADMIN_SETTINGS_PATH=/var/lib/jarvis/admin_settings.json
```

Typische Integrationen:

```env
PROXMOX_BASE_URL=https://pve.example.local:8006
PROXMOX_API_TOKEN=root@pam!jarvis=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...

GITHUB_REPO=owner/repo
GITHUB_BRANCH=main
GITHUB_PAT=ghp_...

WIKIJS_GRAPHQL_URL=https://wiki.example.local/graphql
WIKIJS_API_KEY=...

PIPER_BIN=/usr/local/bin/piper
PIPER_MODEL=/opt/models/en_US-amy-medium.onnx
```

Nach jeder Aenderung:

```bash
sudo systemctl restart jarvis.service
```

## Bedienung

Wichtige UIs:

- `/` fuer Chat
- `/chat` fuer Chat
- `/orb` fuer die Orb-Oberflaeche
- `/dashboard/login` fuer den getrennten Admin-Login
- `/dashboard` fuer Benutzer, Gruppen, Rechte, Audit und Settings

Wichtige Skills:

- `help`
- `skills`
- `status jarvis`
- `diagnose jarvis`
- `proxmox health`
- `pve vm status <host_id> <node> <vmid>`
- `pve lxc status <host_id> <node> <vmid>`
- `service status <target> <service>`
- `service restart <target> <service>`

## Voice und Wakeword

- Browser-Mikrofon braucht `https://...` oder `localhost`.
- Wakeword ist standardmaessig privacy-first deaktiviert.
- Standardphrase: `hey jarvis`
- Laufende Runtime-Steuerung fuer Wakeword und STT liegt in `/dashboard/settings`.

Beispiel:

```env
JARVIS_WAKEWORD_ENABLED=0
JARVIS_WAKEWORD_PHRASE=hey jarvis
PIPER_LENGTH_SCALE=1.12
PIPER_NOISE_SCALE=0.55
PIPER_NOISE_W=0.75
```

## HTTPS und Zertifikate

Das Deploy-Skript aktiviert HTTPS standardmaessig. Wenn keine Zertifikate vorhanden sind, erzeugt `scripts/deploy_local.sh` automatisch ein self-signed Zertifikat unter:

- `/etc/jarvis/tls/fullchain.pem`
- `/etc/jarvis/tls/privkey.pem`

Danach laeuft Jarvis standardmaessig auf:

- `https://<host>/`
- Standard-Port: `443`

Eigenes Zertifikat manuell erzeugen:

```bash
sudo mkdir -p /etc/jarvis/tls
sudo openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout /etc/jarvis/tls/privkey.pem \
  -out /etc/jarvis/tls/fullchain.pem \
  -days 825 \
  -subj "/CN=jarvis.local"
sudo chmod 600 /etc/jarvis/tls/privkey.pem
sudo chmod 644 /etc/jarvis/tls/fullchain.pem
```

Danach in `/etc/jarvis/config.env` setzen oder pruefen:

```env
JARVIS_HOST=0.0.0.0
JARVIS_PORT=443
JARVIS_TLS_CERT_FILE=/etc/jarvis/tls/fullchain.pem
JARVIS_TLS_KEY_FILE=/etc/jarvis/tls/privkey.pem
```

Dann neu starten:

```bash
sudo systemctl restart jarvis.service
```

Wenn du spaeter ein richtiges Zertifikat von einer CA oder von Let's Encrypt nutzt, trage einfach diese Pfade dort ein.

## Betrieb und Wartung

Admin-Daten sichern und pruefen:

```bash
./scripts/backup_admin_data.sh ./backups
./scripts/restore_admin_data.sh ./backups/<archive>.tar.gz
./scripts/check_admin_data_integrity.sh
```

`deploy_local.sh` now seeds integrity strictness flags (`JARVIS_INTEGRITY_FAIL_ON_ORPHANS`, `JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT`, `JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS`) to `0` in `/etc/jarvis/config.env` when missing, so behavior is explicit and opt-in.

`check_admin_data_integrity.sh` uses `JARVIS_ADMIN_SETTINGS_PATH`, can enforce `JARVIS_INTEGRITY_FAIL_ON_ORPHANS=1`, `JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT=1`, and `JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS=1`, and treats duplicate/malformed membership drift as a dedicated failure with exit code `8`.

Update und Rollback:

```bash
sudo ./scripts/update_local.sh
sudo ./scripts/rollback_local.sh
```

Vorbereitete Evidenz-Skripte:

```bash
python3 scripts/benchmark_local.py --base-url https://127.0.0.1 --iterations 25 --output ./benchmark_report.json
HEALTH_URL=https://127.0.0.1/health RESTART_COMMAND="systemctl restart jarvis.service" ./scripts/recovery_drill.sh ./recovery_drill_report.md
python3 scripts/token_lifecycle_drill.py --base-url https://localhost --passphrase "$JARVIS_PASSPHRASE" --admin-user-id usr-123456abcdef --audit-log-path /var/lib/jarvis/audit.log --insecure --report-path ./token_lifecycle_drill_report.md
bash scripts/admin_backup_restore_drill.sh ./admin_backup_restore_drill_report.md
```

## Tests

Schnell:

```bash
.venv/bin/python -m unittest
```

Vollstaendig mit frischer Umgebung:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest
cd frontend && npm run test:run && npm run build && cd ..
```

## Was fuer V1 noch offen ist

Lokal abgeschlossen:

- Backend-, Admin-, Auth- und Ops-Baseline
- Update-, Rollback-, Backup- und Integrity-Skripte
- Admin-UI
- GitHub-RAG-Baseline

Noch offen, aber nicht ehrlich lokal abschliessbar:

- One-command Deploy auf echtem Zielhost verifizieren
- Dev/Test/Prod-Trennung real pruefen
- Wakeword-, STT- und TTS-Qualitaet menschlich bewerten
- Performance auf schwacher Zielhardware messen
- Recovery-Drill auf echtem Service ausfuehren
- Manual Acceptance signieren

Diese Punkte sind jetzt sauber gesammelt unter:

- `docs/v1/planning/`
- `docs/v1/handoff/`
- `docs/v1/evidence/`

## V1-Dokumente

- `docs/v1/planning/ROADMAP_V1.md`
- `docs/v1/planning/EXECUTION_CHECKLIST_V1.md`
- `docs/v1/planning/ROLE_PERMISSION_MATRIX_V1.md`
- `docs/v1/planning/RELEASE_CRITERIA_V1.md`
- `docs/v1/planning/SPRINT_PLAN_V1.md`
- `docs/v1/handoff/MANUAL_ACCEPTANCE_V1.md`
- `docs/v1/handoff/USER_EXECUTION_RUNBOOK_V1.md`
- `docs/v1/trace.md`

## Troubleshooting

`status=203/EXEC` oder fehlende Python-Module:

```bash
sudo ./scripts/deploy_local.sh
```

Browser-Mikrofon fehlt:

- via HTTPS oder `localhost` oeffnen
- Mikrofon im Browser erlauben
- TLS-Dateien und `config.env` pruefen

Proxmox `401` oder `403`:

- Tokenformat pruefen
- Tokenrechte pruefen
- URL, Port und TLS-Reichweite pruefen
