# J.A.R.V.I.S (Iron Man Style) – Setup, Deployment, Betrieb

Jarvis ist ein lokaler Text- und Voice-Assistant mit Skill-Engine, Security-Policy, Proxmox-Integration, RAG-Quellen und optionalem Cloud-LLM-Fallback.

- **Stimme/Tonality**: Antworten sind auf **J.A.R.V.I.S von Iron Man** ausgerichtet (präzise, technisch, "On it." / "Understood.").
- **Skill-first**: Deterministische Skills werden vor Cloud-LLM genutzt.
- **Ziel**: Schnell reproduzierbar deployen, klar konfigurieren, alle Abhängigkeiten transparent machen.

---

## 1) Voraussetzungen / Abhängigkeiten

### Systemabhängigkeiten (Deploy-Host)
- `bash`
- `python3`
- `systemd` (`systemctl`)
- `rsync`
- `openssl`
- für SST: `node`, `npm` (werden über `scripts/install_sst.sh` bei Bedarf automatisch installiert)

### Python-Abhängigkeiten
Werden automatisch via `requirements.txt` installiert. `deploy_local.sh` installiert zusätzlich `uvicorn[standard]`.

---

## 2) One-shot Deployment (empfohlen)

Nach Clone im Repo:

```bash
sudo ./scripts/deploy_local.sh
```

Das Deployment ist **idempotent** und erledigt alles in einem Lauf:

1. Sync vom Repo nach `/opt/jarvis`
2. Venv unter `/opt/jarvis/.venv`
3. Python-Dependencies installieren
4. `/etc/jarvis/config.env` aus Template erstellen (falls nicht vorhanden)
5. TLS-Zertifikat erzeugen (self-signed, falls TLS-ENV gesetzt/ergänzt)
6. `systemd/jarvis.service` installieren
7. Service aktivieren/starten
8. Healthcheck ausführen
9. Sicherstellen, dass auch das Laufskript (`/opt/jarvis/scripts/run_jarvis.sh`) ausführbar ist
10. Admin-Store-Defaults in `config.env` ergänzen und Daten-Dateien unter `/var/lib/jarvis` mit gültigen Initialstrukturen vorbereiten

Danach prüfen:

```bash
systemctl status jarvis.service
curl -k https://localhost:8000/health
```

---

## 3) Konfigurationsdatei und API-Keys

Zentrale Datei:

- `/etc/jarvis/config.env`

Beispiel/Template:

- `config/jarvis.env.example`
- `config/env/dev.env.example`
- `config/env/test.env.example`
- `config/env/prod.env.example`

### Pflichtwerte
```env
JARVIS_PASSPHRASE=change-me
ALLOWED_TARGETS=local,web01
COOLDOWN_RESTART_SECONDS=60
COOLDOWN_CRITICAL_SECONDS=90
```

### API-Keys – wo eintragen?
Alle Keys in `/etc/jarvis/config.env`:

#### Proxmox
```env
PROXMOX_BASE_URL=https://pve.example.local:8006
PROXMOX_API_TOKEN=root@pam!jarvis=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
```

#### OpenAI
```env
OPENAI_API_KEY=sk-...
```

#### Gemini
```env
GEMINI_API_KEY=...
```

#### Wiki.js (RAG)
```env
WIKIJS_GRAPHQL_URL=https://wiki.example.local/graphql
WIKIJS_API_KEY=...
# Optional:
# WIKIJS_GRAPHQL_QUERY=query { pages { list(orderBy: TITLE) { title path description } } }
```

#### GitHub (RAG)
```env
GITHUB_REPO=owner/repo
GITHUB_BRANCH=main
GITHUB_PAT=ghp_...
```

#### TTS (lokale Stimme)
```env
PIPER_BIN=/usr/local/bin/piper
PIPER_MODEL=/opt/models/en_US-amy-medium.onnx
```

#### Persisted admin runtime defaults
```env
JARVIS_ADMIN_SETTINGS_PATH=/var/lib/jarvis/admin_settings.json
```

> Nach Änderungen an `config.env` immer:
```bash
sudo systemctl restart jarvis.service
```

---

## 4) HTTPS, Web-UI und Voice

UI:
- `https://localhost:8000/` (öffnet direkt die Chat-Seite)
- `https://localhost:8000/static/index.html`
- `https://localhost:8000/static/admin.html`
- `https://localhost:8000/static/orb.html`

Für Browser-Mikrofon ist ein **sicherer Kontext** nötig (`https://...` oder localhost).

Deploy ergänzt standardmäßig TLS-Variablen und erzeugt bei Bedarf Zertifikate unter:
- `/etc/jarvis/tls/fullchain.pem`
- `/etc/jarvis/tls/privkey.pem`

---

## 5) SST (essenziell) – Nutzung & Installation

SST ist in diesem Repo nicht als IaC-Projekt verdrahtet, aber als Tooling explizit unterstützt.

### Installation
```bash
sudo ./scripts/install_sst.sh
```

Das Skript:
- prüft ob `sst` bereits vorhanden ist
- installiert bei Bedarf **Node.js + npm** automatisch (apt-get auf Ubuntu/Debian)
- installiert anschließend SST global via `npm install -g sst`

### Verifikation
```bash
sst --version
```

### Nutzung (Basis)
```bash
sst init
sst dev
sst deploy
```

> `deploy_local.sh` kann SST inklusive Node/npm automatisch installieren: `sudo INSTALL_SST=1 ./scripts/deploy_local.sh`.

---

## 6) Skills, Domänenlogik und sinnvolle Antworten

### Wichtige Skills
- `help`
- `skills`
- `status jarvis`
- `diagnose jarvis`
- `config show`
- `proxmox health`
- `pve vm status <host_id> <node> <vmid>`
- `pve lxc status <host_id> <node> <vmid>`
- `service status <target> <service>`
- `service restart <target> <service>`

### Verbessertes Verhalten
- Bei Proxmox-Fragen liefert Jarvis gezielte Proxmox-Antworten/Hints.
- Wakeword-Handling für Voice-Requests ist konfigurierbar.
- Neue Proxmox-Status-Skills (VM/LXC) ergänzt.
- Learning-Memory ist stabilisiert: Jarvis generalisiert Antworten erst nach wiederholter Bestätigung (Confidence), um Fehl-Lernen zu vermeiden.


---

## 6b) Iron-Man Voice (natürlicher, weniger robotisch)

Für weniger "robotisch" klingende TTS-Antworten:

1. Nutze ein hochwertiges Piper-Modell (Studio/HiFi-ähnliche Stimmen, z. B. vits-medium/high).
2. Tune die Parameter in `config.env`:

```env
PIPER_LENGTH_SCALE=1.12
PIPER_NOISE_SCALE=0.55
PIPER_NOISE_W=0.75
```

3. Jarvis normalisiert TTS-Text jetzt automatisch für natürlichere Aussprache:
   - Kommandos wie `status jarvis` werden als natürliche Antwort gesprochen.
   - Fachbegriffe wie `PVE`, `VMID`, `API` werden aussprachefreundlich aufbereitet.

Hinweis: Die exakte "Filmstimme" von Iron Man ist urheberrechtlich geschützt. Technisch am nächsten kommst du mit einer tiefen, klaren englischen TTS-Stimme + Piper-Tuning.

---

## 7) Wakeword ("Hey Jarvis")

Für Voice-Requests kann ein echtes Wakeword erzwungen werden.

- Standard-Wakeword: `hey jarvis`
- **Standardmäßig in der Chat-UI deaktiviert** (privacy-first).
- Wenn in `index.html` aktiviert, lauscht der Browser im Hintergrund per Web Speech API kontinuierlich auf `hey jarvis` (Siri-ähnlicher Trigger).
- Wird `hey jarvis` erkannt, reagiert Jarvis automatisch; bei `hey jarvis <befehl>` wird der Befehl direkt verarbeitet.
- Ohne Wakeword antwortet Jarvis im Voice-Source-Flow: `Awaiting wake word...`
- In `static/index.html` gibt es dafür den **Wakeword Toggle** (Header).
- Sichtbares Feedback ist eingebaut: `wake off` / `wake on` / `wake heard` zeigt direkt an, ob das Wakeword erkannt wurde.
- Gleiches Prinzip im Orb (`static/orb.html`): bei aktivem Toggle hört Orb im Hintergrund zu und antwortet per Stimme automatisch.


UI-Hinweis:
- Chat-Liste unterstützt jetzt Löschen pro Chat: beim Hover erscheint ein Papierkorb-Symbol.
- Wakeword-Toggle ist lokal pro Gerät gespeichert (`localStorage`).

ENV-Konfiguration in `/etc/jarvis/config.env`:

```env
# Default (empfohlen): aus
JARVIS_WAKEWORD_ENABLED=0
JARVIS_WAKEWORD_PHRASE=hey jarvis
```

Aktivieren:

```env
JARVIS_WAKEWORD_ENABLED=1
```

Danach immer neu starten:

```bash
sudo systemctl restart jarvis.service
```


---

## 7b) RAG mit Wiki.js + GitHub (detailliert)

Jarvis kann Inhalte aus Wiki.js und einem GitHub-Repo lokal indexieren und dann in Antworten verwenden.

### Schritt 1: ENV setzen (`/etc/jarvis/config.env`)
```env
WIKIJS_GRAPHQL_URL=https://wiki.example.local/graphql
WIKIJS_API_KEY=<wikijs_api_key>
# Optional: eigene Query
# WIKIJS_GRAPHQL_QUERY=query { pages { list(orderBy: TITLE) { title path description } } }

GITHUB_REPO=owner/repo
GITHUB_BRANCH=main
GITHUB_PAT=<github_pat_optional>
```

### Schritt 2: RAG-Index aktualisieren
```bash
curl -X POST http://localhost:8000/rag/refresh
curl http://localhost:8000/rag/status
```

### Schritt 3: RAG direkt testen
```bash
curl "http://localhost:8000/rag/search?q=tasks"
curl "http://localhost:8000/rag/search?q=proxmox+vm+status"
```

### Schritt 4: Über `/chat` testen (natürliche Sprache)
Beispiele:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"Lies die Wiki Seite Tasks, was steht darin"}'

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"Zeige die aktuellen Tasks aus der Taskliste"}'

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"text":"Lies aus dem Github Repo die Doku zu deployment"}'
```

Erwartetes Verhalten:
- Jarvis erkennt die RAG-Absicht (Wiki/Repo/Taskliste),
- priorisiert passende Treffer,
- und antwortet mit Quelle + kurzem Inhaltsauszug oder Task-Liste.

### Smart-Auswertung (Budgetplan/Taskliste/Repo lesen)
Bei Formulierungen wie:
- `Lies den Budgetplan vor`
- `Liste die aktuellen Tasks aus der Taskliste`
- `Fasse das Repo-Setup zusammen`

nutzt Jarvis bevorzugt Cloud-KI, um aus den RAG-Treffern eine schlau strukturierte Antwort zu formen.

Wenn keine Cloud-KI konfiguriert ist (`OPENAI_API_KEY`/`GEMINI_API_KEY` fehlen), kommt eine klare Meldung:
- `Für diese intelligente Wiki/Repo-Auswertung brauche ich Cloud-KI ...`

### Wichtig: RAG ist jetzt bewusst weniger aggressiv
- Normale Fragen wie `wie ist das wetter heute` werden **nicht** mehr automatisch von Wiki/GitHub "gekapert".
- RAG greift nur bei klaren Wiki/GitHub/Taskliste-Signalen.
- Wenn Cloud-KI aktiv ist und keine klare RAG-Absicht vorliegt, bleibt der normale KI-Pfad aktiv.

---

## 8) Security-Modell

- **READ**: kein Token nötig
- **WRITE**: Token + Confirm `YES`
- **CRITICAL**: Token + Plan + Confirm `YES, proceed`
- Deny-by-default über `ALLOWED_TARGETS`
- Cooldowns gegen Action-Loops

---

## 9) Lokaler Start (ohne systemd)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JARVIS_PASSPHRASE=change-me
export ALLOWED_TARGETS=local
uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000
```

---

## 10) Tests

```bash
python -m unittest discover -s tests
```

Repo-local validation path used in this roadmap phase:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
```

---

### Prepared environment split templates

Use the following as the starting point for real environment separation:

- `config/env/dev.env.example`
- `config/env/test.env.example`
- `config/env/prod.env.example`

They intentionally use different ports, passphrases, and state directories so dev/test/prod do not share runtime data.


### Admin data backup/restore (V1 ops)

```bash
./scripts/backup_admin_data.sh ./backups
./scripts/restore_admin_data.sh ./backups/<archive>.tar.gz
./scripts/check_admin_data_integrity.sh
sudo ./scripts/update_local.sh
sudo ./scripts/rollback_local.sh
```

`check_admin_data_integrity.sh` validates admin-policy schema and semantics (known roles/permission keys, sourced from runtime constants when available), warns on orphan references by default (missing user/group links), validates `JARVIS_ADMIN_SETTINGS_PATH` structure, and flags duplicate/malformed memberships. Set `JARVIS_INTEGRITY_FAIL_ON_ORPHANS=1` to make orphan drift fail hard (useful in strict CI/deploy gates, including malformed membership records) and `JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS=1` to fail on duplicate/malformed membership drift specifically (exit code `8`). The script also reports admin lockout posture (`locked_out`/`at_risk`) from enabled-admin count; set `JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT=1` to fail when no enabled admin exists.

`deploy_local.sh` now seeds integrity strictness flags (`JARVIS_INTEGRITY_FAIL_ON_ORPHANS`, `JARVIS_INTEGRITY_FAIL_ON_ADMIN_LOCKOUT`, `JARVIS_INTEGRITY_FAIL_ON_DUPLICATE_MEMBERSHIPS`) to `0` in `/etc/jarvis/config.env` when missing, so behavior is explicit and opt-in. It also seeds `JARVIS_ADMIN_SETTINGS_PATH` and creates `admin_settings.json` with runtime defaults for token TTL, max active tokens, wakeword behavior, and STT provider.

`restore_admin_data.sh` only accepts expected admin-data filenames from the archive and will fail fast on unexpected entries.

`update_local.sh` snapshots the current `/opt/jarvis` release plus admin data backup, then runs `deploy_local.sh` against the current repo so update/rollback is deterministic. `rollback_local.sh` restores the last release snapshot (or an explicit snapshot path), restores the matching admin data archive when present, restarts `jarvis.service`, and reruns `check_admin_data_integrity.sh`.

Prepared but user-run evidence helpers:

```bash
python3 scripts/benchmark_local.py --base-url http://127.0.0.1:8000 --iterations 25 --output ./benchmark_report.json
HEALTH_URL=http://127.0.0.1:8000/health RESTART_COMMAND="systemctl restart jarvis.service" ./scripts/recovery_drill.sh ./recovery_drill_report.md
```

Those scripts prepare the remaining performance/recovery evidence collection, but they still must be executed on the real target environment to close the checklist honestly.

Backup/restore ops evidence can be captured safely against a probe copy of the current admin stores with:

```bash
bash scripts/admin_backup_restore_drill.sh ./admin_backup_restore_drill_report.md
```

The drill snapshots the currently configured admin data files, runs backup and restore against a temporary probe workspace, verifies the restored files match the original snapshot byte-for-byte, and finishes with `check_admin_data_integrity.sh`. Live admin data is read as seed input but is not mutated by the drill.

Admin API endpoints under `/admin/*` require:
- `Authorization: Bearer <unlock_token>`
- `X-Jarvis-User-Id: <user_id>` for an enabled user with role `admin`
- `X-Jarvis-Role: admin` (must match stored role)

The browser admin console is available at `/static/admin.html` and covers:
- users
- groups and assignments
- permissions and effective-permission lookup
- action logs
- persisted settings / usage limits

For the remaining real-environment execution steps, use `USER_EXECUTION_RUNBOOK_V1.md`.

Token lifecycle ops evidence can be captured against a live instance with:

```bash
python3 scripts/token_lifecycle_drill.py \
  --base-url https://localhost:8000 \
  --passphrase "$JARVIS_PASSPHRASE" \
  --admin-user-id usr-123456abcdef \
  --audit-log-path /var/lib/jarvis/audit.log \
  --insecure \
  --report-path ./token_lifecycle_drill_report.md
```

For first-run systems with no users yet, omit `--admin-user-id` and the drill will bootstrap an enabled admin via `POST /admin/users`. To validate expiry handling as evidence, run the service with a short token TTL (for example `JARVIS_TOKEN_TTL_MIN=1`) and add `--expiry-wait-seconds 65`; the drill then verifies expired-token denial plus the matching `unlock_revoke_denied` audit event.

Usernames in the admin user store are unique (case-insensitive), group names are unique (case-insensitive), memberships reject duplicates, user roles are validated against the V1 role set (`admin`, `standard_user`, `guest_restricted`, `service_system`), and permission sets reject unknown permission keys.

Audit APIs validate query bounds: `/admin/audit/events` requires `limit` between 1 and 500, and both `/admin/audit/events` and `/admin/audit/counts` require `since_ts <= until_ts` when both are provided.

Deleting users/groups performs cleanup of related memberships and direct permission sets to avoid orphaned admin-policy data.
`/admin/status/summary` now also reports orphan diagnostics (memberships or permission sets that reference missing users/groups).
`/admin/status/summary` includes `enabled_admins`, `disabled_admins`, `admin_lockout_risk`, and `admin_lockout_state` (`ok|at_risk|locked_out`) to quickly surface admin-access fragility.

Safety guard: deleting the last enabled admin user is blocked to prevent administrative lockout.
Safety guard: disabling the last enabled admin user is also blocked.
Safety guard: changing the last enabled admin's role away from `admin` is blocked.

First-run bootstrap: when the user store has no users yet, only `POST /admin/users` accepts `X-Jarvis-Role: admin` + active bearer token without `X-Jarvis-User-Id` so an initial **enabled admin** can be created.

## 11) Troubleshooting (kurz)

### `status=203/EXEC`
Deploy neu ausführen:
```bash
sudo ./scripts/deploy_local.sh
```

### `No module named uvicorn`
Deploy neu ausführen (venv + pip + uvicorn werden gesetzt):
```bash
sudo ./scripts/deploy_local.sh
```

### Mic-Fehler (`navigator.mediaDevices is undefined`)
- mit HTTPS öffnen
- Browser-Mikrofon erlauben
- Zertifikat/TLS-ENV prüfen

### Proxmox 401/403
- Tokenformat prüfen: `user@realm!tokenid=tokensecret`
- Rechte des Tokens prüfen
- URL/Port/TLS Reachability prüfen

---

## V1 Planning Docs

- `ROADMAP_V1.md` – phased roadmap and timeline to August launch.
- `EXECUTION_CHECKLIST_V1.md` – operational step-by-step tracker for delivery.
- `ROLE_PERMISSION_MATRIX_V1.md` – V1 RBAC roles, permissions, and enforcement rules.
- `RELEASE_CRITERIA_V1.md` – objective pass/fail launch criteria and required evidence.
- `SPRINT_PLAN_V1.md` – detailed sprint execution plan with estimates, dependencies, and exit criteria.
