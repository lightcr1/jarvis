"""Offline tests for the Open WebUI idea bridge (stdlib only, no network)."""

from __future__ import annotations

import urllib.error

from integrations.openwebui import idea_inbox as bridge


def test_only_explicit_forms_forwarded():
    assert "Business-Idee:" in bridge.submit_idea("Schau dir das Dashboard an", token="t")
    assert "Business-Idee:" in bridge.submit_idea("Kurzes Update", token="t")
    body = bridge.submit_idea("Business-Idee: Lokale Marktanalyse", token="t")
    assert "JARVIS_AGENT_REQUEST_TOKEN ist nicht konfiguriert" not in body


def test_missing_token_blocks_without_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network must not be called without token")
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert "nicht konfiguriert" in bridge.submit_idea("Projektidee: CLI-Doku", token=None)


def test_network_payload_and_failure_handling(monkeypatch):
    captured = {}

    class FakeResponse:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout=15):
        captured["url"] = request.full_url
        captured["headers"] = {k: v for k, v in request.header_items()}
        captured["body"] = request.data
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    body = bridge.submit_idea("Jarvis-Idee: Admin-Zentrale verbessern", base_url="http://gw:8100", token="request-only")
    assert "Idee notiert" in body
    assert captured["url"] == "http://gw:8100/agent/ideas"
    assert any(k.lower() == "x-jarvis-agent-request-token" and v == "request-only"
               for k, v in captured["headers"].items())
    assert "platform" in captured["body"].decode()

    class FakeError(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("http://gw:8100", 401, "unauthorized", None, None)

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(FakeError()))
    assert "konnte nicht gespeichert" in bridge.submit_idea("Idee: Test", base_url="http://gw:8100", token="t")
