---
name: project-rag-api-shape
description: Actual shape of /rag/status backend response — different from what you'd expect
metadata:
  type: project
---

`GET /rag/status` returns:
```json
{
  "updated_at": 1716123456,   // unix epoch — 0 if never indexed
  "report": {},               // arbitrary key/value report from indexing run
  "counts": {                 // per-source document counts, e.g. {"github": 142, "wikijs": 38}
    "github": 142,
    "wikijs": 38
  }
}
```

**To check if RAG is active:** `updated_at > 0 && sum(counts.values()) > 0`

**Not present:** `indexed: bool`, `document_count: int`, `sources: string[]` — these were the intuitive field names but the backend uses `counts` (dict) and `updated_at` instead.

**Backend source:** `jarvis/api_auth_chat.py`, `rag_status()` function (~line 770).

**Frontend type:** `RagStatus` in `frontend/src/shared/api/chat.ts`.
