import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).parents[1] / "scripts" / "agent" / "check_policy.py"
SPEC = importlib.util.spec_from_file_location("check_policy", MODULE_PATH)
policy = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(policy)


def test_secret_paths_are_denied_but_examples_are_allowed():
    config = __import__("json").loads(policy.POLICY_PATH.read_text())
    assert policy.matches("deploy/openhands/.env", config["deny_paths"])
    assert policy.matches("deploy/openhands/.env.example", config["allow_example_paths"])


def test_security_and_deploy_paths_are_protected():
    config = __import__("json").loads(policy.POLICY_PATH.read_text())
    assert policy.matches("jarvis/authz.py", config["protected_paths"])
    assert policy.matches("deploy/openhands/compose.yml", config["protected_paths"])
    assert not policy.matches("frontend/src/App.tsx", config["protected_paths"])
