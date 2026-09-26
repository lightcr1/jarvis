# Plan: Jarvis als persönlicher Assistent für (fast) alles

Stand: 2026-09-26 · Nachfolger von `docs/JARVIS_ASSISTANT_PLAN.md` (Plattform,
Freigaben, Executor – umgesetzt). Auftrag für einen Coding-Agenten. Es gelten
dieselben Arbeitsregeln (ein PR pro Aufgabe gegen `dev`, Tests, 🔒 = nur
Vorschlags-PR).

Ziel ist ein eigener, überall erreichbarer Assistent auf dem eigenen Server.
Der Besitzer nutzt die eigene App für Text und Sprache, unterwegs auch über
mit dem Handy verbundene Kopfhörer oder einen einzelnen Ohrhörer. Jarvis kennt
den Besitzer, denkt mit und erledigt Aufgaben. Vor der Erweiterung seiner
Handlungsrechte müssen die Sicherheitslücken in Abschnitt 0 geschlossen werden.

---

## 0. Befunde aus dem letzten Review (zuerst)

- **0.1 Chat-Tools ohne Capability-Zuordnung.** `send_email_draft`,
  `proxmox_vm_action`, `proxmox_lxc_action`, `restart_service`,
  `control_device` usw. haben keine `capability` und landen als
  `unclassified.action` auf T2. E-Mail-Versand ist laut `capabilities.json` aber
  `email.send` = **T3**. Alle Schreib-Tools explizit zuordnen und einen Test
  schreiben, der verlangt, dass jedes Tool mit `risk != READ` eine Capability hat.
  Stehende Freigaben auf `unclassified.action` verbieten (wie `*`).
- **0.2 T3 im Chat ohne zweiten Faktor.** TOTP wird nur in der Admin-Freigabe-API
  geprüft. Ein T3-Tool, das im Chat mit „Ja“ bestätigt wird, braucht keinen Code.
  Deshalb T3 im Chat nie per „Ja“ bestätigen, sondern immer eine Freigabe-Anfrage
  mit TOTP (Push/Admin) auslösen. Sobald der Executor oder Proxmox aktiv ist, TOTP
  für T3 **erzwingen** statt optional.
- **0.3 Pod-Budget vertraut der Anfrage.** `within_budget` liest `spent_chf`
  und `estimated_chf` aus den Parametern der Anfrage. Diese Werte stammen vom
  Anfragenden. Stattdessen den Verbrauch serverseitig aus den Controller-Metriken
  bzw. den Pod-Laufzeiten (GPU-Sekunden × Preis) berechnen und die Schätzung aus
  Profil und geplanter Dauer ableiten.
- **0.4 TOTP-Härtung.** Secret mit `secret_crypto` verschlüsselt speichern,
  bereits verwendete Zeitschritte pro Benutzer sperren (Replay-Schutz).

---

## 1. Überall erreichbar

| # | Baustein | Umsetzung |
|---|---|---|
| 1.1 | **Eigene Jarvis-App und weltweiter Serverzugriff** | Textchat, Sprachgespräche, Aufgaben, Ergebnisse und Freigaben in einer App; authentifizierter, verschlüsselter Zugriff auf den eigenen Server über WLAN und Mobilfunk. Telegram und andere Messenger sind nicht Teil dieses Plans |
| 1.2 | **Mobile App, Audio und Push** | Bestehende Web-App/PWA als Grundlage und Zwischenstufe; Ziel ist eine eigene mobile App mit Mikrofon-/Audioanbindung, Push und Verbindungsstatus. Kopfhörer bzw. einzelner Ohrhörer sind mit dem Handy verbunden und dienen als Mikrofon und Audioausgabe |
| 1.3 | **Sprachassistent zu Hause** | Wakeword auf Zielhardware validieren (V1-Punkt), ein Gerät pro Raum optional |
| 1.4 | **Ein Gesprächsfaden über Sprache, Text und Geräte** | Gesprochenes Anliegen im App-Chat sehen, per Text oder auf einem anderen angemeldeten Gerät fortsetzen. Aufgaben laufen auf dem Server weiter, auch wenn die App geschlossen ist |

**Sprachbedienung:** Aufnahme in der App starten, mit Jarvis sprechen, Antworten
über den gewählten Audioausgang hören und unterbrechen können. Headset-Taste,
Wakeword, Hintergrundbetrieb und Bedienung bei gesperrtem Handy sind auf den
gewählten Mobilplattformen zu prüfen; sie sind Abnahmeziele, keine bereits
zugesicherten PWA-Fähigkeiten. Verbindungsverlust klar anzeigen und Aktionen
nach Wiederverbindung nicht doppelt ausführen. T3-Freigaben bleiben an die
konkrete Aktion und den zweiten Faktor in der App gebunden.

Dies konkretisiert das gemeinsame Interface aus
`docs/v2/planning/ROADMAP_V2.md` und ersetzt für diesen Plan dessen optionale
Messenger-Brücken. Bestehenden Chat, Sprachoberfläche und Push wiederverwenden.

## 2. Jarvis kennt den Besitzer

- **2.1 Profil-Gedächtnis:** strukturiertes Profil (Vorlieben, Routinen,
  wichtige Personen, Orte, Geräte, laufende Projekte) auf Basis von
  `memory_store`. Jarvis schlägt Einträge vor („Soll ich mir merken, dass …?“),
  der Besitzer bestätigt. Einsehbar und löschbar in den Einstellungen.
- **2.2 Kontakte:** kleines Adressbuch (CardDAV-Sync optional) als Kontext für
  E-Mails, Termine und Erinnerungen.
- **2.3 Persönliche Wissensbasis:** Notizen, Dokumente aus dem Datei-Drive,
  wichtige E-Mails werden indexiert (lokale Embeddings) und sind im Chat
  durchsuchbar („Was stand im Mietvertrag zur Kündigungsfrist?“).
- **2.4 Datenklassen:** `public` / `personal` / `sensitive` pro Quelle. Nur
  `public` darf an Cloud-Modelle, `personal` nur mit Einverständnis pro Anfrage,
  `sensitive` nie. Das ist Voraussetzung für 5.2.

## 3. Mitdenken (proaktiv)

- **3.1 Morgen-Briefing** erweitern: Termine, wichtige E-Mails (klassifiziert),
  offene Aufgaben, Wetter/Verkehr, Status der Agent-Aufgaben, Business-Kennzahlen.
- **3.2 Fristen-Wächter:** erkennt Fristen und Zusagen in E-Mails und
  Dokumenten (Rechnungen, Kündigungen, Termine) und schlägt Erinnerungen oder
  Aufgaben vor.
- **3.3 Nachfass-Automatik:** „Du wolltest X bis Freitag antworten“ bzw. „Y hat
  seit 5 Tagen nicht geantwortet – nachfassen?“
- **3.4 Routinen:** wiederkehrende Abläufe als Playbooks (existieren), die
  Jarvis vorschlägt, wenn er Muster erkennt („Du schaltest jeden Abend …, soll
  ich das automatisieren?“).
- **3.5 Ruhe-Regeln:** Nicht-stören-Zeiten, Bündelung, Dringlichkeitsstufen,
  damit Proaktivität nicht nervt.

## 4. Dinge erledigen

- **4.1 Browser-Agent in der Sandbox:** Headless-Browser (Playwright) als
  Sandbox-Image. Damit kann Jarvis recherchieren, Formulare ausfüllen,
  Preise vergleichen und Bestellungen **vorbereiten**. Absenden von
  Bestellungen, Zahlungen und Formularen im Namen des Besitzers ist T3 mit
  Screenshot und Zusammenfassung in der Freigabe. Logins nur über einen
  Credential-Tresor (4.3), niemals im Modellkontext.
- **4.2 E-Mail-Assistent:** Posteingang zusammenfassen, Antwortentwürfe im Stil
  des Besitzers, Versand nach Stufe (Standardantworten per stehender Freigabe,
  neue Empfänger T3).
- **4.3 Credential-Tresor für Tools/Plugins:** Zugangsdaten pro Plugin und
  Website in `integration_credentials`, Zuweisung in der App. Vom Besitzer für
  einen Dienst und Auftrag übergebene Zugangsdaten darf Jarvis tatsächlich
  verwenden: anmelden, APIs aufrufen und erlaubte Aufgaben erledigen. Übergabe
  über eine geschützte Tresor-Eingabe statt über den normalen Chatverlauf;
  Dienst, Zweck und zugewiesene Tools bleiben einsehbar und widerrufbar.
  Executor, Browser und Integrationen beziehen die Zugangsdaten zur Laufzeit
  aus dem verschlüsselten Tresor, das Modell arbeitet mit Referenzen.
  Passwörter und Tokens dürfen nicht in Modellkontext, Logs oder Screenshots
  erscheinen. Innerhalb des Auftrags braucht nicht jeder Login eine erneute
  Erlaubnis. Aktionsrechte und T3-Freigaben gelten weiterhin; notwendige
  MFA-/Captcha-Schritte gehen bei Bedarf an den Besitzer in der App.
- **4.4 Dokumente:** Rechnungen/Belege aus E-Mails automatisch in den
  Datei-Drive ablegen, benennen und für die Steuer sortieren.
- **4.5 Einkauf/Haushalt:** Einkaufsliste (existiert) mit Browser-Agent
  verbinden: Warenkorb vorbereiten, Freigabe, bestellen.

## 5. Qualität der Antworten

- **5.1 Modell-Routing nach Aufgabe:** kleines lokales Modell für Klassifikation
  und Rückfragen, großes selbst gehostetes Modell für Chat und Agent, optional ein
  Cloud-Modell für schwere Aufgaben, **nur** mit Daten der Klasse `public` (2.4).
  Die Routing-Entscheidung ist im Chat sichtbar.
- **5.2 Feedback-Schleife:** 👍/👎 und „So hätte ich es gewollt“ an jeder Antwort
  → Lernfall → Eval-Suite (existiert) → messbare Verbesserung.
- **5.3 Assistenz-Eval:** 30–50 echte Alltagsanliegen des Besitzers
  (anonymisiert) als Testset: Termin eintragen, E-Mail beantworten, Recherche,
  Home-Automation, Aufgabe delegieren. Jede Änderung an Prompt, Router oder
  Modell läuft dagegen.

## 6. Selbständiger Business-Betrieb durch Jarvis

Die Bausteine aus `docs/business/AI_BUSINESS_PLAN.md`, Abschnitt 6
(Business-Zone, Stripe-Lesezugriff, Support-Workflow, Ausgaben-Tracking,
Business-Deploy, Wochenbericht, Rollen-Evals), sind Teil dieses Plans und kommen
nach Abschnitt 4.

Jarvis soll Geschäftsmöglichkeiten selbst suchen, bewerten, auswählen,
validieren, umsetzen und betreiben. Der Besitzer gibt Ziele, Budget und
Berechtigungen als widerrufbaren Geschäftsauftrag vor. Innerhalb dieses
Rahmens arbeitet Jarvis selbständig weiter und berichtet über die App;
manuelle Ideenauswahl und tägliche Arbeitsanweisungen sind kein Regelfall.
Phasenübergänge, Abbruchkriterien und Besitzerpflichten stehen im Business-Plan.

---

## 7. Reihenfolge

| # | Aufgabe | Aufwand |
|---|---|---|
| 1 | 0.1–0.4 Review-Befunde | S |
| 2 | 1.1, 1.2, 1.4 Eigene App, sicherer Fernzugriff, mobiler Sprachdialog, Push und gemeinsamer Verlauf | L |
| 3 | 2.1 + 2.4 Profil-Gedächtnis + Datenklassen | M |
| 4 | 3.1 + 3.5 Briefing erweitern + Ruhe-Regeln | S |
| 5 | 4.2 + 4.3 E-Mail-Assistent + Credential-Tresor | M |
| 6 | 2.3 Persönliche Wissensbasis | M |
| 7 | 3.2 + 3.3 Fristen-Wächter + Nachfassen | M |
| 8 | 4.1 Browser-Agent in der Sandbox | L |
| 9 | 5.1–5.3 Routing, Feedback, Assistenz-Eval | M |
| 10 | Business-Bausteine (Abschnitt 6) | L |
| 11 | 4.4, 4.5, 3.4, 1.3 | je S–M |

**Abnahme:** Der Besitzer nutzt Jarvis eine Woche lang als ersten
Ansprechpartner in der eigenen App: Text und Sprache über Handy, Kopfhörer
oder einzelnen Ohrhörer, über WLAN und Mobilfunk. Gerätewechsel, App-Schließen,
Audio-Unterbrechung und Verbindungsverlust sind geprüft. Mindestens 70 % der Anliegen werden ohne
Nacharbeit erledigt oder sauber delegiert. Jede T3-Aktion lief über eine
Freigabe mit TOTP. Der Wochenbericht zeigt die Zahlen.
