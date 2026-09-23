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
Prozess-, RAM- und CPU-Limits. Das verhindert keinen normalen ausgehenden
Netzwerkverkehr aus OpenHands; fuer echte Egress-Allowlisten ist eine separate
Firewall/Proxy-Grenze ausserhalb des vom Agenten beschreibbaren Repos noetig.

Die festen Pfade und LAN-Endpunkte in diesem Skript sind installationsspezifisch.
Die Laufzeitdateien (`autonomy-state.json`, Log), `.env`-Dateien und Tokens
duerfen nicht versioniert oder als Agenten-Secrets verfuegbar gemacht werden.
## Projektfreigaben (API und Grenzen)

Jarvis bietet einen getrennten, SQLite-gestuetzten Freigabekern fuer genaue
Projektart, Ziel und Operation: Agenten koennen mit einem **eigenen**
`JARVIS_AGENT_REQUEST_TOKEN` unter `POST /agent/grants/requests` anfragen und
unter `GET /agent/grants/requests/{id}` den Status lesen. Fehlt der Token, sind
beide Agentenendpunkte geschlossen. Der Besitzer kann nach Anmeldung in der
Admin-UI unter Autonomie oder via `/admin/agent-grants` genehmigen, ablehnen
und widerrufen. Ideen koennen vom Besitzer (`POST /admin/ideas`) oder Agenten
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
bereitstellen. Admin-Sessions darf der Agent nie erhalten. Ist ein Request-Token auf dem
Loop-Host eingerichtet und die Jarvis-API erreichbar, liest der Loop bis zu
fuenf offene Besitzerideen und gibt sie als **unvertraute Daten** an die
naechste OpenHands-Runde weiter, ohne das Token ins Modell-Prompt zu kopieren.
Ohne Token funktioniert der bisherige Repo-/Issue-Workflow weiter, aber die
Admin-Queue ist fuer den Loop nicht sichtbar. Das Token muss erst separat
bereitgestellt werden; PR/Merge tun das nicht.

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
fehlgeschlagener GitHub-Aufruf eine neue Freigabe. Private Repos und das
Erzeugen/Pushen eines Branches brauchen weiterhin separat bereitgestellte
Zugriffe und einen geprueften Schreibpfad.
Business-Projekte brauchen einen definierten Auftrag und fuer finanzielle oder
oeffentliche Aktionen separate Einzelfreigaben.
