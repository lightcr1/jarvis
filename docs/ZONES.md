# Zonen & Sandbox (Plan 4.1)

J.A.R.V.I.S. darf nur in klar abgegrenzten **Zonen** handeln. Die Policy steht in
`config/zones.json` und ist **backend-agnostisch**: lokal laufen Sandboxen als
Docker-Container, dieselbe Policy kann später auf echte VMs (Proxmox) oder
Kubernetes zeigen — dafür nur `backend` ändern.

## Die Zonen

| Zone | Was Jarvis darf | Umsetzung lokal |
|---|---|---|
| **Sandbox** | Wegwerf-Container erstellen, Software installieren, ausführen, löschen | Docker-Netz `jarvis-sandbox`, Egress über den Allowlist-Proxy |
| **Verwaltet** | Bestehende Dienste ändern (Neustart, Deploy) — **nur mit Freigabe (T2)** | Docker auf dem Host, außer kritische Dienste |
| **Unmanaged / Kritisch** | **kein** Zugriff, nur lesen | `runpod-controller`, `searxng` |

**Kritische Dienste** (`critical_services`): `runpod-controller`, `searxng`.
Agent und Executor dürfen sie weder ändern noch umgehen.

## Quoten (Host behält Luft)

`host_reserve` hält für das System reserviert, der Rest wird auf die Sandboxen
verteilt:

- Host-Reserve: **1 CPU / 4 GB RAM**
- je Sandbox: **1 CPU / 2 GB RAM / 25 GB Disk / max. 120 min**
- max. **4 Sandboxen** gleichzeitig

Auf einem 4-CPU-/16-GB-Host passen damit **3** Sandboxen parallel
(`available_sandbox_slots`), Storage ist reichlich vorhanden und begrenzt nicht.
Braucht Jarvis mehr, fragt er per **T3** nach (z. B. über `pod.start`).

## Isolationsschritte der Sandbox

Die Policy legt die **Grenzen** fest; der Executor setzt sie beim Erstellen durch:

- eigenes Docker-Netz **`jarvis-sandbox` mit `internal: true`** → **kein** direkter
  Internet-/LAN-Zugang; `allow_lan: false` ist Pflicht (der Executor lehnt sonst ab)
- **Egress nur über den Allowlist-Proxy**: der Executor setzt `HTTP(S)_PROXY`;
  der Proxy (`allowlist-proxy`) ist dual-homed und der einzige Weg nach draußen
- `cap_drop: ALL`, `no-new-privileges`, `read_only`-Root + `tmpfs`
- harte Limits (`cpus`, `mem_limit`, `pids_limit`), max. Laufzeit + Aufräumen
- Zugriff auf **nur** die deklarierten Netzziele
- vor Aktionen in der **verwalteten** Zone: Snapshot/Freigabe, Ausgabe gekürzt ins Log

> Ehrlich: Container sind **keine** VM-Grenze. Ein Escape trifft den Host. Deshalb
> enge Rechte (`cap_drop`, `userns-remap`, seccomp) und später eine echte
> VM-Zone, wenn mehr Schutz nötig ist.

## Modul

`jarvis/zones.py` liest die Config und beantwortet:

- `critical_services()`, `is_forbidden(name)`
- `service_zone(name)` → `forbidden` | `sandbox` | `managed`
- `authorize_service(name)` → `(erlaubt, zone|grund)`
- `sandbox_limits()`, `host_reserve()`, `backend_of(zone)`
- `available_sandbox_slots(active, host_cpus, host_memory_mb)`

## Reproduzierbar auf einer anderen Maschine

1. Repo klonen, `deploy/`-Compose verwenden (siehe `docs/DEPLOYMENT.md`).
2. `config/zones.json` prüfen/anpassen (kritische Dienste, Quoten, Backend).
3. Die Sandbox/Der Executor kommen im nächsten Schritt als eigener Dienst dazu
   (`deploy/sandbox/`), der den eingeschränkten Docker-Zugriff nutzt.
4. Solange kein Proxmox/K8s da ist, bleibt `backend: docker` — die übrigen
   Dienste (`jarvis-app`, `searxng`, …) laufen unverändert.
