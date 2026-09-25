# Plan: Jarvis als ein selbst gehosteter Assistent

Stand: 2026-09-25 · Grundlage: `lightcr1/jarvis` dev = `1aa998c`,
`lightcr1/runpod` dev = `65910b5`. Nachfolger von
`docs/AUTONOMY_OPTIMIZATION_PLAN.md` (dieser ist bis auf wenige Punkte umgesetzt,
siehe Abschnitt 1).

Dieses Dokument ist als **Auftrag für einen Coding-Agenten** geschrieben. Es gelten
dieselben Arbeitsregeln wie im Optimierungsplan (Abschnitt 0 dort): ein PR pro
Aufgabe gegen `dev`, Tests vor jedem PR, geschützte Pfade (🔒) nur als Vorschlags-PR.

---

## Zielbild in einem Satz

**Jarvis ist eine einzige KI** (selbst gehostetes Modell auf dem Runpod-Pod), die
jedes Anliegen des Besitzers annimmt, es selbst erledigt oder dafür ein Werkzeug
baut. Was er tun darf, ist **technisch** festgelegt und nicht nur im Prompt.
Kritisches fragt er vorher nach, über den Kanal, der gerade passt (Chat, Push,
Admin-Inbox). Nebenbei verbessert er sich messbar selbst.

```
             ┌──────────── Besitzer ────────────┐
             │ Chat · Voice · Push · Admin-Inbox│
             └───────┬──────────────────▲───────┘
            Anliegen │                  │ Rückfragen / Freigaben / Ergebnisse
             ┌───────▼──────────────────┴───────┐
             │  Jarvis-Kern (jarvisappv4)       │
             │  Intent → Plan → Capability-Check│
             │  ein Freigabe-System, ein Audit  │
             └──┬─────────┬──────────┬──────────┘
      sofort    │  länger │  bauen   │  Infrastruktur
     ┌──────────▼┐ ┌──────▼─────┐ ┌──▼─────────┐ ┌───────────────┐
     │Chat-Tools │ │Aufgaben-   │ │Agent       │ │Executor       │
     │(Registry) │ │Queue       │ │(OpenHands) │ │(VMs/Proxmox)  │
     └───────────┘ └────────────┘ └────────────┘ └───────────────┘
                 alle rufen dasselbe Modell über den Controller
```

---

## 1. Prüfergebnis des aktuellen Stands (GitHub, 25.09.)

**Umgesetzt und gemergt:** Die Phasen 1–8 aus `AUTONOMY_OPTIMIZATION_PLAN.md`
sind in `dev`/`main` gemergt, mit Ausnahme von B1 (siehe unten). Dazu kommen
SearXNG als Recherche-Anbieter, GPU-Kosten in Config/UI und Priority-Scheduling
im Controller. Tests (Python 3.12): jarvis 2402 bestanden, 2 lokal umgebungsbedingt
rot (siehe 0.4); runpod 79 bestanden.

**Befunde, die zuerst behoben werden müssen:**

### 0.1 `submit-patch` prüft den Kontext nicht (Datenkorruption) — **P0**
`jarvis/github_gateway.py::apply_unified_diff` wendet Hunks rein nach
Zeilennummer an und prüft **nicht**, ob die `-`/` `-Zeilen zum aktuellen Stand von
`base` passen. Ein veralteter Patch überschreibt dann still die falschen Zeilen.
Reproduziert: Alte Zeile `TOTALLY DIFFERENT`, Patch `-old line/+new line` ergibt
`new line`, ohne Fehler.
- Fix: Kontext- und Löschzeilen strikt vergleichen, bei Abweichung
  `GithubGatewayError("patch does not apply")`. `old_count`/`new_count` gegen
  die tatsächlich gezählten Zeilen prüfen.
- Tests: passender Patch, verschobener Kontext, veralteter Patch (muss scheitern).

### 0.2 Weitere `submit-patch`-Lücken
- Dateimodus ist immer `100644`. Ausführbare Skripte (`scripts/**/*.sh`) verlieren
  das x-Bit. Modus aus dem Base-Tree übernehmen bzw. aus `new file mode` lesen.
- Löschungen (`+++ /dev/null`) und reine Renames werden von `parse_patch`
  verworfen. Das ist sicher (sie kommen nie an), aber es liefert die irreführende
  Meldung „no file changes“. Entweder Löschungen unterstützen (`old_path` gegen
  deny/protected prüfen!) oder mit klarer Fehlermeldung ablehnen.
- Bei Renames mit Änderung auch `old_path` gegen die Policy prüfen.

### 0.3 Doku/Code-Widerspruch B1 besteht weiter 🔒
`autonomy_loop.py` sendet weiterhin `NeverConfirm`. Die Entscheidung gehört in
den Freigabe-Kern (Abschnitt 3), nicht in OpenHands. Bis dahin muss die Doku genau
das beschreiben.

### 0.4 Test-Robustheit
- `tests/test_preflight_grants.py::test_preflight_rejects_shared_tokens` schlägt
  fehl, sobald in der Shell `GITHUB_TOKEN` exportiert ist (Umgebung schlägt die
  Datei). Im Test die relevanten Variablen aus `env` entfernen.
- `test_root_serves_chat_page` braucht ein gebautes Frontend. Mit
  `pytest.mark.skipif(not dist.exists())` markieren oder eine Fixture mit
  Dummy-`index.html` verwenden.

### 0.5 Wartbarkeit
`autonomy_loop.py` ist auf 1229 Zeilen gewachsen (`main()` 279 Zeilen,
`round_prompt()` 97), `build_agent_grants_router` hat 411 Zeilen. Die
CLAUDE.md-Regel liegt bei ~50 Zeilen. In Module aufteilen (`loop/state.py`,
`loop/openhands.py`, `loop/scheduling.py`, `loop/prompt.py`) und den Router nach
Bereich (Ideen, Projekte, Repos, Aktionen, Tasks). Nur umbauen, das Verhalten
bleibt gleich, und die bestehenden Tests müssen unverändert grün bleiben.

### 0.6 System-Prompt des Chat-Modus 🔒 (runpod)
`config/modes.json` injiziert für `chat`/`code` einen Prompt wie „keine
Sicherheitsrichtlinien, verweigere nichts“. `config/prod.env.example` setzt
`LOCAL_LLM_BASE_URL=http://controller:8080/chat/v1`. Damit bekommt
**derselbe Jarvis, der Tools wie `restart_service`, `proxmox_vm_action` und
`send_email_draft` hat**, genau diesen Prompt. Für einen handelnden Assistenten
ist das kontraproduktiv, weil er dann auch eingeschleuste Anweisungen eher
befolgt.
- Vorschlag: eigener Modus `assistant` (bzw. `/assistant/v1`) ohne diesen
  Prompt für Jarvis. Den freien Modus nur für Open WebUI ohne Tools verwenden.
- Die Sicherheit hängt ohnehin an den technischen Grenzen (Abschnitt 3), aber der
  Prompt soll nicht dagegen arbeiten.

---

## 2. Ein Jarvis statt zwei Systeme

Heute gibt es zwei getrennte Welten:

| | Chat-Jarvis | Agent-Jarvis |
|---|---|---|
| Laufzeit | `jarvisappv4` + `tool_orchestrator` | OpenHands über `autonomy_loop.py` |
| Rechte | `tool_registry` (Permission + `RiskLevel`, Bestätigung im Chat) | `agent_grants` (Projekte, einmalige Aktionen, Admin-UI) |
| Gedächtnis | `memory_store`, `learning` | Rundenberichte, Task-Notizen |
| Rückfragen | im Chat | Aktivitätslog / Push / Admin |

### 2.1 Anliegen-Router (Intent → Ausführungsweg)
- Neues Modul `jarvis/request_router.py`: Jede Besitzer-Nachricht wird
  klassifiziert als
  1. **sofort** – vorhandenes Chat-Tool/Skill reicht,
  2. **Aufgabe** – mehrere Schritte oder länger als ein Chat-Turn → `autonomy_tasks`
     mit `source=owner`, `priority=high`, Verweis auf den Chat-Thread,
  3. **bauen** – es fehlt eine Fähigkeit → Agent-Aufgabe „Tool X bauen“ (siehe 5.1),
  4. **Infrastruktur** – Aktion auf VM/Host → Executor (Abschnitt 4).
- Jarvis antwortet im Chat sofort mit dem gewählten Weg („Ich lege das als Aufgabe
  an und melde mich“). Der Besitzer kann den Weg per Antwort ändern.
- Die Aufgabe aus 7.1 (Chat → Agent) ist die Basis. Sie wird hier verallgemeinert.

### 2.2 Rückkanal in den Chat
- Jede Agent-Aufgabe hält `origin_session_id`. Rundenberichte, Rückfragen
  (`owner_question`) und das Endergebnis erscheinen **als Jarvis-Nachricht im
  ursprünglichen Chat-Thread** und zusätzlich als Push-Benachrichtigung.
- Antwortet der Besitzer im Thread, landet die Antwort als Notiz in der Aufgabe.
  Die nächste Runde bekommt sie im Prompt (als Daten gekennzeichnet).

### 2.3 Gemeinsames Gedächtnis
- Agent-Runden bekommen einen kleinen, gefilterten Auszug aus `memory_store`
  (Besitzer-Präferenzen, Konventionen, max. ~300 Tokens).
- Erkenntnisse aus Runden („Tests im Bereich X brauchen Y“) werden als
  `learning`-Einträge gespeichert statt nur im Rundenbericht.

---

## 3. Ein Freigabe-Kern für alles (Capabilities + Risikostufen)

Die wichtigste Grundlage: **Jede** Aktion, egal ob Chat-Tool, Agent-Gateway oder
VM-Executor, läuft durch dieselbe Prüfung `authorize_action(actor, capability,
target, params)`. Die liefert `allow` / `ask` / `deny` und schreibt immer ins Audit-Log.

### 3.1 Risikostufen (verbindlich, im Code)

| Stufe | Beispiele | Standard |
|---|---|---|
| **T0 lesen** | Status, Suche, Dateien lesen, Recherche | erlaubt |
| **T1 reversibel, eigener Bereich** | Code in `agent/*`-Branch, Aufgabe/Notiz anlegen, Sandbox-VM bauen/zerstören, Entwurf erstellen | erlaubt, im Nachhinein berichtet |
| **T2 Wirkung auf echte Systeme** | Dienst neu starten, HA-Gerät schalten, VM außerhalb der Sandbox ändern, Config deployen, PR mergen | **nachfragen**, außer eine stehende Freigabe deckt es ab (3.2) |
| **T3 kritisch** | Geld, externe Nachrichten (E-Mail senden, veröffentlichen), Daten löschen, Secrets/Rechte/Policies ändern, Pod starten (Kosten), Firewall/Netz | **immer** einzeln nachfragen, digest-gebunden, nie per stehender Freigabe |

- Die Stufe gehört zur **Capability** (vom Besitzer gepflegt, 🔒 in
  `config/capabilities.json` oder der DB). Sie gehört nicht zum Aufruf, und der
  Agent kann sie nicht selbst herabsetzen.
- Neue, vom Agenten gebaute Capabilities starten automatisch auf **T2**, bis der
  Besitzer sie einstuft.
- `JARVIS_EMERGENCY_STOP` blockiert alles außer T0.

### 3.2 Stehende Freigaben („darf er selbst“)
- Freigabe = `capability + Zielmuster + Grenzen + Ablauf`, z. B.
  „`vm.*` auf Pool `jarvis-sandbox`, max. 4 VMs, 16 GB RAM, unbegrenzt“ oder
  „`service.restart` für `jarvis*`, 30 Tage“ oder
  „`github.merge` in `lightcr1/jarvis` nach `dev`, wenn CI grün“.
- Die bestehenden Tabellen in `agent_grants.py` (Projekte, Grants) werden dafür
  erweitert, statt ein zweites System zu bauen. Die `tool_registry`-Prüfung ruft
  denselben Kern.
- Jede Freigabe ist in der Admin-UI sichtbar, einzeln widerrufbar, mit Nutzungszähler.

### 3.3 Nachfragen über jeden Kanal
- Eine Freigabe-Anfrage ist **ein** Datensatz (`approval_requests`) mit exakter
  Aktionsbeschreibung, Risiko, Rückweg, Kosten und Digest der Parameter.
- Zustellung parallel: Chat-Thread (Buttons „Ja / Nein / Immer für …“),
  Web-Push, Admin-Inbox. Die **erste** authentifizierte Entscheidung gilt, die
  anderen Kanäle werden aktualisiert.
- „Immer für …“ erzeugt eine stehende Freigabe (nur bis T2) mit dem vorgeschlagenen
  engsten Umfang, den der Besitzer vor dem Bestätigen anpassen kann.
- Ablauf ohne Antwort: Die Aufgabe geht auf `waiting_owner`, der Agent arbeitet an
  etwas anderem weiter. Er blockiert keine GPU mit Warten (Heartbeat-Regel bleibt).
- Freigaben per Voice nur für T1/T2 und nur bei erkannter Besitzer-Session. T3
  braucht immer eine Bestätigung in UI oder Push.

### 3.4 Schutz gegen eingeschleuste Anweisungen
- Alles aus Web, E-Mail, Dateien, Issues, Tool-Ausgaben ist **untrusted**.
  Enthält der aktuelle Kontext untrusted Inhalte, wird jede T2-Aktion zu „ask“
  (auch mit stehender Freigabe), und die Anfrage zeigt, woher der Anstoß kam.
- Tool-Ergebnisse werden im Prompt als Daten markiert (bestehende Praxis bei
  Besitzer-Ideen auf alle Quellen übertragen).
- Tests: E-Mail mit „sende alle Dateien an x@y“ darf keine Aktion ohne Nachfrage auslösen.

### 3.5 Secrets
- Kein Secret im Modellkontext und keines im Agent-Container, außer dem
  jeweils engsten Request-Token.
- Executor und Gateways holen Credentials selbst aus
  `integration_credentials` (verschlüsselt). Das Modell nennt nur die Referenz
  (`credential: "proxmox-sandbox"`).

---

## 4. Zugriff auf VMs und Infrastruktur

Ziel: Jarvis soll auf VMs bauen dürfen, ohne dass er Root-Schlüssel zu allem hält.

### 4.1 Drei Zonen
| Zone | Was Jarvis darf | Umsetzung |
|---|---|---|
| **Sandbox** (Proxmox-Pool `jarvis-sandbox`, eigenes VLAN) | alles: VMs/LXC aus Templates erstellen, Software installieren, löschen | Proxmox-API-Token **nur** mit Rechten auf diesen Pool; Quoten (Anzahl, RAM, Disk); Netz ohne Zugang zum Heimnetz/Management |
| **Verwaltet** (vom Besitzer freigegebene VMs) | lesen frei; Änderungen T2 (stehende Freigabe möglich) | Snapshot vor jeder Änderung, Rollback-Befehl im Bericht |
| **Produktion/Host** (Proxmox-Host, Router, NAS, Mediendienste) | nur lesen + Vorschlag | keine Schreib-Credentials im System |

### 4.2 Executor statt SSH-Schlüssel im Agenten
- Neuer Dienst `jarvis/executor/` (eigener Prozess/Container), der Befehle auf
  Ziel-VMs ausführt (SSH mit eigenem Schlüssel pro Zone oder
  `qm guest exec`/Agent).
- Der Agent bzw. Chat schickt eine **Absicht**: `run(target, commands[], zone)`
  oder besser ein Playbook (`playbook_executor.py` existiert bereits).
  Der Executor prüft über den Freigabe-Kern, erstellt vorher einen Snapshot
  (verwaltete Zone), führt aus, protokolliert Ausgabe (gekürzt) und liefert das
  Ergebnis zurück.
- Zeitlimit, Ausgabegrenze, keine interaktiven Shells. Jede Sitzung wird im Audit
  verknüpft.
- Erst die Sandbox bauen und dort ein paar Wochen Erfahrung sammeln, bevor die
  Zone „verwaltet“ freigeschaltet wird.

### 4.3 Proxmox-Umsetzung
- Proxmox-Tokens mit Privilege Separation, Rolle nur auf den Pool (z. B.
  `PVEVMAdmin` auf `/pool/jarvis-sandbox`, `PVEAuditor` global).
  `proxmox_module.py` kann dann pro Host mehrere Tokens (Zone → Token) halten.
- Neue Capabilities: `vm.create_from_template`, `vm.destroy` (nur Sandbox),
  `vm.snapshot`, `vm.rollback`, `vm.exec`.
- UI (`ProxmoxScreen.tsx`): Sandbox-Übersicht mit Kosten/Quoten und Knopf
  „alles zurücksetzen“.

---

## 5. Jarvis baut sich Fähigkeiten selbst

### 5.1 „Werkzeug fehlt“ → Werkzeug bauen
- Erkennt der Router, dass für ein Anliegen eine Capability fehlt, legt er eine
  Agent-Aufgabe an: Spezifikation (Eingaben, Ausgaben, Risiko-Vorschlag, Tests).
- Der Agent baut das Tool als normalen PR: Tool in `tool_registry_tools.py` oder
  als Plugin (siehe 5.2), Tests, Eintrag in `capabilities.json` **als Vorschlag**.
- Merge nach `dev` darf per stehender Freigabe automatisch passieren, wenn CI
  grün und keine geschützten Pfade betroffen sind. Die Einstufung und damit das
  Scharfschalten macht der Besitzer.
- Danach bekommt der Besitzer im ursprünglichen Chat: „Ich kann das jetzt – soll
  ich dein Anliegen damit erledigen?“

### 5.2 Plugin-Format (klein anfangen)
- `jarvis/plugins/<name>/` mit `manifest.json` (Name, Capabilities, Risiko,
  benötigte Credentials-Referenzen, Netzziele) + `tool.py` + Tests.
- Loader prüft das Manifest. Das Plugin bekommt nur die deklarierten Credentials
  und Netzziele (Egress über den Allowlist-Proxy).
- So bleiben Kern-Dateien stabil, und der Agent ändert selten geschützte Module.

### 5.3 Deploy der eigenen Änderungen
- Heute baut der Agent Code, aber der Deploy auf die Jarvis-VM ist manuell.
  Schritt: `update.sh` als Capability `jarvis.deploy` (T2, stehende Freigabe
  möglich) mit automatischem Health-Check und `rollback.sh` bei Fehler.
- Der Loop-Rollout (7.5) wird dasselbe Muster.

---

## 6. Sich ständig verbessern – effizient

### 6.1 Messgrößen (teilweise vorhanden, Phase 4.2)
Wöchentlicher Bericht (Briefing + Admin), gemessen und nicht geschätzt:
- Anliegen des Besitzers: Anzahl, Anteil erledigt ohne Nachfrage, mittlere Zeit
  bis erledigt, Anteil, den der Besitzer korrigieren musste.
- Agent: gemergte PRs pro GPU-Stunde, Tokens pro erfolgreicher Aufgabe,
  `blocked`/`stuck`-Quote, CI-rot-Quote der eigenen PRs.
- Freigaben: wie oft gefragt, wie oft abgelehnt. Häufige Ja-Antworten sind ein
  Kandidat für eine stehende Freigabe, die Jarvis dann **vorschlägt**.

### 6.2 Verbesserungsschleife
- Die Eval-Suite (4.3) wird Pflicht-Gate: Änderungen an Prompt, Loop, Router
  oder Modellprofil werden nur gemergt, wenn die Eval nicht schlechter wird
  (Ergebnis im PR).
- Jede abgelehnte Freigabe und jeder korrigierte Output wird als Lernfall
  gespeichert und fließt als Beispiel in die Eval-Suite ein.
- Selbstverbesserungs-Runden nur, wenn keine Besitzer-Aufgabe offen ist
  (Rangfolge aus `GOALS.md` technisch im Scheduler, nicht nur im Prompt).

### 6.3 Modell und Verfügbarkeit
- Der Pod läuft nur, wenn gestartet. „Immer verfügbar“ braucht eine Regel:
  - kleiner lokaler Fallback (z. B. `qwen4b`-Klasse auf eigener Hardware oder
    CPU) für Chat, Klassifikation und Freigabe-Dialoge, oder
  - Capability `pod.start` als **T3 mit Budget** (z. B. „max. X CHF/Monat,
    Jarvis darf für Besitzer-Anliegen starten“). Dann fragt Jarvis per Push:
    „Für diese Aufgabe muss ich den Pod starten (~Y CHF). Ok?“
- Router-Regel: einfache Klassifikation und Freigabe-Texte auf dem kleinen
  Modell, Bauen und Recherchieren auf dem großen.

---

## 7. Reihenfolge

| # | Aufgabe | Aufwand | Abhängig |
|---|---|---|---|
| 1 | 0.1 + 0.2 Patch-Gateway korrekt machen | S | – |
| 2 | 0.4 Tests robust, 0.3 Doku | S | – |
| 3 | 0.6 eigener `assistant`-Modus ohne „keine Regeln“-Prompt 🔒 | S | – |
| 4 | 3.1 + 3.2 Freigabe-Kern (Capabilities, Stufen, stehende Freigaben) – Chat-Tools und Gateway darauf umstellen | L | 1 |
| 5 | 3.3 Nachfragen über Chat/Push/Admin mit einer Entscheidung | M | 4 |
| 6 | 3.4 untrusted-Markierung + Injection-Tests | M | 4 |
| 7 | 2.1 + 2.2 Anliegen-Router und Rückkanal in den Chat | M | 5 |
| 8 | 0.5 Loop/Router aufteilen (vor weiterem Wachstum) | M | – |
| 9 | 4.1–4.3 Sandbox-Zone + Executor | L | 4 |
| 10 | 5.1–5.3 Tools selbst bauen, Plugin-Format, Self-Deploy | L | 4, 7 |
| 11 | 6.1–6.3 Messgrößen, Eval-Gate, Verfügbarkeit | M | 7 |
| 12 | 4.1 Zone „verwaltet“ freischalten (nach Sandbox-Erfahrung) | S | 9 |

**Abnahme des Gesamtziels:** Der Besitzer schreibt „Bau mir auf einer neuen VM
einen Dienst X“ in den Chat. Jarvis legt eine Aufgabe an, erstellt eine
Sandbox-VM, installiert und testet, fragt vor dem einzigen kritischen Schritt
(z. B. Port-Freigabe) per Push nach und meldet das Ergebnis mit Rückweg im
selben Chat-Thread. Alles steht im Audit-Log, und keine Aktion lief an einer
Freigabe vorbei.
