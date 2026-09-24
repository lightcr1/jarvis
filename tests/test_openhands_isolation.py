from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_agent_canvas_has_only_isolated_network_and_exact_repo_mount():
    compose = (ROOT / "deploy/openhands/compose.yml").read_text()
    canvas = compose.split("  canvas-edge:", 1)[0]
    assert "OPENHANDS_JARVIS_PROJECT_DIR" in canvas
    assert "OPENHANDS_PROJECTS_DIR" not in canvas
    assert "- agent-isolated" in canvas
    assert "runpod-internal" not in canvas
    assert "cap_drop:\n      - ALL" in canvas
    assert "docker.sock" not in compose
    assert "canvas-edge" in compose and "./canvas-edge.conf" in compose
    assert (ROOT / "deploy/openhands/canvas-edge.conf").exists()


def test_canvas_edge_proxies_only_to_agent():
    config = (ROOT / "deploy/openhands/canvas-edge.conf").read_text()
    assert "proxy_pass http://jarvis-openhands:8000" in config
    assert "upgrade" in config.lower()
    compose = (ROOT / "deploy/openhands/compose.yml").read_text()
    assert "OPENHANDS_EDGE_PORT" in compose


def test_gateway_has_fixed_upstream_and_default_deny():
    config = (ROOT / "deploy/openhands/inference-gateway.conf").read_text()
    assert "proxy_pass http://controller:8080/agent/v1/;" in config
    assert "location / { return 403; }" in config
    assert "^/jarvis-agent/" in config
    assert "/admin" not in config
    assert "proxy_pass $" not in config
    assert "resolver" not in config
