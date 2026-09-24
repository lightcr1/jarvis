# Dockerfile: allowlist-proxy
#
# Kleiner, strikt auf eine Allowlist beschraenkter HTTP(S)-Proxy fuer den
# Agent-Container (Jarvis). Der Proxy laeuft DUAL-HOMED: im internen
# `agent-isolated`-Netz (nur dort erreicht ihn der Agent) und im externen
# `runpod-internal`-Netz (nur dort hat er Internet). Er blockt alles ausser
# einer festen Liste erlaubter Hostnamen.
#
# Sicherheit:
# - HTTPS (CONNECT) wird anhand des angefragten Ziel-Hostnamen geprueft und der
#   Tunnel NUR zu den aufgeloesten, erlaubten IPs der Allowlist geoeffnet.
# - Keine MITM-Entschluesselung, kein Logging der Inhalte, kein generischer
#   Durchgriff auf andere Ziele (DNS-Rebinding wird durch erneute Pruefung
#   verhindert).
FROM python:3.12-alpine

RUN apk add --no-cache ca-certificates && \
    addgroup -S prox && adduser -S -G prox prox

WORKDIR /app
COPY allowlist_proxy.py /app/allowlist_proxy.py

USER prox
EXPOSE 3128
ENTRYPOINT ["python", "-u", "/app/allowlist_proxy.py"]
