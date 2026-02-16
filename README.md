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

> Nach Änderungen an `config.env` immer:
```bash
sudo systemctl restart jarvis.service
```

---

## 4) HTTPS, Web-UI und Voice

UI:
- `https://localhost:8000/`
- `https://localhost:8000/static/index.html`
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
- Nur aktiv, wenn Request mit `source: "voice"` an `/chat` gesendet wird
- Ohne Wakeword antwortet Jarvis: `Awaiting wake word...`
- Bei reiner Wakeword-Eingabe (`hey jarvis`) reagiert Jarvis direkt wie ein Assistant-Trigger (ready/status).
- In `static/index.html` gibt es einen **Wakeword Toggle** (Header), damit du es pro Gerät/UI ein- oder ausschalten kannst.

ENV-Konfiguration in `/etc/jarvis/config.env`:

```env
JARVIS_WAKEWORD_ENABLED=1
JARVIS_WAKEWORD_PHRASE=hey jarvis
```

Deaktivieren:

```env
JARVIS_WAKEWORD_ENABLED=0
```

Danach immer neu starten:

```bash
sudo systemctl restart jarvis.service
```

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

---

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
