# Optimierungsplan: Autonomy-Loop, Kontext-Effizienz und fehlende Features

Stand: 2026-09-25 · Grundlage: Code-Review von `lightcr1/jarvis` (dev = `5fd0dcf`)
und `lightcr1/runpod` (main = `164df8c`).

Dieses Dokument ist als **Auftrag für einen Coding-Agenten** geschrieben. Jede
Aufgabe hat Ziel, betroffene Dateien und Abnahmekriterien. Reihenfolge = Priorität.

---

## 0. Arbeitsregeln für den ausführenden Agenten

- Arbeite pro Aufgabe auf einem eigenen Branch `agent/<kurzname>`, PR gegen `dev`.
  Eine Aufgabe = ein PR. Keine Sammel-PRs über mehrere Phasen.
- Vor jedem PR: `python3 -m pytest -q` (jarvis: mindestens die betroffenen
  Testdateien plus `tests/test_autonomy_loop.py`, `tests/test_agent_*.py`;
  runpod: `python -m pytest -q`) und `python3 scripts/agent/check_policy.py`.
- **Geschützte Pfade** (`AGENTS.md`, `config/agent-policy.json`, `.github/**`,
  `deploy/**`, Auth/Billing/Permission-Module) nur als **Vorschlags-PR** mit
  Label/Hinweis "owner review required". Aufgaben, die das betreffen, sind unten
  mit 🔒 markiert.
- Nichts an Runpod-Ressourcen, `.env`-Dateien oder Tokens ändern. Kein Test,
  der einen echten Pod startet.
- Die installierte Loop-Kopie auf der VM (`/home/media/jarvis-openhands/autonomy/`)
  wird **nicht** vom Agenten ersetzt; Rollout macht der Besitzer mit
  `scripts/agent/install_loop.sh`.

---

## 1. Ist-Analyse (kurz)

Pipeline heute:

```
cron (*/2 min) -> autonomy_loop.py -> OpenHands-API (Canvas, :8001)
   -> Agent-Container (agent-isolated) -> inference-gateway -> Controller /agent/v1
   -> Runpod-Pod (vLLM, Qwen3.8-27B-FP8, max_model_len 32768, max_num_seqs 2)
Veröffentlichung: nur über scripts/agent/jarvis_gateway.py (write-file pro Datei, request-pr)
```

Wichtigste Befunde:

| # | Befund | Wirkung |
|---|---|---|
| B1 | `start_round()` sendet `confirmation_policy: NeverConfirm`, `docs/AUTONOMY_LOOP.md` behauptet, die versionierte Quelle nutze `ConfirmRisky`. | Doku/Code widersprechen sich; unklar, was sicherheitlich gilt. |
| B2 | Rundenprompt sagt „Agent-Container hat KEIN Internet“, aber `deploy/openhands/compose.yml` setzt `HTTP(S)_PROXY` auf den Allowlist-Proxy (GitHub + PyPI erlaubt). | Agent bekommt falsches Weltbild, verschwendet Iterationen oder nutzt Pfade, die er nicht nutzen soll. |
| B3 | Fällt `/api/status` auf den `model-ready`-Fallback (`pod_id=None`), wertet der Loop das als **neuen Pod-Zyklus** und leert `active_sessions`. Laufende eigene Runden gelten danach als `foreign_active` → keine Heartbeats mehr, keine neuen Runden. | Controller-Idle-Stop kann den Pod **mitten in einer Runde** stoppen; Loop blockiert sich selbst. |
| B4 | Wrapup: Nach `wrapup_done` kehrt `main()` sofort zurück. Eine parallel noch laufende Normalrunde bekommt keinen Wrapup-Hinweis; endet sie nach der Wrapup-Runde, ruft `close_round(..., force_stop=False)` **keinen** Pod-Stop auf. | Pod läuft bis zum Controller-Idle-Stop weiter (Kosten), Normalrunde wird ggf. hart abgeschnitten. |
| B5 | `delete_conversation()` ist definiert, wird aber nie aufgerufen; Worktrees werden nie aufgeräumt. | Conversations/Worktrees sammeln sich an, Canvas-Liste und Disk wachsen. |
| B6 | Pausieren bei Benutzeraktivität greift nur alle 2 min (Cron). vLLM hat `max_num_seqs: 2`, der Loop fährt bis zu **2** parallele Agentenrunden. | Besitzer-Anfragen in Open WebUI/IDE warten hinter Agenten-Requests (bis zu Minuten). |
| B7 | `docs/ACTIVITY_LOG.md` hat genau einen Eintrag, obwohl Runden laufen. Runden schreiben das Log im eigenen Worktree-Branch, der meist nie veröffentlicht wird. | Kein nachvollziehbarer Verlauf, kein Rundengedächtnis. |
| B8 | Veröffentlichung nur über `write-file` **pro Datei** + separater `request-pr`. | Viele Tool-Calls und Kontext pro Änderung; Mehrdatei-Änderungen sind nicht atomar. |
| B9 | Cron führt die installierte Kopie aus, nicht das Repo; kein Versions-/Drift-Check. | Gemergte Fixes laufen unbemerkt nicht. |
| B10 | Hartkodierte IPs/Pfade (`10.10.40.100`, `/home/media/...`), TLS-Verifikation aus. | Schwer testbar/portierbar; MITM im LAN möglich. |
| B11 | `runpod/docs/CURRENT_STATUS.md` ist veraltet („noch nicht committet“, Pod noch nie gestartet). | Agenten lesen falschen Stand und planen falsch. |

Kontext-Befunde (Token-Zahlen sind Schätzungen, ≈ 4 Zeichen/Token):

| Quelle | Größe | ≈ Tokens |
|---|---|---|
| Modell-Kontext gesamt (`max_model_len`) | – | 32 768 |
| `CLAUDE.md` (jarvis) | 50 KB | 12–14 k |
| `docs/v2/planning/EXECUTION_CHECKLIST_V2.md` | 52 KB | 13–15 k |
| `AGENTS.md` | 10 KB | ~2,7 k |
| `docs/GOALS.md` | ~6 KB | ~1,6 k |
| Rundenprompt (`round_prompt`) | ~3,5 KB | ~1 k |
| `jarvisappv4.py` | 49 KB | 12–13 k |

→ Liest der Agent `CLAUDE.md` oder die Checkliste einmal komplett, ist ~40 % des
Kontexts weg, bevor er eine Zeile Code gesehen hat. Dazu kommen OpenHands-
Systemprompt + Tool-Definitionen und Reasoning-Tokens (`--reasoning-parser qwen3`).
Der Condenser steht auf `max_size: 200` **Events** – bei 32k Kontext läuft das
Fenster deutlich früher über, als der Condenser eingreift.

---

## Phase 1 — Korrektheit des Loops (Quick Wins, zuerst)

### 1.1 Pod-Zyklus-Erkennung reparieren (B3)
- **Datei:** `scripts/agent/autonomy_loop.py` (`main`, `check_pod`)
- Neuen Pod-Zyklus nur erkennen, wenn `pod_id` **nicht None** und verschieden ist.
  Beim `model-ready`-Fallback `pod_id` aus dem State übernehmen.
- Zusätzlich: eigene Sessions nie über `foreign_active` blockieren – Sessions mit
  Tag `kind=autonomy` (werden bereits gesetzt) als eigene erkennen und wieder in
  `active_sessions` adoptieren.
- **Abnahme:** Test, der `check_pod` → `(True, "RUNNING(model-ready)", None)` liefert
  und prüft, dass `active_sessions` erhalten bleibt und Heartbeat gesendet wird.
  Test für Adoption einer getaggten, unbekannten Session.

### 1.2 Wrapup sauber zu Ende führen (B4)
- Wenn Wrapup ausgelöst wird: an alle noch laufenden eigenen Runden eine
  Nachricht „Schließe ab, keine neuen Aufgaben“ senden (OpenHands
  `POST /api/conversations/{id}/events` o. ä. – Endpunkt gegen die eingesetzte
  OpenHands-Version prüfen).
- In `close_round`: Pod stoppen, sobald **die letzte** Session endet und
  `wrapup_done` gesetzt ist – unabhängig davon, welche Art Runde zuletzt endet.
- **Abnahme:** Tests für (a) Wrapup endet vor Normalrunde, (b) Normalrunde endet
  vor Wrapup – in beiden Fällen genau ein `stop_pod`-Aufruf.

### 1.3 Aufräumen (B5)
- Beendete eigene Conversations nach erfolgreichem Rundenabschluss (und nach
  Speichern des Rundenberichts, siehe 3.2) mit `delete_conversation` löschen –
  konfigurierbar (`KEEP_FINISHED_CONVERSATIONS=N`, Standard: letzte 10 behalten).
- Verwaiste Worktrees (`git worktree prune` + Löschen von Worktrees ohne aktive
  Session älter als 24 h) in einem separaten, getesteten Helfer.
- **Abnahme:** Unit-Tests mit gemockter HTTP-Schicht; kein Löschen laufender/pausierter Sessions.

### 1.4 Doku und Code angleichen (B1, B2) 🔒 (teilweise `deploy/**`)
- Entscheidung als Vorschlag vorlegen: `ConfirmRisky` vs. `NeverConfirm`.
  Empfehlung: `NeverConfirm` **nur** im isolierten Container behalten (echte
  Grenzen sind Netzwerk + Gateway), dafür Doku korrigieren – `ConfirmRisky` ohne
  menschlichen Beobachter blockiert Runden nur.
- Umgebungsbeschreibung im Prompt **nicht** hartkodieren, sondern zu Rundenbeginn
  vom Loop ermitteln (Konfigwert `AGENT_NETWORK_MODE = isolated | allowlist-proxy`)
  und daraus den passenden Satz erzeugen.
- **Abnahme:** `docs/AUTONOMY_LOOP.md` (beide Repos) beschreibt exakt das
  Code-Verhalten; Test, dass beide Netzwerkmodi den richtigen Prompt-Text liefern.

### 1.5 Konfiguration statt Konstanten (B10)
- Alle Konstanten (`CONTROLLER_BASE`, `OPENHANDS_BASE`, `JARVIS_BASE`, Pfade,
  `COOLDOWN_SECONDS`, `MAX_PARALLEL_ROUNDS`, `MAX_ITERATIONS`, Condenser-Werte)
  aus einer Datei `autonomy-loop.env` bzw. Umgebungsvariablen lesen, mit den
  heutigen Werten als Default.
- TLS: statt `CERT_NONE` optional `CONTROLLER_CA_FILE` (die selbst erzeugte
  `tls/server.crt` aus dem runpod-Repo) verwenden; `CERT_NONE` nur als expliziter
  Fallback mit Log-Warnung.
- **Abnahme:** bestehende Tests grün, neue Tests für Config-Parsing.

### 1.6 Versions-Drift sichtbar machen (B9)
- Loop loggt beim Start den SHA256 seiner eigenen Datei und schreibt ihn in den
  State. `AgentMonitorPage.tsx` zeigt „installiert: <hash> / Repo: <hash>“ und
  warnt bei Abweichung.
- `install_loop.sh` um `--check` erweitern (Exit 1 bei Drift) – für einen
  späteren Timer.

---

## Phase 2 — Kontext-Effizienz (größter Hebel für Qualität pro GPU-Stunde)

### 2.1 Kompakte Agenten-Kontextdatei
- Neue Datei `docs/agent/CONTEXT.md` (**Ziel ≤ 1 500 Tokens**): Repo-Karte
  (Verzeichnisse → Zweck in einer Zeile), wie man Tests gezielt ausführt,
  wichtigste Konventionen, wo Details stehen (mit Hinweis „per `grep`, nicht
  komplett lesen“).
- Pro Bereich optionale Kurzkarten `docs/agent/areas/<bereich>.md` (≤ 600 Tokens):
  `autonomy`, `home_assistant`, `billing`, `files`, `frontend`, `voice`.
- Rundenprompt verweist nur noch auf `docs/agent/CONTEXT.md` + die zur Aufgabe
  passende Bereichskarte; **ausdrücklich**: `CLAUDE.md`,
  `EXECUTION_CHECKLIST_V2.md`, `jarvisappv4.py` nie vollständig lesen, nur
  `grep -n` / `sed -n a,bp`.
- Prüfen, ob die eingesetzte OpenHands-Version `AGENTS.md` bzw.
  `.openhands/microagents/repo.md` automatisch in den Kontext lädt. Falls ja:
  diesen Inhalt bewusst klein halten (AGENTS.md ist 🔒 → Kürzungsvorschlag als PR).
- **Abnahme:** Test/Script `scripts/agent/context_budget.py`, das die Größe der
  Agenten-Kontextdateien prüft (Tokens ≈ Zeichen/4) und in CI bei Überschreitung fehlschlägt.

### 2.2 Condenser und Iterationsbudget an 32k anpassen
- `condenser.max_size` von 200 auf einen gemessenen Wert senken (Startwert
  40–60 Events, `keep_first: 2`), konfigurierbar (1.5).
- `MAX_ITERATIONS` 120 → pro Aufgabentyp (siehe 3.1): klein 40, mittel 80.
- **Abnahme:** in 5 Testrunden kein Kontext-Überlauf-Fehler (HTTP 400
  „maximum context length“) im Controller-Log; Messung aus 4.1.

### 2.3 Prefix-Caching ausnutzen
- `round_prompt()` so umbauen, dass der **statische Teil zuerst** kommt
  (Regeln, Umgebung, Arbeitsweise) und alles Variable (Fokus, Aufgabe,
  Besitzer-Ideen, letzte Übergabenotizen) **am Ende**. Heute steht `focus_text`
  vor dem statischen Umgebungstext – das verhindert Prefix-Cache-Treffer
  zwischen Engineering- und Ideen-Runden.
- Im runpod-Repo sicherstellen, dass vLLM Prefix-Caching aktiv hat
  (`--enable-prefix-caching`, falls die Version es nicht standardmäßig aktiviert).
- **Abnahme:** Test, dass die ersten N Zeichen des Prompts für alle Fokus-Arten
  identisch sind.

### 2.4 Mehr effektiver Kontext auf derselben GPU (runpod-Repo)
- Experiment (kein Default-Wechsel ohne Messung): `--kv-cache-dtype fp8` im
  Profil `default` testen und `max_model_len` auf 49 152 bzw. 65 536 anheben,
  solange `max_num_seqs: 2` stabil in den VRAM passt.
- Reasoning: Für `/agent/v1` testen, ob `chat_template_kwargs:
  {"enable_thinking": false}` (vom Controller injiziert, abschaltbar per
  Setting) die Erfolgsquote hält und Tokens/Zeit spart. Nur übernehmen, wenn
  die Eval aus 4.2 das bestätigt.
- **Abnahme:** Messprotokoll in `runpod/docs/MODELLAUSWAHL.md` (Kontext,
  Tokens/s, Erfolgsquote); Profiländerung erst nach Besitzerfreigabe.

### 2.5 Tool-Output klein halten
- Standardbefehle als Skripte mit kompakter Ausgabe, auf die der Prompt verweist:
  - `scripts/agent/verify.sh [pfade…]`: führt nur betroffene Tests aus
    (`pytest -q -x --no-header -p no:cacheprovider`, Ausgabe auf die letzten
    ~60 Zeilen begrenzt), `check_policy.py`, bei Frontend-Änderungen `vitest run`
    für betroffene Dateien.
  - `scripts/agent/find.sh <begriff>`: `grep -rn` mit Ausschlüssen
    (`node_modules`, `dist`, `.git`) und Trefferlimit.
- **Abnahme:** Tests für die Pfad→Testdatei-Zuordnung in `verify.sh` (bzw. Python-Helfer).

---

## Phase 3 — Aufgabensteuerung statt „such dir was aus“

Heute bekommt jede Runde denselben offenen Auftrag („wähle die wertvollste
Arbeit“). Jede Runde erkundet das Repo neu → der Großteil des Kontexts geht in
Orientierung statt Umsetzung, Doppelarbeit ist wahrscheinlich.

### 3.1 Backlog als Datenquelle
- Neue Tabelle `autonomy_tasks` im bestehenden SQLite-Store
  (`jarvis/agent_grants.py` oder eigener `jarvis/autonomy_task_store.py`):
  `id, title, description, area, size (small|medium), priority, status
  (open|in_progress|submitted|done|blocked|rejected), source (owner|agent|issue),
  attempts, last_round_id, created_at, updated_at`.
- Endpunkte (Muster `build_*_router`):
  - Admin: CRUD + Priorisieren (`/admin/autonomy/tasks`).
  - Agent (mit `JARVIS_AGENT_REQUEST_TOKEN`): `POST /agent/tasks` (nur
    Vorschlag, Status `proposed` – Besitzer muss freigeben),
    `POST /agent/tasks/{id}/report`.
- Loop: holt vor Rundenstart die höchstpriorisierte offene Aufgabe passend zum
  Fokus, setzt sie auf `in_progress` und gibt **genau diese** Aufgabe (+
  Bereichskarte, + letzte Übergabenotiz zu dieser Aufgabe) in den Prompt.
  Leerer Backlog → „Discovery-Runde“ mit hartem Limit (max. 3 Aufgabenvorschläge,
  keine Codeänderung).
- `attempts >= 3` ohne Erfolg → `blocked` + Besitzerfrage statt Endlosschleife.
- **Abnahme:** Store-Tests mit echter In-Memory/Temp-SQLite, API-Tests mit
  `TestClient`, Loop-Test für Aufgabenauswahl.

### 3.2 Strukturierter Rundenbericht statt ACTIVITY_LOG im Worktree (B7)
- Am Rundenende schreibt der Agent über `jarvis_gateway.py report-round` einen
  JSON-Bericht: `task_id, outcome (done|partial|blocked|no_change),
  summary (≤ 800 Zeichen), branch, files_changed, tests (passed/failed/cmd),
  next_step, owner_question`.
- Server speichert ihn; der Loop gibt beim nächsten Versuch derselben Aufgabe
  die letzte Notiz (≤ 500 Tokens) mit. Das ersetzt Rundengedächtnis über
  `docs/ACTIVITY_LOG.md`.
- `docs/ACTIVITY_LOG.md` wird optional aus den Berichten generiert (Admin-Export),
  nicht mehr von Runden direkt bearbeitet → keine Merge-Konflikte zwischen
  parallelen Branches.
- Fehlt nach Rundenende ein Bericht, erzeugt der Loop einen Minimalbericht
  (`outcome=unknown`, letzte Agent-Nachricht gekürzt).

### 3.3 Doppelarbeit vermeiden
- Vor Rundenstart: offene `agent/*`-PRs und `submitted`-Aufgaben abfragen
  (Gateway-Endpunkt `GET /agent/repositories/{o}/{r}/pulls?head_prefix=agent/`)
  und in einer Zeile in den Prompt geben.
- Zwei parallele Runden bekommen nie dieselbe Aufgabe und nie denselben `area`.

### 3.4 GitHub-Issues als Backlog-Quelle (optional)
- Issues mit Label `agent` werden (über das Gateway, read-only) als
  `source=issue`-Aufgaben importiert; Besitzer priorisiert im Admin-UI.

---

## Phase 4 — Veröffentlichung, Messen und Evaluieren

### 4.1 Atomare Patch-Einreichung (B8)
- Neuer Gateway-Endpunkt `POST /agent/repositories/{o}/{r}/patches` +
  CLI `jarvis_gateway.py submit-patch <repo> <branch> <base> <patchfile> <message>`:
  - Agent erzeugt lokal `git diff <base>...HEAD > /tmp/change.patch`.
  - Server prüft: Projektfreigabe mit Operation `write`, Größenlimit,
    `deny_paths`/`protected_paths` aus `config/agent-policy.json`, keine
    Binärdateien, Branch-Präfix `agent/`.
  - Server wendet den Patch auf den Base-Stand an und erzeugt **einen** Commit
    über die GitHub Git-Data-API (Tree + Commit + Ref), danach optional direkt
    den einmaligen `request-pr`-Antrag.
- `write-file` bleibt für Einzeldateien bestehen.
- **Abnahme:** Tests mit gemocktem GitHub-Client: erlaubter Patch → ein Commit;
  Patch mit geschütztem Pfad → 403; ohne Projektfreigabe → 403.

### 4.2 Rundenmetriken und Kosten
- Controller (runpod): pro `/agent/v1`-Request `usage.prompt_tokens`,
  `completion_tokens`, Dauer loggen (ohne Inhalte) und über
  `GET /api/agent/usage?since=` aggregiert ausgeben; Header
  `X-Agent-Round-Id` (vom Loop gesetzt über ein Feld in der LLM-Config, falls
  OpenHands Extra-Header unterstützt, sonst per Zeitfenster zuordnen).
- Loop: pro Runde `started_at, ended_at, iterations, status, tokens, gpu_seconds,
  geschätzte Kosten (GPU-$/h aus Config)` in den Rundenbericht.
- Admin-UI (`AgentMonitorPage.tsx`): Tabelle der letzten Runden, Kennzahlen
  „eingereichte Patches / GPU-Stunde“, „gemergte PRs / GPU-Stunde“,
  „Tokens pro erfolgreicher Aufgabe“, Anteil `blocked/no_change`.

### 4.3 Kleine Eval-Suite für Modell- und Konfigurationsentscheidungen
- `scripts/agent/eval/`: 6–10 reproduzierbare Aufgaben aus dem echten Repo
  (fester Commit, Aufgabenbeschreibung, Prüfskript = bestimmte Tests grün).
- Runner startet je Aufgabe eine OpenHands-Conversation mit der gewählten
  Konfiguration und misst Erfolg, Iterationen, Tokens, Zeit.
- Damit entscheiden: Qwen3.8-27B vs. `coding-max` (Qwen3-Coder-30B-A3B, MoE –
  vermutlich deutlich mehr Tokens/s), Thinking an/aus, Condenser-Größe,
  1 vs. 2 parallele Runden.
- Läuft nur, wenn der Besitzer den Pod ohnehin gestartet hat; startet nie selbst einen Pod.

### 4.4 Hänger erkennen
- Loop markiert eine Runde als `stuck`, wenn (a) N Zyklen keine neuen Events,
  (b) wiederholt identische Fehlermeldungen, oder (c) Iterationslimit erreicht
  ohne Bericht. Dann pausieren/beenden, Bericht erzeugen, Aufgabe `attempts+1`.

---

## Phase 5 — Besitzer zuerst: GPU-Teilung

### 5.1 Priorität für Besitzer-Anfragen (B6)
- runpod: vLLM mit `--scheduling-policy priority` starten (Verfügbarkeit in der
  eingesetzten vLLM-Version prüfen) und im Controller für `/agent/v1` ein
  `priority`-Feld mit niedrigerer Priorität als für `/v1`, `/chat/v1`,
  `/code/v1` setzen.
- Fallback, falls nicht verfügbar: Controller hält bei Besitzer-Traffic neue
  Agent-Requests kurz zurück (Semaphore, max. Wartezeit), statt auf den
  2-Minuten-Cron zu warten.
- Loop: bei aktivem Besitzer höchstens **eine** Agentenrunde laufen lassen.
- **Abnahme:** Controller-Tests, dass Agent-Requests das Priority-Feld bekommen
  und Besitzer-Requests nicht; Messung der Besitzer-Latenz bei 2 laufenden Runden.

### 5.2 Parallelität adaptiv
- Zweite (Ideen-)Runde nur starten, wenn (a) der Ideen-Backlog nicht leer ist
  oder Besitzer-Ideen offen sind und (b) das Recherche-Kontingent
  (`consume_research_quota`, 20/Tag) nicht aufgebraucht ist. Sonst eine
  Engineering-Runde mit voller GPU.
- Messen (4.3), ob 2 parallele Runden bei `max_num_seqs: 2` mehr Ergebnis/Stunde
  bringen als eine.

### 5.3 Budget und Zeitfenster
- `config/autonomy.json` erweitern: `max_gpu_hours_per_day`,
  `allowed_windows` (z. B. nachts), `max_rounds_per_pod_session`.
  Loop respektiert die Werte, Admin-UI (`AutonomyPage.tsx`) kann sie setzen.
- Bei Budget-Ende: Wrapup-Runde + Pod-Stop wie bei Idle.

---

## Phase 6 — Sicherheit der Automatisierung (Vorschläge, 🔒 `deploy/**`)

- **Allowlist-Proxy:** `github.com`, `raw.githubusercontent.com`,
  `codeload.github.com` erlauben Download beliebigen Codes. Vorschlag: für PyPI
  einen lokalen Wheel-Cache/Mirror (z. B. `devpi` oder vorab gebaute Wheels
  im Image) und GitHub nur über das Gateway; Proxy dann entweder nur PyPI oder
  komplett aus. Rundenprompt entsprechend (1.4).
- Prüfen, dass von OpenHands gestartete Arbeitscontainer ebenfalls nur im
  `agent-isolated`-Netz hängen (offener Punkt aus `docs/AUTONOMY_LOOP.md`).
- Tokens im Agent-Container minimieren: `JARVIS_AGENT_REQUEST_TOKEN` ist nötig,
  aber auf die Agent-Endpunkte begrenzt – Test ergänzen, dass er keinen
  Admin-/Owner-Endpunkt öffnet.

---

## Phase 7 — Features, die noch fehlen (nach Nutzen sortiert)

1. **Aufgabe aus dem Chat an den Agenten geben** – Skill in
   `assistant_domain.py`: „Jarvis, gib dem Agenten die Aufgabe …“ →
   `autonomy_tasks` (Status `open`, `source=owner`). Rückmeldung im Chat, wenn
   die Aufgabe fertig/blockiert ist.
2. **Diff-Review im Admin-UI** – eingereichte Patches (4.1) mit Diff-Ansicht,
   Testergebnis und „PR anlegen / ablehnen“-Buttons; ersetzt das Springen
   zwischen Canvas, GitHub und Admin.
3. **Benachrichtigung bei Besitzerfrage** – bei `owner_question` oder
   `blocked` eine Push-Benachrichtigung über das vorhandene Notification-System
   (optional E-Mail via Resend), statt nur Log-Eintrag.
4. **Morgendlicher Agenten-Report** – „Was hat der Agent seit gestern gemacht?“
   als Jarvis-Briefing-Baustein (aus den Rundenberichten, kurz, TTS-tauglich).
5. **Automatischer, freigegebener Loop-Rollout** – Timer, der Drift erkennt
   (1.6) und nach einem Klick im Admin-UI `install_loop.sh` mit Backup/Rollback ausführt.
6. **Eskalation an ein stärkeres Modell** – Aufgaben, die 2× scheitern,
   als „braucht stärkeres Modell“ markieren (für eine Claude-/Cloud-Session
   durch den Besitzer), statt weitere GPU-Stunden zu verbrennen.
7. **Lernschleife** – Merge/Ablehnung eines Agent-PRs zurück in die Aufgabe
   schreiben; im Discovery-Modus Aufgabentypen mit hoher Erfolgsquote bevorzugen.

---

## Phase 8 — Doku-Hygiene

- `runpod/docs/CURRENT_STATUS.md` auf den echten Stand bringen (B11) oder durch
  einen Verweis auf eine aktuelle Statusseite ersetzen.
- `CLAUDE.md` (jarvis): Hinweis ergänzen, dass Agenten zuerst
  `docs/agent/CONTEXT.md` lesen; Duplikat `proxmox.ts` in der Strukturliste entfernen.
- Eine einzige Autonomy-Doku als Quelle (jarvis `docs/AUTONOMY_LOOP.md`), die
  runpod-Version verweist nur darauf.

---

## Empfohlene Reihenfolge der PRs

| Schritt | PR | Aufwand | Abhängig von |
|---|---|---|---|
| 1 | 1.1 Pod-Zyklus + Session-Adoption | S | – |
| 2 | 1.2 Wrapup + 1.3 Aufräumen | S | 1 |
| 3 | 1.5 Konfiguration + 1.6 Drift | S | – |
| 4 | 2.1 CONTEXT.md + 2.5 verify/find-Skripte + 2.3 Prompt-Reihenfolge | M | – |
| 5 | 2.2 Condenser/Iterationen konfigurierbar | S | 3 |
| 6 | 3.1 Backlog + 3.2 Rundenbericht | L | 4 |
| 7 | 4.1 submit-patch | M | 6 |
| 8 | 4.2 Metriken (runpod + jarvis) | M | 6 |
| 9 | 5.1 Priorität (runpod) + 5.2/5.3 | M | 8 |
| 10 | 4.3 Eval-Suite, dann 2.4 Modell/Kontext-Experimente | M | 8 |
| 11 | 1.4 + Phase 6 als Vorschlags-PRs (🔒) | S | – |
| 12 | Phase 7 Features, Phase 8 Doku | je S–M | 6, 7 |

**Erfolgskriterium des Gesamtplans:** gemessen über eine Woche Betrieb steigen
„gemergte Agent-PRs pro GPU-Stunde“ und sinken „Tokens pro erfolgreicher
Aufgabe“ gegenüber dem heutigen Stand; keine Runde wird durch Idle-Stop
abgeschnitten; Besitzer-Anfragen warten nicht mehr spürbar hinter Agenten.
