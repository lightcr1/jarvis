# Umsetzung: persönlicher Assistent und KI-Business

Quellen: `JARVIS_PERSONAL_ASSISTANT_PLAN.md`, `business/AI_BUSINESS_PLAN.md`
(Stand 2026-09-26). Dies ist ein Arbeitsstand, keine Live-Abnahme und kein
Geschäftsauftrag. Bestehende Funktionen werden je Paket geprüft und erweitert,
nicht pauschal als fertig gezählt.

## Arbeitsweise

Eigener Arbeitsstand, `agent/*`-Branches, thematische PRs gegen `dev`, relevante
Tests. Sicherheits-, Berechtigungs-, Credential-, Billing- und Infrastruktur-
Änderungen benötigen Owner-Review. Keine realen Ausgaben, Kontoaktionen,
Veröffentlichungen oder Produktionsdeployments aus diesem Plan ableiten.

## Reihenfolge und Status

| Paket | Inhalt | Status |
|---|---|---|
| 0.1 | Schreib-Tools explizit klassifizieren; Blanket-Grants verhindern | Implementiert, Regressionstests grün; Owner-Review ausstehend |
| 0.2 | T3 nie durch Chat-Ja; aktionsgebundene Admin-Freigabe mit TOTP | Implementiert (TOTP-gebundene, digest- und nutzergebundene Admin-Freigabe; Snapshot bindet die Aktion); Owner-Review ausstehend |
| 0.3 | Pod-Budget aus vertrauenswürdigen Laufzeit-/Profildaten | Implementiert (serverseitige Pod-Sitzungen + Profil-Stundensatz + geplante Dauer, Fail-Closed; Controller-Reconciliation); Owner-Review ausstehend |
| 0.4 | Verschlüsseltes TOTP-Secret, atomarer Replay-Schutz | Implementiert (Fernet-verschlüsselt, dateibasierter Lock, monotone Zeitschritt-Sperre); Owner-Review ausstehend |
| 1 | App, mobile Sprache/Push, gemeinsamer Verlauf, sichere Wiederverbindung | Teilweise: PWA + Tailscale-Runbook + sichtbare Verbindungsanzeige (`Live`/`Reconnecting`/`Offline`) ohne Aktionswiederholung umgesetzt; native iOS/Android-App und echte Geräteabnahme offen |
| 2 | Bestätigtes Profil-Gedächtnis und Datenklassen | Offen |
| 3 | Briefing und Ruhe-Regeln | Offen |
| 4 | E-Mail-Assistent und dienst-/toolgebundener Credential-Tresor | Offen |
| 5 | Persönliche Wissensbasis | Offen |
| 6 | Fristen und Nachfassen | Offen |
| 7 | Browser-Sandbox und konkrete T3-Freigaben | Offen |
| 8 | Routing, Feedback, Assistenz-Evals | Offen |
| 9 | Business-Zonen, Auftrag, Budget, Arbeitszyklus und Rollen | Offen |
| 10 | Dokumente, Einkauf, Routinen, Wakeword | Offen |

## Paket 0.1

Alle mutierenden Pilot-Tools tragen eine registrierte Capability. E-Mail-Versand
ist `email.send` (T3), Infrastruktur und Gerätesteuerung sind explizit T2.
`save_memory_note` war fälschlich READ und ist nun WRITE. Für Gedächtnis,
Aufgabenabschluss und Kalender bleiben konservative T2-Freigaben bestehen;
Aufgabenanlage und E-Mail-Entwürfe verwenden die vorhandenen T1-Capabilities.

`unclassified.action` und `*` dürfen weder neu als stehende Freigabe angelegt
werden noch als Altbestand wirken. Die zentrale Freigabeprüfung lehnt beide
auch dann ab, wenn ein Aufrufer einen Grant direkt übergibt.

Wichtig: Die T3-Klassifikation allein schließt den Chat-Ja-Bypass noch nicht;
dieser wird in Paket 0.2 behandelt. Dieses Paket deshalb nicht als vollständige
Sicherheitsfreigabe für neue Handlungsrechte verstehen.

## Externe Abnahmen / Entscheidungen

- **`JARVIS_SECRET_KEY` muss gesetzt sein**, sonst schlägt die 2FA-Einrichtung
  bewusst fehl (503) und ein bereits aktivierter Faktor kann nicht deaktiviert
  werden. Dies ist Fail-Closed: ohne Schlüssel wird 2FA nie stillschweigend
  abgeschaltet.
- T3-Freigaben sind jetzt an Capability, Nutzer, Parameter-Digest und einen
  Moment-Snapshot gebunden und werden nach einmaliger Nutzung verbraucht.
  Ein „Ja“ im Chat reicht nicht mehr.
- Pod-Budget (`JARVIS_POD_MONTHLY_BUDGET_CHF`) wird server-seitig geführt:
  `JARVIS_POD_COST_PER_HOUR_CHF` und `JARVIS_POD_PLANNED_HOURS` sind nötig,
  sonst wird ein Start fail-closed abgelehnt. Anfrage-Parameter zählen nicht.
  Hinweis: Die Agent-Grants-Deps verdrahten jetzt `totp_store`, `pod_control`
  und `pod_budget_store` – vorher fehlten sie, wodurch T3-Freigaben in
  Produktion nie genehmigbar gewesen wären.
- Mobile Zielplattformen und echte Headset-/Hintergrundtests bleiben erforderlich.
- Geschäftsauftrag mit Budget, erlaubten Konten, Branchen und Eskalationsgrenzen
  muss der Besitzer explizit erteilen. Kein Default-Budget aktivieren.
- Rechtsform, Verträge, Steuern und Haftung bleiben beim Besitzer.
- Messziele (eine Woche Assistenz, 70 % ohne Nacharbeit; vollständiger
  Business-Validierungszyklus) benötigen echte, dokumentierte Abnahmeläufe.
