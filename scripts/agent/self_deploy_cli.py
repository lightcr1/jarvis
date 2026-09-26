#!/usr/bin/env python3
"""Host-seitiger Self-Deploy-Einstieg (Plan 5.3).

Baut den SelfDeployer aus der Umgebung, fuehrt den Deploy **mit Freigabe**
(approved=True, der Host-Loop ist die Freigabe) aus und druckt das Ergebnis als
JSON. Exitcode 0 = ok, 1 = fehlgeschlagen (bereits zurueckgerollt).

Aufruf typischerweise ueber scripts/agent/self_deploy_loop.sh (Cron).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jarvis.self_deploy import SelfDeployer  # noqa: E402


def runner(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    os.environ.setdefault("JARVIS_DEPLOY_COMMAND", f"bash {ROOT}/scripts/agent/self_deploy.sh")
    os.environ.setdefault("JARVIS_ROLLBACK_COMMAND", f"bash {ROOT}/scripts/agent/rollback_self.sh")
    service = os.getenv("SELF_DEPLOY_SERVICE", "jarvis")
    deployer = SelfDeployer(runner)
    result = deployer.deploy(service, approved=True, actor="self-deploy-loop")
    print(json.dumps(result.to_dict(), ensure_ascii=False))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
