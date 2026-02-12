# jarvis
Jarvis ist ein Text- und Voice-Assistant mit Skill-Engine, Security-Policy und optionalem Cloud-KI-Fallback.

## Quick Deploy (Ubuntu VM, idempotent)
Nach einem Repo-Clone reicht:
```bash
sudo ./scripts/deploy_local.sh
```

Das Script erledigt idempotent:
- Sync nach `/opt/jarvis` via `rsync -a --delete`
- venv unter `/opt/jarvis/.venv` (falls nicht vorhanden)
- `pip install -r requirements.txt` + `uvicorn[standard]`
- `/etc/jarvis/config.env` aus `config/jarvis.env.example` (falls nicht vorhanden, danach `chmod 600`)
- Installation/Aktualisierung von `jarvis.service`
- `systemctl daemon-reload && systemctl enable --now jarvis.service`
- Ausgabe von Service-Status + Health-URL

Danach:
```bash
systemctl status jarvis.service
curl http://localhost:8000/health
```

## HTML-UI öffnen
Nach dem Start erreichst du die UI unter:
- `http://localhost:8000/` (standardmäßig Orb-UI)
- `http://localhost:8000/static/orb.html`
- `http://localhost:8000/static/index.html`

Für Remote-Mic (Browser-API) ist ein **sicherer Kontext** nötig (`https://...`). Jarvis unterstützt optional TLS direkt via ENV (`JARVIS_TLS_CERT_FILE`, `JARVIS_TLS_KEY_FILE`) im Service-Startscript.
Beim Deploy (`scripts/deploy_local.sh`) werden bei gesetzten TLS-ENV Variablen fehlende Zertifikate **idempotent als self-signed** unter den konfigurierten Pfaden erzeugt und danach direkt per `curl -k https://localhost:8000/health` geprüft.

## Troubleshooting
- **CHDIR / WorkingDirectory Fehler**
  - Symptom in Journal: `Failed at step CHDIR`.
  - Ursache: falsches Arbeitsverzeichnis.
  - Fix: Service verwendet `WorkingDirectory=/opt/jarvis`; erneut deployen:
    ```bash
    sudo ./scripts/deploy_local.sh
    ```

- **`No module named uvicorn`**
  - Ursache: venv/dependencies fehlen oder falscher Python-Interpreter.
  - Fix: Deploy-Script installiert `uvicorn[standard]` in `/opt/jarvis/.venv` und startet den Service mit diesem Binary:
    ```bash
    /opt/jarvis/.venv/bin/uvicorn
    ```

- **`status=203/EXEC` bei `jarvis.service`**
  - Ursache: `ExecStart` zeigt auf einen nicht existierenden/nicht ausführbaren Pfad (typisch: fehlendes venv oder fehlendes `uvicorn`).
  - Fix:
    ```bash
    sudo ./scripts/deploy_local.sh
    ```
    Das Deploy-Script prüft explizit, dass `/opt/jarvis/.venv/bin/uvicorn` vorhanden und ausführbar ist.

- **Service läuft, Seiten laden nicht**
  - Logs prüfen:
    ```bash
    sudo journalctl -u jarvis.service -n 200 --no-pager
    ```
  - Lokal testen:
    ```bash
    curl -i http://localhost:8000/health
    curl -i http://localhost:8000/
    ```


- **Mic error: `navigator.mediaDevices is undefined`**
  - Ursache: Browser-Kontext ist nicht sicher (kein HTTPS/localhost), Berechtigung blockiert oder Browser hat kein Microphone-API.
  - Jarvis-Änderung: Die Web-UI leitet Remote-HTTP automatisch auf `https://` um (localhost bleibt bei http erlaubt).
  - Fix-Checkliste:
    1. TLS in `/etc/jarvis/config.env` setzen:
       ```env
       JARVIS_TLS_CERT_FILE=/etc/jarvis/tls/fullchain.pem
       JARVIS_TLS_KEY_FILE=/etc/jarvis/tls/privkey.pem
       ```
    2. Service neu starten: `sudo systemctl restart jarvis.service`
    3. UI über `https://<host>:8000` öffnen.
    4. Browser-Mikrofonrechte erlauben (Site Settings → Microphone → Allow).
    5. In Chrome/Edge prüfen: `chrome://settings/content/microphone` und korrektes Input-Device wählen.
    6. Bei Reverse-Proxy HTTPS korrekt terminieren und `X-Forwarded-Proto=https` setzen.
    7. Gegenprobe: im gleichen Browser `navigator.mediaDevices` in der DevTools-Konsole prüfen.

## Orb-UI (Voice)
Die Orb-Oberfläche (`/static/orb.html`) nutzt STT + TTS:
- Spracheingabe → `/stt`
- Antwort → `/chat` → Audioausgabe über `/tts`
Wenn `/tts` nicht erreichbar ist, nutzt die Orb-UI den Browser-Voice-Fallback (SpeechSynthesis).

Damit lokale Sprachausgabe funktioniert, müssen gesetzt sein:
- `PIPER_BIN` (Pfad zum piper Binary)
- `PIPER_MODEL` (Pfad zum Voice-Model)

## Konfiguration (ohne Secrets im Repo)
Verwende `/etc/jarvis/config.env` (Template: `config/jarvis.env.example`).
- `JARVIS_PASSPHRASE`
- `ALLOWED_TARGETS` (deny-by-default für write/critical)
- `COOLDOWN_RESTART_SECONDS`, `COOLDOWN_CRITICAL_SECONDS`
- Optional: `PROXMOX_BASE_URL`, `PROXMOX_API_TOKEN`
- Optional: `OPENAI_API_KEY`, `GEMINI_API_KEY`


## Proxmox API-Key hinzufügen (Schritt-für-Schritt)
Wenn du jetzt deinen Proxmox API-Token hast, kannst du ihn auf zwei Arten einbinden:

### Variante A (einfach): direkt in `/etc/jarvis/config.env`
1. Datei öffnen:
   ```bash
   sudo nano /etc/jarvis/config.env
   ```
2. Diese Werte setzen (Beispiel):
   ```env
   PROXMOX_BASE_URL=https://pve.example.local:8006
   PROXMOX_API_TOKEN=root@pam!jarvis=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ```
   Token-Format ist **genau**:
   `user@realm!tokenid=tokensecret`
3. Service neu starten:
   ```bash
   sudo systemctl restart jarvis.service
   ```
4. Prüfen:
   ```bash
   curl http://localhost:8000/health
   curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"proxmox health"}'
   ```

### Variante B (empfohlen für mehrere Proxmox-Hosts): über API speichern
Damit legst du einen Host in der internen Host-Liste an (`proxmox_hosts.json`).

1. Token holen (Unlock):
   ```bash
   TOKEN=$(curl -s -X POST http://localhost:8000/unlock      -H "Content-Type: application/json"      -d '{"passphrase":"change-me"}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["token"])')
   ```
2. Host hinzufügen:
   ```bash
   curl -X POST http://localhost:8000/proxmox/hosts      -H "Authorization: Bearer $TOKEN"      -H "Content-Type: application/json"      -d '{
       "name":"home-pve",
       "base_url":"https://pve.example.local:8006",
       "api_token":"root@pam!jarvis=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
       "verify_tls":true
     }'
   ```
3. Hosts anzeigen:
   ```bash
   curl http://localhost:8000/proxmox/hosts
   ```

### Häufige Fehler
- `401`/`403` von Proxmox: Token falsch oder Rechte fehlen.
- `Proxmox unreachable`: URL/Port/TLS nicht erreichbar.
- Self-signed Zertifikat: testweise `"verify_tls": false` setzen (nur intern/temporär).
- In Proxmox muss der Token passende Berechtigungen auf Node/VM/LXC haben.

## Learning / Memory (deterministisch)
Jarvis kann Nutzungsdaten lokal speichern (JSON, kein Modell-Finetuning):
- `JARVIS_MEMORY_PATH` (Default: `/var/lib/jarvis/memory.json`)
- Merkt sich Query-Statistiken, Feedback und Alias-Korrekturen
- Nach Responses liefert `data.feedback` eine Feedback-ID

Feedback senden:
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"feedback <id> ok"}'
```
oder bei falscher Zuordnung:
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"feedback <id> bad correct: proxmox health"}'
```

Wenn eine unbeantwortete Anfrage häufiger vorkommt, wird in `data.skill_suggestion` vorgeschlagen, einen neuen Skill anzulegen.


### Selbstständiges Lernen (ohne expliziten Befehl)
Jarvis speichert erfolgreiche Antworten jetzt zusätzlich als lokale Muster und kann ähnliche Fragen später aus der Memory beantworten:
- Bei bekannten/erfolgreichen Antworten werden lokale Reply-Muster in `learned_replies` gespeichert.
- Bei ähnlicher Formulierung nutzt Jarvis diese Antwort direkt (`route: learned_memory`).
- Bei mittlerer Unsicherheit fragt Jarvis gezielt nach (`Need clarification`).

Beispiel:
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"how are you"}'
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"how are u today"}'
```

### Learning-Kommandos (direkt im Chat)
Jarvis kann jetzt explizit Memory-Einträge setzen und anzeigen:
- `remember node <name> <value>`
- `remember vmid <name> <value>`
- `remember default <key> <value>`
- `memory show`

Beispiele:
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"remember node pve1 10.0.0.10"}'
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"memory show"}'
```

### Cloud-Ausfall / Offline-Assistant
Wenn OpenAI/Gemini gerade nicht erreichbar ist oder API-Fehler liefert, gibt Jarvis jetzt **keinen rohen Upstream-Fehler** mehr zurück.
Stattdessen antwortet er als Assistant mit kontextbasierten Next-Steps (z. B. für "web gui down", "deploy branch", "proxmox").

### Lern- und Fallback-Tests
```bash
python -m unittest discover -s tests
```
Enthalten sind u. a. Tests für:
- Feedback-Loop + Alias-Lernen
- wiederholte unbekannte Anfragen → Skill-Suggestion
- explizite Memory-Kommandos (`remember`, `memory show`)
- Cloud-Fehler → kontextbasierte Offline-Assistant-Antwort

## Security-Model (Kurzfassung)
- read: kein Token nötig.
- write: Token + Confirm (`YES`).
- critical: Token + Plan + Confirm (`YES, proceed`).
- Targets müssen in `ALLOWED_TARGETS` stehen (deny-by-default).
- Cooldowns verhindern Restart-Loops.

## Build: Bootbares ISO/Disk-Image
Reproduzierbarer Build via `mkosi`:
```bash
scripts/build-image.sh
```

Beim Boot sorgt `first-boot-wizard` automatisch für Grundkonfiguration und ruft anschließend `scripts/deploy_local.sh` auf. Dadurch werden Dependencies installiert und `jarvis.service` automatisch aktiviert/gestartet.

## Legacy Installer
`install_service.sh` bleibt als Wrapper erhalten und ruft intern `deploy_local.sh` auf:
```bash
sudo ./scripts/install_service.sh
```

## Tests
```bash
python -m unittest discover -s tests
```

## Lokales Starten (MVP)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JARVIS_PASSPHRASE=change-me
export ALLOWED_TARGETS=local
uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000
```

Beispiele:
```bash
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"status jarvis"}'
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" -d '{"text":"skills --verbose"}'
```

## Konfiguration (ohne Secrets im Repo)
Verwende ENV oder eine Datei wie `/etc/jarvis/config.env` (siehe `config/jarvis.env.example`).
- `JARVIS_PASSPHRASE`
- `ALLOWED_TARGETS` (deny-by-default für write/critical)
- `COOLDOWN_RESTART_SECONDS`, `COOLDOWN_CRITICAL_SECONDS`
- Optional: `PROXMOX_BASE_URL`, `PROXMOX_API_TOKEN`
- Optional: `OPENAI_API_KEY`, `GEMINI_API_KEY`



## RAG mit Wiki.js + GitHub
Jarvis unterstützt vorbereitete RAG-Quellen für Wiki.js und GitHub (PAT-ready):

### 1) ENV konfigurieren
```env
WIKIJS_GRAPHQL_URL=https://wiki.example.local/graphql
WIKIJS_API_KEY=<wikijs_api_key>
# Optional: eigene Query, sonst Default
# WIKIJS_GRAPHQL_QUERY=query { pages { list(orderBy: TITLE) { title path description } } }

GITHUB_REPO=owner/repo
GITHUB_BRANCH=main
# Für public optional, für private später erforderlich
GITHUB_PAT=<github_pat>
```

### 2) RAG-Index aktualisieren
```bash
curl -X POST http://localhost:8000/rag/refresh
curl "http://localhost:8000/rag/status"
```

### 3) Suche testen
```bash
curl "http://localhost:8000/rag/search?q=proxmox+vm+status"
```

Hinweis:
- Wiki.js wird per GraphQL mit Bearer-Token angebunden.
- GitHub ist für public Repos ohne Token nutzbar; für private Repos `GITHUB_PAT` setzen.

## Serverseitige Chat-History (F5-safe)
Chats werden jetzt serverseitig gespeichert (`JARVIS_CHAT_HISTORY_PATH`).
- F5 verliert den Chat nicht mehr.
- In der Web-UI gibt es links eine Chat-Liste mit alten Chats.
- Mit **New** startest du einen neuen Chat.
- Beim Wechsel von Chat → Orb bleibt der aktive Chat-Kontext erhalten.

## Web-UI testen (Chat + Skills)
1. Backend starten:
```bash
uvicorn jarvisappv4:app --host 0.0.0.0 --port 8000
```
2. Browser öffnen: `http://localhost:8000/static/index.html`
3. In der Chat-UI testen:
   - links **New** klicken (neuen Chat starten)
   - `skills` oder auf den **Skills**-Button klicken
   - `status jarvis`
   - Proxmox-Status: `pve vm status <host_id> <node> <vmid>`
   - Seite mit F5 neu laden (Chat muss erhalten bleiben)
   - auf **ORB** wechseln und weiter fragen (gleicher aktiver Chat-Kontext)
4. Optional Lernverhalten prüfen:
   - `how are you`
   - danach ähnliche Formulierung wie `how are u today`
   - anschließend `memory show` prüfen

## Security-Model (Kurzfassung)
- read: kein Token nötig.
- write: Token + Confirm (`YES`).
- critical: Token + Plan + Confirm (`YES, proceed`).
- Targets müssen in `ALLOWED_TARGETS` stehen (deny-by-default).
- Cooldowns verhindern Restart-Loops.

## Build: Bootbares ISO/Disk-Image
Reproduzierbarer Build via `mkosi`:
```bash
scripts/build-image.sh
```
Output unter `build-output/`. Das Image startet nach Boot automatisch (`systemd/jarvis.service`).

## First-Boot Wizard
Beim ersten Boot schreibt `first-boot-wizard` eine minimale Konfiguration:
- `/etc/jarvis/config.env`
- Statusdatei: `/var/lib/jarvis/first-boot.done`

## Update-Strategie
Empfohlen: neues Image bauen und per A/B-Update ausrollen. Im MVP werden keine automatischen Updates erzwungen.

## Requirements-Trace
Siehe `trace.md` für R1–R25 Status.

## Tests
```bash
python -m unittest discover -s tests
```


## Kiosk-Mode (Boot direkt in WEB-UI)
Das Image konfiguriert beim ersten Boot automatisch einen lokalen `jarvis`-Benutzer im Kiosk-Betrieb:
- Auto-Login auf `tty1`
- Start von X/Openbox
- Chromium im Kiosk-Vollbild auf `http://localhost:8000/`

Dadurch kann das System auf SSD/USB geflasht und direkt auf einem anderen PC als Appliance genutzt werden (USB-Eingabegeräte wie Tastatur/Maus bleiben nutzbar).

Anpassung über `/etc/jarvis/config.env`:
- `KIOSK_URL` (default `http://localhost:8000/`)
- `LOCAL_LLM_ENABLED` (default `0`)
- `LOCAL_LLM_MODEL_DIR` (default `/var/lib/jarvis/local-ai/models`)
- `LOCAL_LLM_DEFAULT_MODEL` (default `future-local-model`)
