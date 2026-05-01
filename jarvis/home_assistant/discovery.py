from __future__ import annotations

import time
import uuid


def build_discovery_candidate(
    *,
    source: str,
    ip_address: str,
    label: str,
    suggested_type: str,
    suggested_area: str,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "id": f"hac-{uuid.uuid4().hex[:12]}",
        "source": source,
        "ip_address": ip_address,
        "label": label,
        "suggested_type": suggested_type,
        "suggested_area": suggested_area,
        "trust_level": "untrusted",
        "risk_level": "medium",
        "onboarding_status": "review_pending",
        "approval_status": "pending",
        "created_at": int(time.time()),
        "metadata": metadata or {},
    }
