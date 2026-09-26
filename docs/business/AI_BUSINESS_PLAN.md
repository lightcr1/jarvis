# Business-Plan: Ein von KI betriebenes Kleinunternehmen

Stand: 2026-09-26 · Zielgruppe: der Besitzer **und** die ausführende KI (Jarvis,
Claude o. a.). Das Dokument ist gleichzeitig Plan und Betriebsanleitung.

> **Ehrliche Vorbemerkung.** Eine KI kann Produkt, Betrieb, Support, Inhalte und
> Auswertung weitgehend übernehmen. Sie kann aber **nicht** Rechtsträger sein:
> Firma, Verträge, Steuern, Bankkonto und Haftung liegen beim Besitzer. Ein
> „Business ohne Aufwand“ gibt es nicht. Realistisch ist ein Geschäft, bei dem der
> Besitzer nach der Aufbauphase **ca. 1–3 Stunden pro Woche** für Freigaben,
> Kundengespräche und Pflichten aufwendet. Einnahmen sind nicht garantiert.
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

### Kandidaten (Jarvis bewertet sie in Phase 0)

| # | Modell | Beispiel | Aufwand Besitzer | Einschätzung |
|---|---|---|---|---|
| A | **Nischen-Micro-SaaS** | Kleines Web-Tool für eine enge Zielgruppe in CH/DACH (z. B. Dokumente/QR-Rechnungen verarbeiten, Terminerinnerungen, Berichte aus Home-Assistant-Daten für Vermieter) | niedrig nach dem Aufbau | **Favorit.** Skaliert, und die KI kann es bauen und betreiben |
| B | **Produktisierter Dienst** „Private KI für KMU“ | Festpreis-Paket: datenschutzfreundlicher KI-Assistent auf Basis der eigenen Plattform, gehostet oder vor Ort | mittel (Verkaufsgespräche) | Höchster Preis pro Kunde, nutzt den eigenen Stack direkt. Menschlicher Kontakt nötig |
| C | **Digitale Vorlagen/Pakete** | Home-Assistant-Blueprints, Self-Hosting-Stacks, Automations-Pakete | sehr niedrig | Wenig Umsatz, gut als Einstieg und Marketing für A/B |

**Empfohlene Strategie:** C als günstiger Markttest und Reichweiten-Aufbau,
parallel A validieren. B nur, wenn der Besitzer Verkaufsgespräche führen möchte.
Die endgültige Wahl trifft der Besitzer nach Phase 0.

---

## 2. Rollen: wer macht was

### Besitzer (Mensch) – nur das, was rechtlich oder menschlich nötig ist
- Firma gründen/führen (z. B. Einzelfirma), Bank- und Stripe-Konto, Steuern.
- Freigaben: Budget, Veröffentlichungen, Preise, AGB/Datenschutz, neue Kanäle.
- Menschliche Interaktion: Kundengespräche, Partner, Eskalationen.
- Monatlicher Review (30–60 Min.): Zahlen, Entscheidungen, Kurs.

### KI-Team (Jarvis + bei Bedarf stärkere Cloud-Modelle)
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
| **1 Validierung** | 3–4 Wochen | Landingpage + Warteliste/Vorverkauf, 10–20 Gespräche (Besitzer) oder Umfragen | ~CHF 50–200 (Domain, kleine Werbung) | ≥ 20 qualifizierte Anmeldungen oder ≥ 3 Vorverkäufe/Absichtserklärungen |
| **2 MVP** | 4–8 Wochen | Kleinstes zahlbares Produkt, Stripe-Abo, Doku, Support-Wissensbasis | ~CHF 100–300 (Hosting, Mail, Tools) | ≥ 5 zahlende Kunden in 4 Wochen nach Launch |
| **3 Betrieb & Wachstum** | laufend | Retention, Automatisierung, organisches Marketing | Ausgaben ≤ 30 % des Umsatzes | Monatlich positiver Deckungsbeitrag nach 6 Monaten |
| **Stopp** | – | Idee einstellen, Kunden sauber informieren, Kosten beenden | – | Abbruchkriterium verfehlt → nächste Idee aus Phase 0 |

Gesamtes Startkapital realistisch **CHF 200–600**. Das Budget ist in Jarvis als
harte Grenze hinterlegt (5.2) und nicht nur als Richtwert.

---

## 4. Wie die KI das Geschäft täglich führt

### 4.1 Betriebsrhythmus
- **Täglich (automatisch):** Monitoring, Support-Eingang sortieren und
  beantworten (im Rahmen der Freigaben), Fehler beheben, Kennzahlen aktualisieren.
- **Wöchentlich:** Bericht an den Besitzer (Push + Chat), maximal eine Seite:
  Umsatz, Kosten, Kunden (neu/gekündigt), Top-3-Probleme, 1–3 Entscheidungen, die
  der Besitzer treffen muss.
- **Monatlich:** Review mit dem Besitzer. Danach werden Plan und Backlog angepasst.

### 4.2 Entscheidungsregeln
- Die KI entscheidet selbst: Produkt-Details, Bugfixes, Doku, Support nach
  Wissensbasis, Experimente im freigegebenen Budget.
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

---

## 7. Erster konkreter Schritt

Jarvis startet **Phase 0** als Ideen-Runde (existiert bereits im Autonomy-Loop):
1. Für die Kandidaten A/B/C und bis zu zwei eigene Vorschläge je eine
   Bewertung (1 Seite): Problem, Zielgruppe, Zahlungsbereitschaft (mit Quellen),
   Konkurrenz, Aufwand, Risiken, Kosten, erster Validierungstest.
2. Ergebnis in die Ideen-Queue (Admin → Autonomie) mit Empfehlung.
3. Der Besitzer wählt eine Idee und gibt das Budget für Phase 1 frei.
