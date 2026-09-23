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
