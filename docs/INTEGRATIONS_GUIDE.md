# Integrationen im Jarvis-Agent-Gateway

Dieser Leitfaden beschreibt, wie externe Aktionen sicher an Jarvis angebunden
werden. Grundprinzip (siehe `docs/AUTONOMY_LOOP.md`): **kein generischer
Netzzugang**, sondern pro Kanal ein geschlossener, typisierter Gateway, der
Ziel und Aktion serverseitig prüft, Owner-Freigaben (`AgentGrantStore`)
einholt und Audit schreibt. Ein LLM-Prompt ist niemals eine Erlaubnis.

## Bestehende Gateways (Stand 23.09.2026, Draft-PR #84)

| Kanal | Gateway | Freigabe-Typ | Aktionen | Hinweise |
| --- | --- | --- | --- | --- |
| GitHub-Metadaten | `jarvis/github_gateway.py` | Grant `other_project` + `read_metadata` | `GET /agent/repositories/{o}/{r}/metadata` | nur öffentliche Repos, anonym, keine Redirects |
| GitHub-Branch | `jarvis/github_gateway.py` | Projektop. `create_branch` | `POST .../branches` | nur `agent/*`, Basis nur `dev`/`main` |
| GitHub-Datei | `jarvis/github_gateway.py` | Projektop. `write_branch_file` | `PUT .../files` | ≤256 KiB, Schutzpfade blockiert |
| GitHub-PR | `jarvis/github_gateway.py` | einmalige Aktion `github_create_pr` | `POST /agent/actions/github-pull-request` | digest-gebunden, einmalig |
| Business-Suche | `jarvis/research_gateway.py` | Projektop. `web_search` (`business_research`) | `POST /agent/research/search` | Brave-API, 20/Tag/Projekt, keine Redirects |
| E-Mail-Versand | `jarvis/email/service.py` | einmalige Aktion `email_send` | `POST /agent/actions/email-send` | Inhalt zum Review, einmalig |
| Open WebUI-Brücke (Ideen) | `integrations/openwebui/idea_inbox.py` | – (nur Vorschlag) | `POST /agent/ideas` | nur explizite `...-Idee:`-Formulare; normaler Chat wird nicht automatisch erfasst |

## So kommt eine neue Integration dazu (Checkliste)

1. **Modul:** eigenes `jarvis/<name>_gateway.py` mit fester Ziel-URL,
   `_NoRedirect`, Größen-/Format-Limits und klarer Error-Klasse. Keine beliebigen
   vom Agenten wählbaren URLs/Hosts; keine Secrets im Rückgabewert.
2. **Freigabe:** Aktion in `AgentGrantStore` modellieren:
   - wiederkehrend innerhalb eines Ziels → Projekt-Operation (in
     `_validate` als `SAFE_KINDS`/Operation aufnehmen, keine Wildcards),
   - einmalig mit Außenwirkung → One-Time-Action (Digest + einmalig + Owner).
3. **API:** Endpoint in `jarvis/api_agent_grants.py`: `agent()`-Guard (Request-
   Token), Rate-Limit (`cap`), `require_operational()` (Not-Aus), dann
   `authorize()` **vor** dem externen Aufruf, Ergebnis ins Audit.
4. **Isolierung:** Pfad-Muster in `deploy/openhands/inference-gateway.conf`
   explizit aufnehmen; alles andere liefert 403.
5. **Client:** Unterbefehl in `scripts/agent/jarvis_gateway.py`, damit der
   isolierte Agent den Kanal überhaupt nutzen kann.
6. **Tests:** Offline-Tests ohne Netz – Validierung, Freigabepflicht (401/403),
   Einmaligkeit/Widerruf, Not-Aus (503), Rate-Limit; Mock des externen Calls.
7. **Doku:** Diese Tabelle, `docs/AUTONOMY_LOOP.md`, ggf. `docs/HUMAN_TODO_GRANTS.md`.
8. **Produktiv:** Provider-Credentials nur serverseitig in `jarvis.env`,
   Preflight-Kennung, Token-Rotation, Praxis-Test auf der VM.

## Bewusst NICHT enthalten

- **Zahlungen, Verträge, Käufe, Publikation:** brauchen einen echten Provider,
  Budgetgrenzen und eine eigene Freigabe-Kostenlogik; ohne diese kein Pfad.
- **Private Repos:** nur wenn der serverseitige GitHub-Token genau dafür
  berechtigt wird; Zugriff bleibt auf der Server-Seite.
- **Allgemeines Shell-/Terminal-Gateway für den Agenten:** OpenHands bleibt
  durch Sandbox/Netz begrenzt; ein Shell-Gateway wäre ein eigenes, großes,
  reviewpflichtiges Vorhaben.
