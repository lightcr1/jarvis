# Deployment & Reproduzierbarkeit

Diese Seite beschreibt, **welche Dienste** laufen, **wie sie verbunden** sind und
**wie man alles auf einer anderen Maschine** nachbaut. Maßgeblich sind immer die
Compose-Dateien; hier steht die Übersicht.

## Projekte (Compose)

| Projekt | Datei | Dienste |
|---|---|---|
| `deploy` | `deploy/docker-compose.yml` + `deploy/docker-compose.override.yml` | `jarvis` (App), `searxng` |
| `openhands` | `deploy/openhands/compose.yml` | `agent-canvas`, `canvas-edge`, `inference-gateway`, `allowlist-proxy` |
| `runpod` | `/home/media/runpod/docker-compose.yml` | `controller`, `open-webui`, `reverse-proxy` |
| `jarvis-sandbox` | `deploy/sandbox/compose.yml` | `docker-socket-proxy`, `jarvis-executor` |

## Netz-Topologie

```
                    ┌──────────────────────── runpod_default (Internet/NAT) ────────────────────────┐
                    │                                                                              │
  runpod: controller ─┐                     openhands: inference-gateway ── agent-isolated (internal)
  open-webui ─────────┤                        canvas-edge ───────────────┘        │
  reverse-proxy ──────┘                        allowlist-proxy ── dual-homed ───────┘
                                                  agent-canvas                      │
                                                                                    │
  deploy: jarvis ── runpod-internal ──┐                                             │
          searxng ── jarvis-search (internal) ── jarvis-search-egress (bridge)      │
                                                                                    │
  jarvis-sandbox: jarvis-executor ── executor-internal (internal) ── docker-socket-proxy ── /var/run/docker.sock
                       └── jarvis-sandbox (bridge) ── [Sandbox-Container]
```

- **`agent-isolated`** (`internal: true`): nur Agent ↔ Gateways/Proxy, **kein**
  direkter Internetzugang. Internet nur über `allowlist-proxy`.
- **`jarvis-search`** (`internal: true`): nur App ↔ SearXNG.
- **`executor-internal`** (`internal: true`): nur Executor ↔ Socket-Proxy.
- Der Executor hängt zusätzlich in `agent-isolated`, damit der Agent ihn als
  `jarvis-executor:8120` erreicht (kein Host-Port).
- **`jarvis-sandbox`**: Wegwerf-Container, `runpod-controller`/`searxng` gesperrt.

## Dienste im Detail

| Dienst | Image | Zweck | Netz(e) | Bemerkung |
|---|---|---|---|---|
| `jarvis` | `ghcr.io/lightcr1/jarvis-app:latest` | Backend/SPA, Chat, Admin | `runpod-internal`, `jarvis-search` | bind-mountet `config/autonomy.json` |
| `searxng` | `searxng/searxng@sha256:5286…` | interne Webrecherche (kein Brave-Token) | `jarvis-search`, `jarvis-search-egress` | `cap_drop ALL`, kein Host-Port |
| `agent-canvas` | `${OPENHANDS_IMAGE}` | OpenHands-Agent | `agent-isolated` | `read_only`, Limits |
| `canvas-edge` | `nginx:alpine@sha256:62ff…` | TLS/Proxy vor Canvas | `agent-isolated`, `runpod-internal` | |
| `inference-gateway` | `nginx:alpine@sha256:62ff…` | LLM-Gateway (`/agent/v1`, `/assistant/v1` …) | `agent-isolated`, `runpod-internal` | |
| `allowlist-proxy` | `allowlist-proxy:local` (build) | Egress nur auf Allowlist | `agent-isolated`, `runpod-internal` | `ALLOW_GITHUB=0` (Phase 6) |
| `controller` | build (`controller/`) | Pod-/Modell-Steuerung, Nutzung | `runpod_default` | TLS auf `:8443` |
| `open-webui` | `${OPEN_WEBUI_IMAGE}` | Chat-UI fürs Modell | `runpod_default` | |
| `jarvis-executor` | `jarvis-executor:local` (build) | Sandbox-Zone (siehe `docs/EXECUTOR.md`) | `executor-internal`, `jarvis-sandbox`, `agent-isolated` | **standardmäßig deaktiviert** |
| `docker-socket-proxy` | `tecnativa/docker-socket-proxy` | eingeschränkter Docker-Zugriff | `executor-internal` | nur Containers/Images/Networks/Exec |

Details zu Isolation und Quoten: [`docs/ZONES.md`](ZONES.md).
Executor aktivieren: [`docs/EXECUTOR.md`](EXECUTOR.md).
OpenHands/Agent: [`docs/OPENHANDS_SETUP.md`](OPENHANDS_SETUP.md).

## Env-Dateien (nicht ins Git!)

| Datei | Für |
|---|---|
| `/home/media/jarvis.env` | `jarvis`-App (Container) |
| `/home/media/runpod/.env` | `controller`, Runpod |
| `/home/media/jarvis-openhands/autonomy/autonomy-loop.env` | Autonomy-Loop |
| `deploy/.env` | Compose-Variablen (Images, Tokens) |

Vorlagen: `config/prod.env.example`, `config/autonomy-loop.example.env`.

## Reproduktion auf einer neuen Maschine

1. **Repo klonen** (Branch `main`) und `deploy/` mitnehmen.
2. **Docker + Compose** installieren (Docker ≥ 27).
3. **Netzwerke**: `runpod_default` als externes Netz anlegen
   (`docker network create runpod_default`), dann `deploy/`- und
   `openhands/`-Stacks starten; die internen Netze entstehen automatisch.
4. **Env setzen**: `config/prod.env.example` → `.env`, Tokens/Secrets eintragen
   (`JARVIS_AGENT_REQUEST_TOKEN`, `SEARXNG_SECRET`, `OPENHANDS_*`, `CONTROL_TOKEN`).
5. **Jarvis-App**: `docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml up -d`.
6. **SearXNG**: kommt aus dem Override (kein Host-Port, intern). Prüfen:
   `docker network inspect deploy_jarvis-search`.
7. **Executor/Sandbox (optional, siehe `docs/EXECUTOR.md`)**:
   `docker compose -f deploy/sandbox/compose.yml up -d --build`.
8. **Autonomy-Loop**: `scripts/agent/install_loop.sh` (Einzeldatei, Cron `*/2`).

## Health-Checks

| Dienst | Check |
|---|---|
| `jarvis` | `GET /health` (Host `:8100`) |
| `searxng` | intern `http://searxng:8080/` (nur App) |
| `controller` | `https://<host>:8443/api/model/ready` (mit `X-Control-Token`) |
| `jarvis-executor` | `GET /health` (intern `:8120`, nur Agent-Netz) |
| `allowlist-proxy` | `TCP 127.0.0.1:3128` im Container |

## Self-Deploy & verwaltete Zone (Plan 5.3 / 4.1)

Die **verwaltete Zone** umfasst alle Dienste **außer** `runpod-controller` und
`searxng` (siehe `config/zones.json`). Jarvis darf dort deployen/neustarten,
aber `jarvis.deploy` ist **T2** (nie ohne Freigabe).

- Logik: `jarvis/self_deploy.py` — `authorize_service` (kritische gesperrt) →
  `authorize_action("jarvis.deploy")` → Deploy-Befehl → Health-Check → bei
  Fehler **automatischer Rollback**.
- Befehle/URL per Env: `JARVIS_DEPLOY_COMMAND` (Default `bash scripts/update.sh`),
  `JARVIS_ROLLBACK_COMMAND` (Default `bash scripts/rollback.sh`),
  `JARVIS_HEALTH_URL` (Default `http://127.0.0.1:8100/health`).
- Besitzer-Auslöser: `POST /admin/autonomy/deploy` `{"service": "jarvis"}`
  (Owner-Session; der Klick ist die Freigabe). Der Agent braucht eine stehende
  Freigabe für `jarvis.deploy`.

### Containerisierter Self-Deploy (empfohlen für diese Maschine)

`scripts/update.sh` zielt auf die **systemd-Installation** `/opt/jarvis`. Für die
aktive Container-App `jarvis-app` diese Skripte **auf dem Host** nutzen — der
App-Container hat **keinen** Docker-Zugriff, daher laufen sie host-seitig (wie
der Autonomy-/Rollout-Loop per Cron). Die Skripte merken sich das vorherige
Image und stellen es beim Rollback wieder her:

```bash
export JARVIS_DEPLOY_COMMAND="bash scripts/agent/self_deploy.sh"
export JARVIS_ROLLBACK_COMMAND="bash scripts/agent/rollback_self.sh"
export JARVIS_HEALTH_URL="http://127.0.0.1:8100/health"
export SELF_DEPLOY_COMPOSE_FILES="deploy/docker-compose.yml deploy/docker-compose.override.yml"
export SELF_DEPLOY_SERVICE="jarvis"
export SELF_DEPLOY_IMAGE="ghcr.io/lightcr1/jarvis-app:latest"
export SELF_DEPLOY_BUILD="1"   # oder SELF_DEPLOY_PULL=1
```

Trockenlauf: `bash scripts/agent/self_deploy.sh --dry-run` (führt nichts aus).

### Automatisch per Cron (host-seitig, Marker-basiert)

Der Besitzer/Admin schreibt nur einen **Marker**; der Host-Loop führt den Deploy
mit Health-Check + Rollback aus (wie der Rollout-Loop):

```bash
mkdir -p /home/media/jarvis-openhands/autonomy
cp config/self-deploy.example.env /home/media/jarvis-openhands/autonomy/self-deploy.env
touch /home/media/jarvis-openhands/autonomy/self-deploy-requested   # Deploy anfordern
```

Cron-Eintrag (Beispiel):
```cron
*/5 * * * * flock -n /tmp/jarvis-selfdeploy.lock bash /home/media/jarvis-deploy/scripts/agent/self_deploy_loop.sh >> /home/media/jarvis-openhands/autonomy/self-deploy-loop.log 2>&1
```

Sofort testen: `bash scripts/agent/self_deploy_loop.sh --force` (bzw. `--dry-run`
im Deploy-Skript).

## Rollback

- Jarvis-App: `scripts/rollback.sh` (siehe Repo) bzw. Compose-Image-Tag zurück.
- Controller: `runpod-controller:rollback-*`-Image.
- Loop: `scripts/agent/install_loop.sh` mit älterem Stand neu installieren.
