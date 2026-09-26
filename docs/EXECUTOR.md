# Executor & Sandbox-Dienst (Plan 4.2)

Der **Executor** ist die einzige Stelle mit Zugriff auf die Laufzeit. Der Agent
hält keine Schlüssel und redet nur über diesen Dienst. Standardmäßig ist er
**deaktiviert**.

## Architektur

```
Agent ──(Agent-Token)──> jarvis-executor ──> docker-socket-proxy ──> Docker
                              │  (nur Container/Image/Netz/Exec)
                              └── Zonen-Policy (config/zones.json) + Freigabe-Kern
```

- `services/executor/app.py` — FastAPI-Dienst.
- `jarvis/executor.py` — Policy/Quoten/Isolation.
- `jarvis/docker_runtime.py` — spricht mit dem **Socket-Proxy**, nie mit `docker.sock`.
- `deploy/sandbox/compose.yml` — Proxy + Executor.

## Scharfschalten (auf der Jarvis-VM)

```bash
cd /pfad/zum/jarvis
JARVIS_EXECUTOR_ENABLED=1 \
JARVIS_AGENT_REQUEST_TOKEN="$(grep -E '^JARVIS_AGENT_REQUEST_TOKEN=' /home/media/jarvis.env | cut -d= -f2-)" \
  docker compose -f deploy/sandbox/compose.yml up -d --build
```

Danach ist der Dienst unter `jarvis-executor:8120` aus dem Agenten-Netz
(`agent-isolated`) erreichbar; er veröffentlicht **keinen** Host-Port.


## Aufruf aus Jarvis (Client + Tools)

Jarvis ruft den Executor ueber `jarvis/executor_client.py` an (Token-geschuetzt).
Die Chat-Tools `sandbox_create`, `sandbox_exec`, `sandbox_destroy` (T1, ueber den
Freigabe-Kern) nutzen ihn. Aktivierung:

```bash
export JARVIS_EXECUTOR_URL="http://jarvis-executor:8120"
export JARVIS_AGENT_REQUEST_TOKEN="..."   # bereits gesetzt
```

Der Executor haengt dafuer zusaetzlich im Netz `runpod-internal` (wie `jarvis-app`).
Ohne `JARVIS_EXECUTOR_URL` melden die Tools freundlich "sandbox zone not configured".

## Endpunkte (Agent-Token: `X-Jarvis-Agent-Request-Token`)

| Methode | Pfad | Wirkung |
|---|---|---|
| GET | `/health` | Status (kein Token) |
| GET | `/sandboxes` | Sandboxen auflisten |
| POST | `/sandboxes` | `{image, command}` → Sandbox starten (T1) |
| DELETE | `/sandboxes/{name}` | Sandbox löschen (T1) |
| POST | `/sandboxes/{name}/exec` | Befehl in einer Sandbox (T1) |

## Was der Proxy **nicht** kann

Nur `CONTAINERS`, `IMAGES`, `NETWORKS`, `POST`, `DELETE`, `EXEC` sind erlaubt.
**Aus**: Build, Swarm, Volumes, Auth, System/Info. Zusammen mit der Zonen-Policy
sind `runpod-controller` und `searxng` doppelt gesperrt (Proxy-Sicht + Policy).

## Isolation der Sandboxen

Jede Sandbox (Netz `jarvis-sandbox`):
- `cap_drop: ALL`, `no-new-privileges`, `read_only`-Root, `tmpfs /tmp`
- Limits: `cpus`, `mem_limit`, `pids_limit`, max. Laufzeit
- nur erlaubte Images (`allowed_images` in `config/zones.json`)
- Quoten mit Host-Reserve (`host_reserve`)

## Egress

Empfehlung Plan: Egress nur über den **Allowlist-Proxy** (`allowlist-proxy`,
duales Netz `agent-isolated` + Internet). Der Executor kann Sandboxen das
Proxy-Env mitgeben; das harte Anbinden (Sandbox-Netz `internal: true` + Proxy
dual-homed) ist der nächste Härtungsschritt und in `docs/ZONES.md` beschrieben.

## Reproduzierbar auf einer anderen Maschine

1. Repo klonen; `deploy/` + `deploy/sandbox/` mitnehmen.
2. `docker compose -f deploy/sandbox/compose.yml up -d --build` (Basis-Images
   werden gepullt; `tecnativa/docker-socket-proxy` ggf. auf einen Digest pinnen).
3. `config/zones.json` prüfen (kritische Dienste, Quoten, Backend).
4. Später `backend: proxmox`/`k8s`: nur `jarvis/docker_runtime.py` durch einen
   passenden Runtime-Adapter ersetzen — Policy und Dienst bleiben gleich.

> Hinweis: Container sind keine VM-Grenze. Für stärkere Isolation `userns-remap`,
> seccomp und (später) eine echte VM-Zone nutzen.
