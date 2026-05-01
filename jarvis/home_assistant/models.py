from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ManagedEntity:
    entity_id: str
    title: str
    entity_type: str
    area: str = ""
    integration_source: str = "home_assistant"
    capability_tags: tuple[str, ...] = ()
    control_mode: str = "manual"
    trust_level: str = "reviewed"
    risk_level: str = "low"
    approval_status: str = "approved"
    onboarding_status: str = "active"


@dataclass(frozen=True)
class DiscoveryCandidate:
    id: str
    source: str
    ip_address: str
    label: str
    suggested_type: str
    suggested_area: str
    trust_level: str = "untrusted"
    risk_level: str = "medium"
    onboarding_status: str = "review_pending"
    approval_status: str = "pending"
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class HomeAssistantPolicySnapshot:
    first_admin_user_id: str | None
    role: str
    effective_permissions: tuple[str, ...]
    access_granted: bool
    access_reason: str
    action_policies: dict[str, dict[str, object]]
