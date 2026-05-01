from __future__ import annotations

from dataclasses import dataclass


LOW_RISK = "low"
MEDIUM_RISK = "medium"
HIGH_RISK = "high"


@dataclass(frozen=True)
class HomeAssistantActionPolicy:
    capability: str
    risk_level: str
    requires_confirmation: bool
    remote_restricted: bool


HOME_ASSISTANT_ACTION_POLICIES: dict[str, HomeAssistantActionPolicy] = {
    "shopping_list.modify": HomeAssistantActionPolicy(
        capability="home_assistant.access",
        risk_level=LOW_RISK,
        requires_confirmation=False,
        remote_restricted=False,
    ),
    "calendar.read": HomeAssistantActionPolicy(
        capability="home_assistant.access",
        risk_level=LOW_RISK,
        requires_confirmation=False,
        remote_restricted=False,
    ),
    "device.discovery.review": HomeAssistantActionPolicy(
        capability="home_assistant.device_discovery",
        risk_level=MEDIUM_RISK,
        requires_confirmation=True,
        remote_restricted=True,
    ),
    "device.control.basic": HomeAssistantActionPolicy(
        capability="home_assistant.device_control",
        risk_level=MEDIUM_RISK,
        requires_confirmation=False,
        remote_restricted=True,
    ),
    "device.control.security": HomeAssistantActionPolicy(
        capability="home_assistant.security_device_control",
        risk_level=HIGH_RISK,
        requires_confirmation=True,
        remote_restricted=True,
    ),
    "integration.manage": HomeAssistantActionPolicy(
        capability="home_assistant.integration_management",
        risk_level=HIGH_RISK,
        requires_confirmation=True,
        remote_restricted=True,
    ),
    "automation.manage": HomeAssistantActionPolicy(
        capability="home_assistant.automation_management",
        risk_level=MEDIUM_RISK,
        requires_confirmation=True,
        remote_restricted=True,
    ),
    "system.control.preapproved": HomeAssistantActionPolicy(
        capability="home_assistant.system_control",
        risk_level=HIGH_RISK,
        requires_confirmation=True,
        remote_restricted=True,
    ),
    "remote.system.control": HomeAssistantActionPolicy(
        capability="home_assistant.remote_control",
        risk_level=HIGH_RISK,
        requires_confirmation=True,
        remote_restricted=True,
    ),
}
