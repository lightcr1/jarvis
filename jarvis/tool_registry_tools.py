from __future__ import annotations

from fastapi import HTTPException

from .files import chat_helpers as _fd
from .infra_actions import restart_service as _restart_service
from .jarvis_engine import RiskLevel
from .tool_registry import Tool, ToolExecutionContext, ToolRegistry


def _list_folder_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    file_service = ctx.deps["file_service"]
    folder_name = str(args.get("folder_name") or "").strip()
    if not folder_name:
        return {"reply": "Which folder, sir?", "data": {"route": "tool_error", "error": "missing_folder_name"}}
    folder = _fd.resolve_granted_folder(file_service, ctx.user_id, folder_name)
    if not folder:
        return {"reply": _fd.DENIAL_TEMPLATE.format(name=folder_name), "data": {"error": "not_granted", "route": "file_drive"}}
    return _fd.list_folder(file_service, folder, folder_name)


def _read_file_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    file_service = ctx.deps["file_service"]
    folder_name = str(args.get("folder_name") or "").strip()
    filename = str(args.get("filename") or "").strip()
    if not folder_name or not filename:
        return {"reply": "I need both a folder name and a filename.", "data": {"route": "tool_error", "error": "missing_args"}}
    folder = _fd.resolve_granted_folder(file_service, ctx.user_id, folder_name)
    if not folder:
        return {"reply": _fd.DENIAL_TEMPLATE.format(name=folder_name), "data": {"error": "not_granted", "route": "file_drive"}}
    return _fd.read_file(file_service, folder, folder_name, filename)


def _save_memory_note_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    memory_store = ctx.deps["memory_store"]
    text = str(args.get("text") or "").strip()
    if not text:
        return {"reply": "There's nothing there worth remembering.", "data": {"route": "tool_error", "error": "empty_text"}}
    note = memory_store.add_note(ctx.user_id, text)
    return {"reply": f'Noted, sir: "{text}"', "data": {"route": "memory_note_saved", "note": note}}


def _proxmox_status_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    proxmox_health = ctx.deps["proxmox_health"]
    health = proxmox_health()
    if not health.get("configured"):
        return {"reply": "No Proxmox host is configured yet.", "data": {"route": "proxmox_status", **health}}
    summary = health.get("summary") or {}
    reply = (
        f"On it. {summary.get('hosts', 0)} host(s), {summary.get('nodes', 0)} node(s), "
        f"{summary.get('running', 0)} running / {summary.get('stopped', 0)} stopped."
    )
    return {"reply": reply, "data": {"route": "proxmox_status", **health}}


def _restart_service_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    service = str(args.get("service") or "").strip()
    if not service:
        return {"reply": "Which service, sir?", "data": {"route": "tool_error", "error": "missing_service"}}
    try:
        result = _restart_service(service, run_cmd=ctx.deps["run_cmd"], ensure_service_allowed=ctx.deps["ensure_service_allowed"])
    except HTTPException as exc:
        return {"reply": f"I can't do that: {exc.detail}", "data": {"route": "tool_error", "error": "service_not_allowed", "detail": exc.detail}}
    reply = f"Done. {service} restarted — it's {result['active']} now." if result["healthy"] else f"Restarted {service}, but it's reporting '{result['active']}', not active — worth a look."
    return {"reply": reply, "data": {"route": "service_restarted", **result}}


def _list_devices_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    home_assistant_service = ctx.deps["home_assistant_service"]
    if not home_assistant_service:
        return {"reply": "Home Assistant isn't configured yet.", "data": {"route": "tool_error", "error": "not_configured"}}
    result = home_assistant_service.list_managed_entities(user_id=ctx.user_id, role=ctx.role)
    entities = result.get("entities") or []
    reply = f"You have {len(entities)} managed device(s)." if entities else "No managed devices are set up yet."
    return {"reply": reply, "data": {"route": "device_list", "entities": entities}}


def _control_device_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    home_assistant_service = ctx.deps["home_assistant_service"]
    if not home_assistant_service:
        return {"reply": "Home Assistant isn't configured yet.", "data": {"route": "tool_error", "error": "not_configured"}}
    entity_id = str(args.get("entity_id") or "").strip()
    action = str(args.get("action") or "").strip().lower()
    if not entity_id or not action:
        return {"reply": "I need both a device and an action.", "data": {"route": "tool_error", "error": "missing_args"}}
    payload = {"action": action}
    if "value" in args and args["value"] is not None:
        payload["value"] = args["value"]
    result = home_assistant_service.request_entity_action(entity_id, payload, user_id=ctx.user_id, role=ctx.role)
    if result.get("executed"):
        reply = f"Done. {entity_id}: {action}."
    else:
        reply = "That device needs an explicit confirmation from the Home Assistant screen before I can proceed — it's queued."
    return {"reply": reply, "data": {"route": "device_action", **result}}


def build_pilot_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(Tool(
        name="list_folder",
        description="List the files inside one of the user's file-drive folders that JARVIS has been granted access to.",
        parameters={
            "type": "object",
            "properties": {"folder_name": {"type": "string", "description": "The folder's name, e.g. 'Reports'."}},
            "required": ["folder_name"],
        },
        required_permission="files.read",
        risk=RiskLevel.READ,
        handler=_list_folder_handler,
    ))
    registry.register(Tool(
        name="read_file",
        description="Read the text content of a specific file inside one of the user's granted file-drive folders.",
        parameters={
            "type": "object",
            "properties": {
                "folder_name": {"type": "string", "description": "The folder's name."},
                "filename": {"type": "string", "description": "The file's name, including extension."},
            },
            "required": ["folder_name", "filename"],
        },
        required_permission="files.read",
        risk=RiskLevel.READ,
        handler=_read_file_handler,
    ))
    registry.register(Tool(
        name="save_memory_note",
        description=(
            "Save a durable fact or preference about the user to JARVIS's persistent memory, so it can be "
            "recalled in future conversations. Call this directly when the user states something clearly "
            "worth remembering; if unsure whether it's worth remembering, ask the user first in plain text "
            "instead of calling this."
        ),
        parameters={
            "type": "object",
            "properties": {"text": {"type": "string", "description": "The fact or preference to remember, written in third person."}},
            "required": ["text"],
        },
        required_permission="assistant.chat",
        risk=RiskLevel.READ,
        handler=_save_memory_note_handler,
    ))
    registry.register(Tool(
        name="proxmox_status",
        description="Get a summary of the configured Proxmox hosts, nodes, and VM/container run state.",
        parameters={"type": "object", "properties": {}},
        required_permission="proxmox.access",
        risk=RiskLevel.READ,
        handler=_proxmox_status_handler,
    ))
    registry.register(Tool(
        name="restart_service",
        description="Restart a system service via systemctl. This is a real, irreversible action on the host — always confirm with the user before calling it.",
        parameters={
            "type": "object",
            "properties": {"service": {"type": "string", "description": "The systemd service name, e.g. 'nginx' or 'docker'."}},
            "required": ["service"],
        },
        required_permission="actions.write.execute",
        risk=RiskLevel.WRITE,
        handler=_restart_service_handler,
    ))
    registry.register(Tool(
        name="list_devices",
        description="List the Home Assistant devices JARVIS manages, with their area, kind, and current state.",
        parameters={"type": "object", "properties": {}},
        required_permission="home_assistant.access",
        risk=RiskLevel.READ,
        handler=_list_devices_handler,
    ))
    registry.register(Tool(
        name="control_device",
        description=(
            "Send an action (e.g. turn_on, turn_off, set_temperature) to a specific Home Assistant device by "
            "entity_id. This is a real action on the user's home — always confirm with the user before calling "
            "it. Note: security-sensitive devices (locks, garage doors) go through Home Assistant's own separate "
            "confirmation queue regardless of this tool's confirmation — a queued reply here is normal for those."
        ),
        parameters={
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "The device's entity_id, from list_devices."},
                "action": {"type": "string", "description": "The action to perform, e.g. 'turn_on', 'turn_off', 'set_temperature'."},
                "value": {"description": "Optional action value, e.g. a target temperature."},
            },
            "required": ["entity_id", "action"],
        },
        required_permission="home_assistant.access",
        risk=RiskLevel.WRITE,
        handler=_control_device_handler,
    ))
    return registry
