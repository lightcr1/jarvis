# Lokaler Jarvis-Autonomy-Loop

Versionierte Quelle: `scripts/agent/autonomy_loop.py`.
Aktuell installierte Kopie auf der Jarvis-VM:
`/home/media/jarvis-openhands/autonomy/autonomy_loop.py` (ausserhalb dieses Repos).
Der Cron-Aufruf verweist **auf die installierte Kopie**, nicht auf das Git-Repo.
Ein Merge aktualisiert den laufenden Dienst deshalb **nicht automatisch**.

## Verhalten

Solange `config/autonomy.json` nicht `enabled: false` enthaelt und der Besitzer
den Pod bereits gestartet hat, startet der Loop OpenHands-Runden im Jarvis-
Workspace. Der Auftrag verweist auf `AGENTS.md` und `docs/GOALS.md`: direkte
Besitzerauftraege vor eigenen Verbesserungen; Assistenz, Plattform und
Business-Ideen planen und nur im tatsaechlich erlaubten Umfang umsetzen.
Bei fehlenden Rechten eine konkrete Frage im Aktivitaetslog hinterlassen.

Der Loop pausiert eine laufende eigene Runde bei Benutzeraktivitaet, nimmt sie
spaeter wieder auf und schliesst nach der Idle-Frist mit einer Wrapup-Runde ab.
Die bisherige Implementierung versucht dann den Pod ueber den Controller zu
stoppen; sie startet oder provisioniert keinen Pod. Die **versionierte Quelle**
fordert in OpenHands `ConfirmRisky` an; eine auf Besitzerfreigabe wartende Runde
sendet keinen Agent-Heartbeat, damit der bezahlte Pod nicht unbeschraenkt durch
Warten am Leben bleibt. Die aktuell installierte Kopie kann noch `NeverConfirm`
verwenden; vor einem Rollout muss das OpenHands-API-Verhalten von `ConfirmRisky`
getestet werden. Auch eine Bestaetigung im Agent-Canvas ist **keine**
technische Freigabe fuer externe Aktionen. Netzwerk-/Dateizugriff, GitHub-
Schutz und Policies muessen ausserhalb des Prompts durchgesetzt werden.

## Aenderung und Installation

Fuer die Inbetriebnahme aller Gates gibt es eine Schritt-fuer-Schritt-Anleitung
in `docs/HUMAN_TODO_GRANTS.md` (runpod-Repo, PR #44). Der sichere Austausch
der installierten Loop-Kopie erfolgt mit `scripts/agent/install_loop.sh`
(`--dry-run` zeigt erst den Diff, ohne Aenderungen). Ein Merge installiert den
Loop weiterhin nicht automatisch.

1. Aenderung im Repo reviewen (inklusive Policy- und Sicherheitstests). Auf
   dem Zielhost die installierte Version gegen die neue Quelle vergleichen.
2. Offline pruefen: `python3 -m py_compile scripts/agent/autonomy_loop.py` und
   `python3 -m pytest -q tests/test_autonomy_loop.py` (kein Pod erforderlich).
3. Erst nach Freigabe eine Kopie der bestehenden installierten Datei sichern,
   Runden beenden oder sicher pausieren, dann die getestete Datei in den oben
   genannten Installationspfad uebernehmen. Dateirechte und Cron-Pfad pruefen.
4. Die naechste Cron-Runde und das lokale Log kontrollieren; bei Fehler die
   gesicherte Datei zurueckspielen. Keine Runpod-Ressource fuer den Test starten.

Der OpenHands-Compose-Draft mountet nur den Jarvis-Clone statt des gesamten
Projekt-Elternverzeichnisses, entfernt alle Linux-Capabilities und setzt
Prozess-, RAM- und CPU-Limits. Agent Canvas haengt nur im internen
`agent-isolated`-Netz ohne direkten Internet- oder Runpod-Netzzugang. Ein
separater, read-only und capability-loser Nginx-Gateway ist dual-homed und
leitet ausschliesslich `/agent/v1/` an den Controller weiter; alle anderen
Pfade liefern 403. Der OpenHands-LLM-Endpunkt muss deshalb
`http://inference-gateway:8080/agent/v1` sein. Fuer den Zugriff auf das Canvas
aus dem LAN publiziert der zusaetzliche `canvas-edge` (nginx, dual-homed)
ausschliesslich Host-Port `OPENHANDS_EDGE_PORT` (Standard 8001) und leitet nur
an `http://jarvis-openhands:8000` weiter; der Agent selbst publiziert keinen
Host-Port. Grund: Interne Docker-Netze publizieren auf diesem Host keine Ports
und Host-Port 8000 ist durch `jarvis.service` (Jarvis-Web) belegt. Der
Autonomy-Loop spricht OpenHands deshalb unter `http://10.10.40.100:8001` an.
Das begrenzt den Compose-
Container, muss aber praktisch verifiziert werden, weil OpenHands je nach
Execution-Backend weitere Arbeitscontainer starten kann. Diese duerfen weder
andere Netzwerke noch Docker-Socket/Hostzugriff erhalten. Eine Host-Firewall
bleibt als aeussere, vom Agenten nicht beschreibbare zweite Grenze empfohlen.

Die festen Pfade und LAN-Endpunkte in diesem Skript sind installationsspezifisch
und lassen sich ohne Codeaenderung konfigurieren. Der Loop liest die Werte in
dieser Reihenfolge: eingebaute Defaults < `autonomy-loop.env` neben der
installierten Kopie (Pfad per `AUTONOMY_LOOP_ENV` ueberschreibbar) <
Prozess-Umgebung. Eine Vorlage mit allen Schluesseln und Defaults liegt unter
`config/autonomy-loop.example.env`. Fuer TLS kann `CONTROLLER_CA_FILE` auf die
selbst erzeugte `tls/server.crt` (runpod-Repo) zeigen; ohne diesen Wert faellt
der Loop auf `CERT_NONE` zurueck und schreibt eine Warnung ins Log.

Der Versions-Drift zwischen installierter Kopie und versionierter Quelle ist
sichtbar: der Loop schreibt beim Start seinen SHA256 in den State
(`loop_sha256`), die Admin-UI (`AgentMonitorPage`) zeigt installierten Hash und
Repo-Hash und warnt bei Abweichung. `scripts/agent/install_loop.sh --check`
vergibt Exit 1 bei Drift (fuer einen spaeteren Timer) und prueft nichts weiter.
Die Laufzeitdateien (`autonomy-state.json`, Log), `.env`-Dateien und Tokens
duerfen nicht versioniert oder als Agenten-Secrets verfuegbar gemacht werden.
## Projektfreigaben (API und Grenzen)

Jarvis bietet einen getrennten, SQLite-gestuetzten Freigabekern fuer genaue
Projektart, Ziel und Operation: Agenten koennen mit einem **eigenen**
`JARVIS_AGENT_REQUEST_TOKEN` unter `POST /agent/grants/requests` anfragen und
unter `GET /agent/grants/requests/{id}` den Status lesen. Fehlt der Token, sind
beide Agentenendpunkte geschlossen. Der Besitzer kann nach Anmeldung in der
Admin-UI unter Autonomie oder via `/admin/agent-grants` genehmigen, ablehnen
und widerrufen. Entscheidungen sind an die in `JARVIS_OWNER_USER_ID`
konfigurierte Besitzer-ID gebunden: Ohne diese Variable sind alle
Besitzer-Entscheidungen gesperrt (HTTP 503), andere Admin-Konten erhalten 403.
Ideen koennen vom Besitzer (`POST /admin/ideas`) oder Agenten
(`POST /agent/ideas`) stammen; die Warteschlange (`GET /agent/ideas`) liefert
Besitzerideen zuerst. Das Einreichen oder Merken einer Idee erteilt **keine**
Ausfuehrungsrechte. Maximal drei unbewertete Agentenideen pro 24 Stunden
verhindern Vorschlags-Spam. Besitzerideen koennen aktuell ueber die Admin-
Oberflaeche oder mit einer ausdruecklichen Nachricht im Jarvis-App-Chat
(`Business-Idee: ...`, `Projektidee: ...`, `Jarvis-Idee: ...`) erfasst werden.
Dieser Pfad verlangt eine eingeloggte Besitzer-Session; normale freie
Chat-Nachrichten und Open WebUI werden nicht automatisch in die Queue
uebernommen. Ein Auftrag im Chat bleibt trotzdem ein Besitzerauftrag und hat
Vorrang. Das selbststaendige Suchen von Chancen ist
ein Rundenauftrag, keine garantierte externe Marktrecherche ohne Webzugang. Freigaben verfallen spaetestens nach 30 Tagen; Ausnahmen fuer
Geld, Veroeffentlichung, Nachrichten, Loeschung oder Sicherheitsregeln sind
nicht ueber diesen allgemeinen Grant freigebbar. Die Anfragen liegen unter
`JARVIS_AGENT_GRANTS_PATH` (Standard `/var/lib/jarvis/agent_grants.sqlite3`),
getrennt vom Repository. Token und Datenbank nicht in den Agenten-Workspace
mounten; nur einen begrenzten Request-Token ueber einen sicheren Kanal
bereitstellen. Admin-Sessions darf der Agent nie erhalten. Derselbe zufaellige
`JARVIS_AGENT_REQUEST_TOKEN` muss im Jarvis-Backend und im OpenHands-Compose-
Secret gesetzt werden; er ist nur fuer Anfragen, Status, exakt genehmigte
Einmalausfuehrungen und begrenzte Recherche gueltig. Der typisierte Client
`scripts/agent/jarvis_gateway.py` kapselt diese Aufrufe. Der isolierte
Inference-Gateway erlaubt dafuer nur explizite `/jarvis-agent/...`-Muster und
blockiert Admin-, Chat- und beliebige HTTP-Pfade. Tokenleak oder Request-Spam
bleiben Risiken: Alle Agenten-Endpunkte sind pro Request-Token gedrosselt
(Anfragen schreibender Typen 10–15/min, Suche 30/min, Status 60/min, Einmal-
Ausfuehrung 5/min). Token regelmassig rotieren, Audit ueberwachen.
Vor der Aktivierung der vollen Kette prueft `scripts/agent/preflight_grants.py`
lesend (liest `/home/media/jarvis.env` selbst per robustem Parser – kein `source`,
kein `sudo`; `--env` fuer andere Dateien): Besitzer-ID, Request-Token und die
Trennung von Service-Tokens, die
Grants-Datenbank, den Git-Index auf verdaechtige Secrets sowie aktive
billbare Runpod-Aktionen; fehlt etwas, endet das Skript mit Fehlercode.
Ist ein Request-Token auf dem
Loop-Host eingerichtet und die Jarvis-API erreichbar, liest der Loop bis zu
fuenf offene Besitzerideen und gibt sie als **unvertraute Daten** an die
naechste OpenHands-Runde weiter, ohne das Token ins Modell-Prompt zu kopieren.
Ohne Token funktioniert der bisherige Repo-/Issue-Workflow weiter, aber die
Admin-Queue ist fuer den Loop nicht sichtbar. Das Token muss erst separat
bereitgestellt werden; PR/Merge tun das nicht.

Groessere Vorhaben koennen als Projektrahmen mit bis zu 20 exakt benannten,
unkritischen Operationen und maximal 30 Tagen Laufzeit beantragt werden. Nach
der Besitzerfreigabe akzeptiert `authorize()` diese Operationen ohne einzelne
Rueckfrage; Ziel, Operationen und Laufzeit sind sichtbar und der gesamte Rahmen
ist widerrufbar. Wildcards und reservierte Kategorien bleiben verboten. Eine
Projektfreigabe erweitert niemals automatisch das technische Toolset: Nur
Gateways, die `authorize()` selbst vor der Nebenwirkung aufrufen, koennen sie
nutzen.

Aktiver Not-Aus (`jarvis_engine.emergency_stop_enabled`) sperrt zusaetzlich die
Agenten-API: Ausfuehrung, Schreibaktionen und Recherche antworten dann 503;
Anfragen und Status bleiben fuer den Besitzer lesbar. Neue Provider folgen der
Checkliste in `docs/INTEGRATIONS_GUIDE.md`; optional kann Open WebUI
ausdrueckliche `...-Idee:`-Formulare ueber `integrations/openwebui/idea_inbox.py`
an die Queue weiterreichen (nicht automatisch fuer freie Chat-Nachrichten).

**Wichtig:** Dieser Kern ist noch keine Freigabe fuer Shell, GitHub, E-Mail
oder Zahlungen. Ein neues ausfuehrendes Tool muss im vertrauenswuerdigen
Gateway erst Aktion und Ziel selbst klassifizieren und `authorize()` vor jeder
Nebenwirkung aufrufen; ein vom Agenten gemeldetes Label ist nicht verlaesslich.
Der Jarvis-App-Tool-Registry-Pfad prueft fuer die Service-Rolle zusaetzlich
RBAC, Not-Aus und einen konkreten Grant vor internen `create_task`- und
`complete_task`-Aktionen. Andere schreibende Tools der Service-Rolle bleiben
in diesem Pfad gesperrt. Das ist nur ein Pilot: OpenHands-Terminal, E-Mail,
Home Assistant, GitHub und fremde Dienste benutzen diesen Pfad nicht und
werden dadurch nicht eingeschraenkt oder freigeschaltet. Ein vorhandener
Grant ersetzt keine separaten externen Sicherheitsgrenzen. Fuer **oeffentliche
GitHub-Repos** gibt es nun einen eng begrenzten Lese-Endpunkt
`GET /agent/repositories/{owner}/{repo}/metadata`: festes GitHub-API-Ziel,
keine Weiterleitungen, kein GitHub-Token, keine beliebigen URLs. Voraussetzung
ist ein aktiver Besitzergrant fuer `kind=other_project`,
`target=owner/repo` und `operation=read_metadata`. Ergebnisdaten sind
unvertraute Recherche, keine neuen Anweisungen. Klonen, Aendern und Pushen sind dadurch **nicht** freigegeben. Fuer das
Erstellen eines PR aus einem bereits vorhandenen Branch gibt es einen separaten
Einmalpfad: Jarvis reicht Repository, Titel, Body, Head und Base ein; die UI
zeigt Inhalt und SHA-256-Digest. Erst nach Besitzerfreigabe kann genau dieser
Request einmal ausgefuehrt werden. Jede Aenderung oder Wiederholung braucht
eine neue Freigabe. Der serverseitige `JARVIS_GITHUB_WRITE_TOKEN` wird nie an
den Agenten gegeben und muss als Fine-Grained Token nur fuer explizit erlaubte
Repos konfiguriert werden; ohne Token schlaegt die Aktion geschlossen fehl.
Da die Freigabe vor dem API-Aufruf atomar verbraucht wird, braucht auch ein
fehlgeschlagener GitHub-Aufruf eine neue Freigabe. Eine weitere
Einmalaktion ist der E-Mail-Versand (`request-email` im Agent-Client): Jarvis
reicht Empfaenger, Betreff und Text ein; die Admin-UI zeigt den vollstaendigen
Inhalt und den Digest. Nach Besitzerfreigabe wird genau dieser Verlauf einmal
ueber das bestehende E-Mail-Konto des Besitzers gesendet; Wiederholung oder
Abweichung brauchen eine neue Freigabe. Ohne konfiguriertes Besitzer-E-Mail-
Konto schlaegt die Ausfuehrung geschlossen fehl. Empfaengeradresse, Laengen
und Einzeiligkeitsregeln fuer den Betreff werden vor dem Speichern geprueft.
Innerhalb eines genehmigten Projektrahmens kann die Operation `create_branch`
einen neuen `agent/*`-Branch aus `dev` oder `main` erzeugen. Mit der getrennten
Operation `write_branch_file` kann Jarvis ueber den typisierten Gateway einzelne
Textdateien bis 256 KiB in einen bereits vorhandenen `agent/*`-Branch
schreiben. Zielrepo, Operation, Branchformat und Pfad werden serverseitig
geprueft; `AGENTS.md`, `.github/`, `deploy/`, Environment-, Credential- und
Secret-Pfade sind immer blockiert. Das serverseitige GitHub-Token bleibt
verborgen. Danach kann der digest-gebundene Einmalpfad einen PR erstellen.
Binaere Dateien, beliebige Git-Befehle und direkte Pushes nach `dev`/`main`
sind nicht Teil dieses Gateways. Private Repos
funktionieren nur, wenn der serverseitige Fine-Grained Token genau dafuer
berechtigt wurde.
Fuer Business-Recherche kann ein genehmigter Projektrahmen der Art
`business_research` die Operation `web_search` fuer ein genaues Projektziel
freigeben. Der Backend-Gateway spricht ausschliesslich die feste Brave-Search-
API mit dem serverseitigen `JARVIS_BRAVE_SEARCH_TOKEN` an, blockiert Redirects,
begrenzt Query und Ergebniszahl, reserviert vor dem Provider-Aufruf eine harte
Quote von 20 Suchen je Projekt und rollierenden 24 Stunden und gibt Ergebnisse
als unvertraute Daten aus.
Ohne konfigurierten Suchanbieter bleibt die Suche geschlossen. Recherche ist
keine Erlaubnis, Personen zu kontaktieren, Inhalte zu veroeffentlichen oder
Geld auszugeben; finanzielle und oeffentliche Aktionen brauchen separate
Einzelfreigaben und einen eigenen typisierten Provider-Gateway.
