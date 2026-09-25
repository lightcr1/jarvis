from fastapi import FastAPI
from fastapi.testclient import TestClient
from jarvis.agent_grants import AgentGrantStore
from jarvis.api_agent_grants import build_agent_grants_router
from jarvis.research_gateway import ResearchError, search_web


def test_search_validation_happens_before_network(monkeypatch):
    monkeypatch.setattr("urllib.request.build_opener", lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    for query, token in (("", "token"), ("x\nheader", "token"), ("x", "")):
        try: search_web(query, token)
        except ResearchError: pass
        else: raise AssertionError("invalid search accepted")


def test_research_requires_exact_project_scope(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "research.sqlite3"); calls = []
    monkeypatch.setattr("jarvis.api_agent_grants.search_web", lambda q, token, limit=5: calls.append((q, token, limit)) or [{"title": "result"}])
    app = FastAPI(); app.include_router(build_agent_grants_router({
        "agent_grant_store": store, "get_identity_session": lambda _: None, "normalize_role": lambda r:r,
        "agent_request_token": "agent", "github_write_token": "", "web_search_token": "server-search-token",
        "audit_admin_event": lambda *a: None,
    }))
    client = TestClient(app); headers={"X-Jarvis-Agent-Request-Token":"agent"}
    payload={"project_target":"business:market-a","query":"market demand","limit":3}
    assert client.post("/agent/research/search", headers=headers, json=payload).status_code == 403
    project=store.request_project(kind="business_research", target="business:market-a", title="Market A", operations=["web_search"])
    store.decide_project(project["id"], actor="owner", approve=True)
    response=client.post("/agent/research/search", headers=headers, json=payload)
    assert response.status_code == 200 and response.json()["untrusted"] is True
    assert calls == [("market demand", "server-search-token", 3)]
    payload["project_target"]="business:other"
    assert client.post("/agent/research/search", headers=headers, json=payload).status_code == 403


import json  # noqa: E402
from jarvis.research_gateway import search_searxng  # noqa: E402


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status = payload, status
    def read(self, n=-1):
        return self._p
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False


def _opener(payload, status=200):
    class _O:
        def open(self, req, timeout=None):
            return _Resp(payload, status)
    return lambda *a, **k: _O()


def test_searxng_parses_json_results(monkeypatch):
    payload = json.dumps({"results": [
        {"title": "T", "url": "https://x", "content": "C"},
    ]}).encode()
    monkeypatch.setattr("urllib.request.build_opener", _opener(payload))
    assert search_searxng("q", "http://searxng:8080", limit=3) == [
        {"title": "T", "url": "https://x", "description": "C"}]


def test_searxng_validates_url_and_query(monkeypatch):
    monkeypatch.setattr("urllib.request.build_opener",
                        lambda *a: (_ for _ in ()).throw(AssertionError("network")))
    for url in ("", "ftp://x", "searxng:8080"):
        try:
            search_searxng("q", url)
        except ResearchError:
            pass
        else:
            raise AssertionError("bad searxng url accepted")
    try:
        search_searxng("x\ny", "http://searxng:8080")
    except ResearchError:
        pass
    else:
        raise AssertionError("bad query accepted")


def test_searxng_rejects_oversized_response(monkeypatch):
    monkeypatch.setattr("urllib.request.build_opener", _opener(b"x" * 524289))
    try:
        search_searxng("q", "http://searxng:8080")
    except ResearchError:
        pass
    else:
        raise AssertionError("oversized response accepted")


def _client_with(store, deps_extra):
    deps = {"agent_grant_store": store, "get_identity_session": lambda _: None,
            "normalize_role": lambda r: r, "agent_request_token": "agent",
            "github_write_token": "", "web_search_token": "", "audit_admin_event": lambda *a: None}
    deps.update(deps_extra)
    app = FastAPI(); app.include_router(build_agent_grants_router(deps))
    return TestClient(app)


def test_research_uses_searxng_provider(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "r.sqlite3"); calls = []
    monkeypatch.setattr("jarvis.api_agent_grants.search_searxng",
                        lambda q, url, limit=5: calls.append((q, url, limit)) or [{"title": "r"}])
    client = _client_with(store, {"search_provider": "searxng", "searxng_url": "http://searxng:8080"})
    project = store.request_project(kind="business_research", target="b:a", title="A", operations=["web_search"])
    store.decide_project(project["id"], actor="owner", approve=True)
    response = client.post("/agent/research/search", headers={"X-Jarvis-Agent-Request-Token": "agent"},
                           json={"project_target": "b:a", "query": "market demand", "limit": 3})
    assert response.status_code == 200
    assert calls == [("market demand", "http://searxng:8080", 3)]


def test_research_searxng_without_url_is_closed(tmp_path, monkeypatch):
    store = AgentGrantStore(tmp_path / "r.sqlite3")
    monkeypatch.setattr("jarvis.api_agent_grants.search_searxng",
                        lambda q, url, limit=5: (_ for _ in ()).throw(ResearchError("searxng url unavailable")))
    client = _client_with(store, {"search_provider": "searxng", "searxng_url": ""})
    project = store.request_project(kind="business_research", target="b:a", title="A", operations=["web_search"])
    store.decide_project(project["id"], actor="owner", approve=True)
    assert client.post("/agent/research/search", headers={"X-Jarvis-Agent-Request-Token": "agent"},
                       json={"project_target": "b:a", "query": "q", "limit": 3}).status_code == 502
