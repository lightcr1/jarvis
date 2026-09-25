# Vorschlag: Sicherheit der Agenten-Automatisierung (Phase 6)

Status: **umgesetzt (GitHub-Sperre) + offener Rest.** GitHub-Downloads sind im
Allowlist-Proxy per Default gesperrt (`ALLOW_GITHUB=0`); PyPI bleibt erlaubt. Die betroffenen Dateien liegen unter `deploy/**` (geschuetzt
laut `config/agent-policy.json`).

## Ausgangslage

- `deploy/openhands/allowlist-proxy/allowlist_proxy.py` erlaubt GitHub
  (`github.com`, `raw.githubusercontent.com`, `codeload.github.com`) und PyPI.
  GitHub-Downloads ermoeglichen dem Agenten, beliebigen Fremdcode zu laden.
- Der Agent-Container haengt im internen `agent-isolated`-Netz; je nach
  Execution-Backend koennen weitere Arbeitscontainer entstehen.
- `JARVIS_AGENT_REQUEST_TOKEN` ist der einzige Jarvis-Zugang des Agenten.

## Vorschlaege (jeweils als eigener, pruefbarer Schritt)

1. **PyPI lokal spiegeln statt Internet-Proxy.**
   - Variante A: vorab gebaute Wheels im Image / lokaler Wheel-Cache.
   - Variante B: `devpi`-Mirror im internen Netz.
   - Danach den Proxy auf PyPI beschraenken oder ganz abschalten.
2. **GitHub nur ueber das Gateway.**
   - Download beliebigen Fremdcodes aus dem Agenten entfernen; Recherche und
     PR-Schritte laufen weiterhin ueber `scripts/agent/jarvis_gateway.py`.
   - Konsequenz fuer den Rundenprompt: `AGENT_NETWORK_MODE` dann `isolated`.
3. **Arbeitscontainer-Isolation pruefen.**
   - `scripts/agent/check_container_isolation.sh <container>` (read-only)
     prueft, dass nur erlaubte Netze (`agent-isolated`) verwendet werden.
   - Als wiederkehrender Check/Hook denkbar; erfordert Docker-Zugriff.
4. **Token-Minimierung (bereits umgesetzt, hier dokumentiert).**
   - Der Agenten-Token oeffnet ausschliesslich `/agent/*`-Endpunkte; Tests in
     `tests/test_autonomy_task_api.py` und `tests/test_github_patch.py`
     belegen, dass kein `/admin/*`-Endpunkt damit erreichbar ist.

## Nicht in diesem Vorschlag

- Keine Aenderung an `.env`, Tokens oder produktiven Diensten.
- Kein automatischer Rollout; jede Aenderung an `deploy/**` braucht
  Owner-Review.
