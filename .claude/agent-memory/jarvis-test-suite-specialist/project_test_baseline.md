---
name: project-test-baseline
description: Test count history across JARVIS V35 session — baseline 1034, V1 work brought to 1057
metadata:
  type: project
---

Test count milestones in V35 session (2026-05-21):

- **Baseline at session start**: 1034 tests passing (143 subtests)
- **After test_acceptance_scenarios.py**: 1042 tests (8 new acceptance scenarios)
- **After test_api_uncovered_endpoints.py**: 1057 tests (15 new endpoint tests)

**Why:** Tracking this allows future sessions to detect regressions or verify progress.

**How to apply:** Before starting work in a new session, run the full suite and compare the count to this baseline. If fewer pass, investigate before adding new tests.

Key files added in V35 test session:
- `tests/test_acceptance_scenarios.py` — 8 acceptance scenarios (V1 release criteria)
- `tests/test_api_uncovered_endpoints.py` — 15 endpoint tests for previously-uncovered endpoints

Endpoints still lacking full coverage after V35 (minor):
- `/ws/status` WebSocket (difficult to test without async client)
- `/ws/alerts` WebSocket (same)
- `/ws/home-assistant` WebSocket (same)
- `/stt` (requires real audio bytes + patched faster-whisper — tested in test_voice_api.py but coverage is partial)
