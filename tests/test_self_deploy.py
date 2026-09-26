"""Tests fuer Self-Deploy/Health-Check/Rollback (Plan 5.3)."""
from __future__ import annotations

import pytest

from jarvis.self_deploy import DeployError, SelfDeployer
from jarvis.zones import load_zones

GRANT = {"capability": "jarvis.deploy", "target_pattern": "*", "status": "approved"}


def _deployer(run, *, healthy=True):
    calls = []

    def runner(cmd):
        calls.append(list(cmd))
        return run(cmd)

    deployer = SelfDeployer(runner, zones=load_zones(), health_check=lambda: healthy,
                            deploy_command=["deploy"], rollback_command=["rollback"],
                            attempts=2, delay=0, sleep=lambda _s: None)
    return deployer, calls


def test_blocks_critical_service():
    deployer, _ = _deployer(lambda cmd: (0, ""))
    with pytest.raises(DeployError):
        deployer.deploy("searxng", approved=True)
    with pytest.raises(DeployError):
        deployer.deploy("runpod-controller", approved=True)


def test_requires_approval_for_t2():
    deployer, calls = _deployer(lambda cmd: (0, ""))
    with pytest.raises(DeployError):
        deployer.deploy("jarvis")          # weder Freigabe noch approved
    assert calls == []                     # nichts ausgefuehrt


def test_deploy_with_standing_grant_succeeds():
    deployer, calls = _deployer(lambda cmd: (0, ""))
    result = deployer.deploy("jarvis", standing_grant=GRANT)
    assert result.ok and not result.rolled_back and calls == [["deploy"]]


def test_failed_deploy_rolls_back():
    deployer, calls = _deployer(lambda cmd: (1, "") if cmd == ["deploy"] else (0, ""))
    result = deployer.deploy("jarvis", approved=True)
    assert not result.ok and result.rolled_back and ["rollback"] in calls


def test_unhealthy_deploy_rolls_back():
    deployer, calls = _deployer(lambda cmd: (0, ""), healthy=False)
    result = deployer.deploy("jarvis", approved=True)
    assert not result.ok and result.rolled_back and ["rollback"] in calls
