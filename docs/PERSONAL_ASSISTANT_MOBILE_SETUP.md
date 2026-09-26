# Jarvis unterwegs: Handy, Sprache, Push, immer erreichbar

Ziel (Plan `JARVIS_PERSONAL_ASSISTANT_PLAN.md`, Abschnitt 1): Jarvis von überall
erreichen — iOS, Android und Web — per Text und Sprache, mit Push und einem
durchgehenden Gesprächsfaden über Geräte hinweg. Dieses Dokument trennt klar:
**was im Code steckt** und **was der Besitzer einmalig einrichten muss**.

> Ehrliche Grenzen vorab: Eine Browser-Web-App (PWA) kann auf iOS **nicht im
> Hintergrund dauerhaft mithören** und im gesperrten Zustand nicht aufnehmen.
> „Immer hören“ funktioniert in der PWA nur bei geöffneter App; echtes
> Always-on im Hintergrund braucht eine native App oder ein Heimgerät mit
> Mikrofon (z. B. Raspberry Pi mit Wakeword). Das ist eine Plattformgrenze,
> kein Codefehler.

## Was bereits im Code steckt

- **PWA/Web-App** mit Textchat, Sprachaufnahme/-wiedergabe, Aufgaben und
  Freigaben (`frontend/`).
- **Push** (Web Push, VAPID) mit Abo-Verwaltung (`/notifications/...`).
- **Live-Status-Kanal** (`/ws/status`) mit automatischem Reconnect.
- **Verbindungsanzeige** in der App: `Live` / `Reconnecting` / `Offline`
  (`frontend/src/components/ConnectionBadge.tsx`). Aktionen werden bei nicht
  verbundener App **nicht** automatisch nachgesendet, damit ein Reconnect
  nichts doppelt ausführt.
- **Wakeword**-Erkennung serverseitig (`jarvis/wakeword_engine.py`) und
  Auto-Start der Aufnahme im Orb-Screen.

## 1.1 Sicherer Fernzugriff mit Tailscale

Tailscale baut ein privates, verschlüsseltes Netz zwischen deinen Geräten — der
Jarvis-Server ist dann aus dem Mobilfunknetz erreichbar, ohne Ports im Router zu
öffnen. Empfohlen, weil keine öffentliche Angriffsfläche entsteht.

**Auf dem Jarvis-Server:** es gibt bereits ein Skript dafür.
```bash
sudo bash scripts/setup_tailscale.sh
```
Das installiert Tailscale, meldet den Server an und zeigt die `100.x.y.z`-Adresse
sowie die nächsten Schritte. Danach ist Jarvis unter `https://<tailscale-ip>/`
erreichbar (TLS über `scripts/deploy_local.sh`, das auf `:443` lauscht). Keine
Portfreigaben, keine öffentliche IP.

**Variante „nur im Tailnet, TLS von Tailscale“:** statt eines eigenen Zertifikats
kannst du `tailscale serve --bg --https=443 http://127.0.0.1:8100` nutzen. Beide
Wege liefern einen sicheren Kontext (nötig für Push und Mikrofon).

**Auf iOS/Android:**
1. Tailscale-App installieren, mit demselben Konto anmelden.
2. Danach die `https://<host>.<tailnet>.ts.net`-Adresse in Safari/Chrome öffnen.

**Web (Desktop/Notebook):** Tailscale installieren und dieselbe URL öffnen.

**Zugriff absichern:** `tailscale up --shields-up` verhindert eingehende
Verbindungen von außen; nur deine eigenen Geräte erreichen den Server. Das
Jarvis-Login bleibt zusätzlich erforderlich.

## 1.2 Als App installieren (PWA) + Push

**iOS (Safari):** Teilen → „Zum Home-Bildschirm“. Push funktioniert erst in der
**installierten** PWA und ab iOS 16.4.

**Android (Chrome):** Menü → „App installieren“ / „Zum Startbildschirm zufügen“.

**Push aktivieren:** in den Jarvis-Einstellungen die Benachrichtigungen
einschalten (nutzt `subscribeToPush`). Auf iOS erst nach der Installation und
nach Erteilen der Mitteilungs-Erlaubnis.

**Mikrofon:** Beim ersten Sprachvorgang fragt der Browser nach der
Mikrofon-Erlaubnis. Auf iOS nur bei geöffneter, aktiver App.

## 1.3 Wakeword / „immer hören“

- **In der PWA (Handy/Desktop, App geöffnet):** Der Orb-Screen nimmt nach dem
  Wakeword-Event automatisch auf. Das ist der Alltagsfall unterwegs.
- **Immer-an (Hintergrund):** braucht ein Gerät mit Mikrofon, auf dem der
  Wakeword-Dienst dauerhaft läuft (Server zu Hause, Raspberry Pi). Dort kann
  `JARVIS_WAKEWORD_ENGINE=openwakeword` dauerhaft hören und den Live-Status
  senden, den die App abonniert.

## 1.4 Ein Gesprächsfaden über Geräte

Chat-Sitzungen liegen serverseitig (`chat_history`). Dasselbe Konto auf Handy
und Desktop sieht dieselben Sitzungen; Aufgaben laufen auf dem Server weiter,
auch wenn die App geschlossen ist. Beim Wechsel/Wiederverbinden zeigt die
Verbindungsanzeige den Zustand, und der Live-Kanal verbindet sich automatisch
neu — **ohne** die letzte Aktion erneut auszuführen.

## Prüfliste (Abnahme)

- [ ] `tailscale status` zeigt Server und Handy im selben Tailnet.
- [ ] `tailscale serve status` liefert eine `https://...ts.net`-URL.
- [ ] Login auf iOS, Android und im Browser erfolgreich.
- [ ] PWA installiert; Push-Testnachricht kommt an (iOS: installiert + 16.4+).
- [ ] Spracheingabe unterwegs (Mobilfunk) liefert eine Antwort; Kopfhörer als
      Mikro/Ausgabe geprüft.
- [ ] App schließen und wieder öffnen: gleiche Sitzung, keine doppelte Aktion.
- [ ] Verbindungsverlust (Flugmodus) zeigt „Offline“, Wiederverbindung „Live“.

Diese Punkte sind echte Gerätetests des Besitzers; sie lassen sich nicht aus
dem Repository heraus abnehmen.
