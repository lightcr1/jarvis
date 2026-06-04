---
name: project-coverage-gaps-v35
description: API endpoints with zero test coverage at V35 session start — all now covered
metadata:
  type: project
---

Endpoints discovered to have zero tests at the start of the V35 QA session (2026-05-21):

| Endpoint | Now Covered In |
|---|---|
| `GET /admin/sessions` | test_api_uncovered_endpoints.py::TestAdminSessionEndpoints |
| `DELETE /admin/sessions/{user_id}` | test_api_uncovered_endpoints.py::TestAdminSessionEndpoints |
| `GET /admin/authz/check` | test_api_uncovered_endpoints.py::TestAdminAuthzCheck |
| `POST /chat/sessions/{id}/pending-home-assistant/clear` | test_api_uncovered_endpoints.py::TestPendingHomeAssistantClear |
| `PUT /auth/me/password` | test_api_uncovered_endpoints.py::TestChangeOwnPassword |

All 8 V1 acceptance scenarios (previously only described in MANUAL_ACCEPTANCE_V1.md) now have automated pytest equivalents in `tests/test_acceptance_scenarios.py`.

**Why:** These endpoints were added/modified in V35 but the test files were not updated. The admin sessions and authz check endpoints are particularly important for RBAC validation.

**How to apply:** When endpoints are added to api_admin.py or api_auth_chat.py, check test_api_uncovered_endpoints.py and test_api_module_routers.py to ensure coverage exists before declaring done.
