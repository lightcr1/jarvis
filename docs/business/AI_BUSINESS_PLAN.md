# Business-Plan: Ein von KI betriebenes Kleinunternehmen

Stand: 2026-09-26 · Zielgruppe: der Besitzer **und** die ausführende KI (Jarvis,
Claude o. a.). Das Dokument ist gleichzeitig Plan und Betriebsanleitung.

**Ziel des Besitzers:** Jarvis sucht sich selbständig eine tragfähige
Geschäftsmöglichkeit und übernimmt Validierung, Aufbau und Betrieb möglichst
vollständig: Produkt, Vermarktung, Vertrieb, Support, Wartung und Auswertung.
Der Besitzer muss weder eine Idee liefern noch jeden Arbeitsschritt anstoßen.

Dafür erteilt der Besitzer einen widerrufbaren Geschäftsauftrag mit Zielen,
ausgeschlossenen Branchen, Gesamt- und Monatsbudget, nutzbaren Konten,
Aktionsrechten und Eskalationsgrenzen. Innerhalb dieses Rahmens wählt Jarvis
die Idee selbst, arbeitet weiter und wechselt bei erfüllten Abbruchkriterien
zur nächsten zulässigen Idee. Der Auftrag wird serverseitig geprüft und setzt
T3-Regeln nicht außer Kraft. Dieser Plan beschreibt das Ziel; er erteilt noch
keine Freigabe für reale Ausgaben, Konten oder Veröffentlichungen.

> **Ehrliche Vorbemerkung.** Eine KI kann Produkt, Betrieb, Support, Inhalte und
> Auswertung weitgehend übernehmen. Sie kann aber **nicht** Rechtsträger sein:
> Firma, Verträge, Steuern, Bankkonto und Haftung liegen beim Besitzer.
> Ziel ist möglichst wenig operative Arbeit für den Besitzer. Der tatsächliche
> Zeitaufwand wird gemessen, statt pauschal 1–3 Stunden pro Woche zu versprechen.
> Jarvis bevorzugt Modelle ohne regelmäßige persönliche Verkaufsgespräche oder
> manuelle Lieferung durch den Besitzer. Einnahmen sind nicht garantiert.
> Deshalb ist der Plan in Phasen mit harten Abbruchkriterien aufgebaut.

---

## 1. Welches Geschäftsmodell passt?

### Auswahlkriterien (KI-tauglich, sicher, wenig Kapital)

| Kriterium | Warum |
|---|---|
| **Digital lieferbar** | Keine Lager, keine Logistik, keine Vor-Ort-Arbeit |
| **Wiederkehrende Einnahmen** | Abo statt Einzelverkauf: planbar, wenig Vertriebsaufwand pro Franken |
| **Klar abgegrenztes Produkt** | Die KI kann Qualität testen, der Support bleibt beherrschbar |
| **Geringes Schadensrisiko** | Keine Medizin, Rechtsberatung, Finanzberatung, Sicherheitsleistungen oder Personendaten in Masse |
| **B2B vor B2C** | Weniger Kunden, höhere Preise, weniger Support-Volumen, weniger Rückbuchungen |
| **Nutzt vorhandene Stärken** | Eigener KI-Stack, Jarvis-Plattform mit Stripe-Abos, Plänen und Benutzerverwaltung, Kenntnisse in Self-Hosting und Home-Automation |

### Ausgeschlossen
- KI-generierte Massen-Inhalte (SEO-Farmen, Content-Spam), Dropshipping,
  Trading/Krypto, Affiliate-Spam. Diese Modelle sind stark gesättigt, rechtlich
  oder plattformseitig riskant und verlieren schnell an Wert.
- Alles, was im Namen des Besitzers Kunden etwas verspricht, das die KI nicht
  überprüfbar liefern kann.

### Beispiele als Suchstart (Jarvis entdeckt und bewertet eigene Kandidaten)

| # | Modell | Beispiel | Aufwand Besitzer | Einschätzung |
|---|---|---|---|---|
| A | **Nischen-Micro-SaaS** | Kleines Web-Tool für eine enge Zielgruppe in CH/DACH (z. B. Dokumente/QR-Rechnungen verarbeiten, Terminerinnerungen, Berichte aus Home-Assistant-Daten für Vermieter) | niedrig nach dem Aufbau | Möglicher Kandidat; Bedarf und Automatisierbarkeit zuerst belegen |
| B | **Produktisierter Dienst** „Private KI für KMU“ | Festpreis-Paket: datenschutzfreundlicher KI-Assistent auf Basis der eigenen Plattform, gehostet oder vor Ort | mittel (Verkaufsgespräche) | Höchster Preis pro Kunde, nutzt den eigenen Stack direkt. Menschlicher Kontakt nötig |
| C | **Digitale Vorlagen/Pakete** | Home-Assistant-Blueprints, Self-Hosting-Stacks, Automations-Pakete | sehr niedrig | Wenig Umsatz, gut als Einstieg und Marketing für A/B |

**Auswahl durch Jarvis:** A/B/C sind Beispiele, keine vorgeschriebene Auswahl
oder feste Reihenfolge. Jarvis recherchiert weitere Möglichkeiten und wählt
nach belegtem Bedarf, Kosten, Automatisierbarkeit und geringem Besitzeraufwand.
Ein Modell mit menschlichen Verkaufsgesprächen kommt nur infrage, wenn der
Besitzer diese übernehmen möchte. Jarvis dokumentiert Auswahl und Belege in
der Ideen-Queue und startet im Geschäftsauftrag selbst die nächste Phase.

---

## 2. Rollen: wer macht was

### Besitzer (Mensch) – nur das, was rechtlich oder menschlich nötig ist
- Firma gründen/führen (z. B. Einzelfirma), Bank- und Stripe-Konto, Steuern.
- Geschäftsauftrag, Budget und Rechte festlegen bzw. widerrufen; verbleibende
  kritische Freigaben und rechtliche Entscheidungen treffen.
- Menschliche Interaktion soweit nötig: Identitätsprüfungen, Unterschriften,
  persönliche Ausnahmen und Eskalationen.
- Monatlicher Review (30–60 Min.): Zahlen, Entscheidungen, Kurs.

### KI-Team (Jarvis + bei Bedarf stärkere Cloud-Modelle)

Jarvis übernimmt die Geschäftsleitung: Chancen suchen, Idee auswählen, Rollen
koordinieren, Phasen fortführen und unwirtschaftliche Ansätze beenden. Jede
Aktion bleibt an Geschäftsauftrag, Budget und ihre Freigabestufe gebunden.

| Rolle | Aufgaben | Rechte (Stufe) |
|---|---|---|
| **Researcher** | Markt, Konkurrenz, Kundenprobleme, Preise | T0 (Web-Recherche über Gateway) |
| **Builder** | Produkt entwickeln, testen, deployen | T1 in eigenem Repo/Sandbox, Deploy T2 |
| **Operator** | Monitoring, Backups, Updates, Kosten | T1/T2 |
| **Support** | Kunden-E-Mails beantworten (nur aus Wissensbasis), Tickets | Entwürfe T1, Versand T2 mit stehender Freigabe für Standardfälle, alles andere T3 |
| **Marketer** | Landingpage, Doku, Beiträge, Newsletter-Entwürfe | Entwürfe T1, Veröffentlichung T3 |
| **Controller** | Einnahmen/Ausgaben, Budget-Wächter, Wochenbericht | T0 auf Stripe-/Kosten-Daten (Lesezugriff) |
| **Auditor** | Prüft die Arbeit der anderen Rollen: Stichproben, Richtlinien, Fehler | T0, kann Stopp auslösen |

Für schwierige Aufgaben (Architektur, heikle Kundenkommunikation, Rechtstexte
vorbereiten) darf die KI ein stärkeres Cloud-Modell nutzen, **ohne**
Kundendaten zu übertragen (siehe 5.4).

---

## 3. Phasen mit Budget und Abbruchkriterien

| Phase | Dauer | Ziel | Budget max. | Weiter nur wenn … |
|---|---|---|---|---|
| **0 Recherche** | 2–3 Wochen | 3 Ideen tief bewerten: Problem, Zielgruppe, Zahlungsbereitschaft, Konkurrenz, Aufwand | ~CHF 0–50 | Eine Idee mit belegtem Problem und identifizierbaren Käufern |
| **1 Validierung** | 3–4 Wochen | Jarvis erstellt und betreibt Landingpage, Warteliste, Umfragen oder zulässige Vorverkaufstests; persönliche Gespräche nur optional | ~CHF 50–200 (Domain, kleine Werbung) | ≥ 20 qualifizierte Anmeldungen oder ≥ 3 Vorverkäufe/Absichtserklärungen |
| **2 MVP** | 4–8 Wochen | Kleinstes zahlbares Produkt, Stripe-Abo, Doku, Support-Wissensbasis | ~CHF 100–300 (Hosting, Mail, Tools) | ≥ 5 zahlende Kunden in 4 Wochen nach Launch |
| **3 Betrieb & Wachstum** | laufend | Retention, Automatisierung, organisches Marketing | Ausgaben ≤ 30 % des Umsatzes | Monatlich positiver Deckungsbeitrag nach 6 Monaten |
| **Stopp** | – | Idee einstellen, Kunden sauber informieren, Kosten beenden | – | Abbruchkriterium verfehlt → nächste Idee aus Phase 0 |

Planungsrahmen für das Startkapital: **CHF 200–600**. Das genehmigte Budget muss
in Jarvis als serverseitig durchgesetzte Grenze hinterlegt werden (5.2).

Die Beträge sind Planungswerte, kein bereits genehmigtes Budget. Jarvis prüft
die Kriterien anhand gespeicherter Belege und entscheidet im Geschäftsauftrag
selbst über Fortsetzung, Anpassung oder Abbruch. Ein Ideenwechsel setzt den
verbrauchten Gesamtetat nicht zurück. Fehlende Rechte und notwendige
T3-Aktionen erzeugen konkrete Freigaben in der eigenen App.

---

## 4. Wie die KI das Geschäft täglich führt

### 4.1 Betriebsrhythmus
- **Täglich (automatisch):** Chancen und Nachfrage prüfen, nächste Schritte
  planen, Produkt und Vertrieb weiterentwickeln, Monitoring, Support im Rahmen
  der Freigaben, Fehler beheben und Kennzahlen aktualisieren.
- **Wöchentlich:** Bericht an den Besitzer (Push + Chat in der eigenen App), maximal eine Seite:
  Umsatz, Kosten, Kunden (neu/gekündigt), Top-3-Probleme, 1–3 Entscheidungen, die
  der Besitzer treffen muss.
- **Monatlich:** Review mit dem Besitzer. Danach werden Plan und Backlog angepasst.

### 4.2 Entscheidungsregeln
- Die KI entscheidet selbst: Ideenwahl, Prioritäten, Phasenübergänge nach
  belegten Kriterien, Produkt-Details, Bugfixes, Doku, Support nach Wissensbasis
  und zulässige Experimente im freigegebenen Gesamtbudget.
- Die KI fragt: Preisänderungen, neue Kanäle, öffentliche Aussagen,
  Rückerstattungen über Schwellwert, neue Tools mit Kosten, alles Rechtliche.
- Die KI stoppt und meldet: Sicherheitsvorfall, ungewöhnliche Zahlungen,
  Beschwerden mit rechtlichem Bezug, Budget zu 80 % verbraucht.

### 4.3 Qualität
- Jede Kundenantwort basiert auf der Wissensbasis. Findet die KI keine Antwort
  darin, geht die Anfrage an den Besitzer und wird **nicht** improvisiert.
- Jeder Release läuft durch Tests und Eval (wie beim Jarvis-Repo).
- Der Auditor zieht wöchentlich Stichproben aus Support und Änderungen.

---

## 5. Sicherheit und Langfristigkeit

### 5.1 Getrennte Welt fürs Business
- Eigene Business-E-Mail, eigenes Stripe-Konto, eigenes GitHub-Repo, eigene
  Domain und eigenes Hosting. **Kein** Zugriff auf private Konten des Besitzers.
- Eigene Zone in Jarvis (`business-<name>`) mit eigenen Capabilities und
  eigenem Budget. Der Not-Aus stoppt auch diese Zone.
- Zugewiesene Business-Zugangsdaten darf Jarvis über den Credential-Tresor
  für Logins, APIs und autorisierte Abläufe verwenden. Verschlüsselte
  Speicherung, Zuweisung je Dienst/Tool, widerrufbare Nutzung und Audit ohne
  Geheimnisse; das Modell sieht Referenzen. Siehe Assistenten-Plan, 4.3.

### 5.2 Geld
- Die KI kann **kein Geld bewegen**. Einnahmen laufen über Stripe, Auszahlungen
  gehen auf das Konto des Besitzers.
- Ausgaben nur über eine virtuelle Karte mit Monatslimit, die der Besitzer
  verwaltet. Jede neue wiederkehrende Ausgabe ist T3.
- Stripe-Zugriff für die KI mit einem **Restricted Key**: lesen, Abos und
  Kunden verwalten, **keine** Auszahlungen, keine Kontoeinstellungen.
  Rückerstattungen bis zu einem Schwellwert per stehender Freigabe, darüber T3.
- Das Budget verfolgt der Server (echte Ausgaben aus Kartenumsätzen/Stripe),
  nicht die KI selbst.

### 5.3 Recht (CH, vom Besitzer zu prüfen)
- Rechtsform: Für den Start genügt typischerweise eine Einzelfirma. Die
  Eintragungspflicht ins Handelsregister und die MWST-Pflicht hängen von
  Umsatzschwellen ab. Vor dem Launch mit Treuhand/Behörde klären.
- AGB, Datenschutzerklärung (revDSG, bei EU-Kunden DSGVO), Impressum: Die KI
  bereitet Entwürfe vor, die der Besitzer von einer Fachperson oder einem
  geprüften Generator prüfen lässt.
- Transparenz: Kunden sollen wissen, dass Support und Produkt KI-gestützt sind.
- Keine Verarbeitung sensibler Personendaten im MVP.

### 5.4 Daten und Modelle
- Kundendaten bleiben auf der eigenen Infrastruktur, beim selbst gehosteten
  Modell. Cloud-Modelle bekommen nur anonymisierte oder öffentliche Inhalte
  (Code ohne Kundendaten, Marketingtexte, Recherche).
- Backups täglich, Wiederherstellung monatlich testen.

### 5.5 Robustheit
- Die KI dokumentiert alles im Business-Repo (`docs/`): Entscheidungen,
  Runbooks, Wissensbasis. So kann ein anderes Modell (oder ein Mensch) jederzeit
  übernehmen.
- Keine Abhängigkeit von einem einzigen Modell. Die Rollen-Prompts und Evals
  sind modellunabhängig.
- Abhängigkeiten minimal halten, einfache Standard-Technik.

---

## 6. Was in Jarvis dafür noch fehlt

| # | Baustein | Zweck |
|---|---|---|
| 1 | **Business-Zone** (Projekt + Zone + Budget + Capabilities pro Geschäft) | Trennung vom Rest, eigenes Budget |
| 2 | **Stripe-Lesezugriff + Restricted Key** als Capability | Controller-Rolle, Kennzahlen |
| 3 | **Support-Postfach-Workflow** (E-Mail lesen → Entwurf → Versand nach Stufe) mit Wissensbasis | Support-Rolle |
| 4 | **Serverseitiges Ausgaben-Tracking** (Kartenumsätze/Rechnungen erfassen) | echtes Budget statt Selbstauskunft |
| 5 | **Web-Deploy für Business-Projekte** (eigene Domain, Health-Check, Rollback) | Builder/Operator |
| 6 | **Wochenbericht Business** im Briefing | Besitzer-Aufwand minimieren |
| 7 | **Rollen-Prompts + Evals pro Rolle** (Support-Antwortqualität, Richtlinien) | Qualität, Modellwechsel |
| 8 | **Geschäftsauftrag und selbständiger Arbeitszyklus** | Ziele, Rechte, Konten, Gesamtbudget und Abbruchregeln speichern; Ideen selbst suchen und wählen, Phasen anhand von Belegen fortführen und Arbeit nach Neustarts fortsetzen |
| 9 | **Besitzeraufwand messen** | Eingriffe, benötigte Minuten, selbständig erledigte Aufgaben und Eskalationsgründe im Wochenbericht ausweisen |

---

## 7. Erster konkreter Schritt

Nach Erteilung des Geschäftsauftrags startet Jarvis **Phase 0** als Ideen-Runde
(Grundlage im Autonomy-Loop vorhanden):

1. Selbst Chancen recherchieren und mindestens drei geeignete Ideen bewerten:
   Problem, Käufer, Zahlungsbereitschaft mit Quellen, Konkurrenz,
   Automatisierbarkeit, Besitzeraufwand, Risiken, Kosten und Validierungstest.
2. Selbst eine Idee innerhalb der Vorgaben auswählen, Entscheidung und Belege
   dokumentieren und den Besitzer in der App informieren.
3. Validierung planen und im genehmigten Rahmen durchführen. Nur konkret
   fehlende Rechte oder T3-Aktionen zur Freigabe vorlegen.
4. Bei belegtem Erfolg MVP und Betrieb selbst weiterführen; andernfalls den
   Versuch geordnet beenden und im verbleibenden Budget neu auswählen.

**Abnahme:** Ein kompletter Zyklus von selbst gefundener Idee über Auswahl und
Validierung bis zum begründeten Weiterführen oder Abbruch läuft ohne tägliche
Arbeitsanweisungen. Fortschritt, Ausgaben, Ergebnisse und Ausnahmen stehen in
der App; der Bericht misst den verbleibenden Besitzeraufwand. Menschliche
Pflichten und kritische Einzelfreigaben bleiben sichtbar.
