integrations/openwebui
======================

Optionales Bruecken-Tool fuer **Open WebUI**: Leitet eine ausdrueckliche
Idee in die Jarvis-Ideenqueue weiter (`/agent/ideas`).

Wichtig
-------

* Nur **explizite** Formulare (`Business-Idee:`, `Projektidee:`,
  `Jarvis-Idee:`, `Idee:`) werden weitergeleitet; normale Chat-Nachrichten
  sollen **nicht** automatisch in der Queue landen.
* Das Tool braucht den **Request-only**-Token (`JARVIS_AGENT_REQUEST_TOKEN`);
  niemals Admin-, Modell- oder GitHub-Tokens hier eintragen.
* Eine Idee ist **keine** Freigabe und kein Ausfuehrungsauftrag – sie landet
  nur zur Bewertung in der Warteschlange (Admin-UI -> Autonomie).
* Sauberer und einfacher ist der Weg ueber den eingeloggten Jarvis-App-Chat
  (siehe docs/AUTONOMY_LOOP.md). Diese Vorlage ist fuer Benutzer, die nur
  Open WebUI verwenden.

Einbau
------

1. Open WebUI: Admin -> Workspace -> Tools -> **New**.
2. Inhalt von `idea_inbox.py` einfuegen, Name z. B. `jarvis_idea_inbox`.
3. Das Tool fuer die Benutzerrolle freigeben (Rechte vergeben).
4. Die Umgebungsvariable `JARVIS_AGENT_REQUEST_TOKEN` muss im
   Open-WebUI-Prozess gesetzt sein (gleicher Wert wie im Backend);
   alternativ den Platzhalter in der Datei ersetzen (dann aber nicht
   versionieren).
5. Aufruftext: `Jarvis-Idee: ...` im Chat eingeben.
