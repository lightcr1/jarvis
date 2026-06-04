---
name: feedback-test-runner
description: How to invoke pytest correctly in the JARVIS repo — requires PYTHONPATH set
metadata:
  type: feedback
---

Always run tests as:
  `PYTHONPATH=/home/jarvis/jarvis .venv/bin/pytest tests/ -x -q`

**Why:** The `jarvis/` package is not installed — tests import from it directly. Without `PYTHONPATH=/home/jarvis/jarvis`, imports like `from jarvis.api_admin import ...` fail with ModuleNotFoundError. The venv at `.venv/` has pytest; the system Python3 does not have pytest installed.

**How to apply:** Always prepend `PYTHONPATH=/home/jarvis/jarvis` when running pytest. The `.venv/bin/pytest` binary must be used, not `python -m pytest` without the venv.
