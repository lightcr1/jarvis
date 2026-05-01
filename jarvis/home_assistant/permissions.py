from __future__ import annotations


HOME_ASSISTANT_PERMISSIONS: tuple[str, ...] = (
    "home_assistant.access",
    "home_assistant.device_discovery",
    "home_assistant.device_control",
    "home_assistant.security_device_control",
    "home_assistant.system_control",
    "home_assistant.integration_management",
    "home_assistant.remote_control",
    "home_assistant.automation_management",
)


HOME_ASSISTANT_PERMISSION_GROUPS: dict[str, tuple[str, ...]] = {
    "core": (
        "home_assistant.access",
        "home_assistant.device_discovery",
    ),
    "control": (
        "home_assistant.device_control",
        "home_assistant.security_device_control",
        "home_assistant.system_control",
        "home_assistant.remote_control",
    ),
    "operations": (
        "home_assistant.integration_management",
        "home_assistant.automation_management",
    ),
}
