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
stoppen; sie startet oder provisioniert keinen Pod. `NeverConfirm` in OpenHands
ist **keine** Freigabe fuer externe Aktionen. Netzwerk-/Dateizugriff, GitHub-
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

Die festen Pfade und LAN-Endpunkte in diesem Skript sind installationsspezifisch.
Die Laufzeitdateien (`autonomy-state.json`, Log), `.env`-Dateien und Tokens
duerfen nicht versioniert oder als Agenten-Secrets verfuegbar gemacht werden.
Dauerhafte Projektfreigaben und externe Aktionen erfordern einen separaten,
technisch erzwungenen und widerrufbaren Freigabe-Workflow; dieser Loop allein
stellt ihn nicht bereit.
