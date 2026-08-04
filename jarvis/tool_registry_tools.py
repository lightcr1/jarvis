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


def _list_tasks_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    task_service = ctx.deps["task_service"]
    status = str(args.get("status") or "").strip().lower() or None
    result = task_service.list_tasks(user_id=ctx.user_id, role=ctx.role, status=status)
    tasks = result.get("tasks") or []
    reply = f"You have {len(tasks)} task(s)." if tasks else "Nothing on your task list."
    return {"reply": reply, "data": {"route": "task_list", "tasks": tasks}}


def _create_task_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    task_service = ctx.deps["task_service"]
    title = str(args.get("title") or "").strip()
    if not title:
        return {"reply": "What should the task be called?", "data": {"route": "tool_error", "error": "missing_title"}}
    payload = {"title": title}
    if args.get("due_at") is not None:
        payload["due_at"] = args["due_at"]
    result = task_service.create_task(payload, user_id=ctx.user_id, role=ctx.role)
    return {"reply": f'Done. Added "{title}" to your tasks.', "data": {"route": "task_created", "task": result["task"]}}


def _complete_task_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    task_service = ctx.deps["task_service"]
    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        return {"reply": "Which task, sir?", "data": {"route": "tool_error", "error": "missing_task_id"}}
    result = task_service.complete_task(task_id, user_id=ctx.user_id, role=ctx.role)
    return {"reply": "Done. Marked as complete.", "data": {"route": "task_completed", "task": result["task"]}}


def _list_calendar_events_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    calendar_service = ctx.deps["calendar_service"]
    result = calendar_service.list_events(user_id=ctx.user_id, role=ctx.role)
    events = result.get("events") or []
    reply = f"You have {len(events)} upcoming event(s)." if events else "Nothing on your calendar."
    return {"reply": reply, "data": {"route": "calendar_event_list", "events": events}}


def _create_calendar_event_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    calendar_service = ctx.deps["calendar_service"]
    title = str(args.get("title") or "").strip()
    start = args.get("start")
    end = args.get("end")
    if not title or start is None or end is None:
        return {"reply": "I need a title, start, and end time for the event.", "data": {"route": "tool_error", "error": "missing_args"}}
    result = calendar_service.create_event({"title": title, "start": start, "end": end}, user_id=ctx.user_id, role=ctx.role)
    if not result.get("created"):
        names = ", ".join(c["title"] for c in (result.get("conflicts") or [])[:3])
        return {"reply": f"That overlaps with {names}. Pick another time.", "data": {"route": "calendar_conflict", **result}}
    return {"reply": f'Done. "{title}" is on your calendar.', "data": {"route": "calendar_event_created", **result}}


def _list_emails_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    email_service = ctx.deps["email_service"]
    unread_only = bool(args.get("unread_only"))
    result = email_service.list_messages(user_id=ctx.user_id, role=ctx.role, unread_only=unread_only)
    messages = result.get("messages") or []
    reply = f"You have {len(messages)} message(s)." if messages else "Inbox is clear."
    return {"reply": reply, "data": {"route": "email_list", "messages": messages}}


def _create_email_draft_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    email_service = ctx.deps["email_service"]
    to = str(args.get("to") or "").strip()
    body = str(args.get("body") or "").strip()
    if not to or not body:
        return {"reply": "I need a recipient and a message body for the draft.", "data": {"route": "tool_error", "error": "missing_args"}}
    payload = {"to": to, "body": body, "subject": str(args.get("subject") or "").strip()}
    result = email_service.create_draft(payload, user_id=ctx.user_id, role=ctx.role)
    return {"reply": f"Draft ready for {to}, held for your approval.", "data": {"route": "email_draft_created", "draft": result["draft"]}}


def _send_email_draft_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    email_service = ctx.deps["email_service"]
    draft_id = str(args.get("draft_id") or "").strip()
    if not draft_id:
        return {"reply": "Which draft, sir?", "data": {"route": "tool_error", "error": "missing_draft_id"}}
    # Our own WRITE-risk confirmation gate already served as the one confirmation
    # step for this tool call — pass confirm=True straight through rather than
    # making the user confirm a second time against send_draft's own internal gate.
    result = email_service.send_draft(draft_id, user_id=ctx.user_id, role=ctx.role, confirm=True)
    return {"reply": "Done. Message sent.", "data": {"route": "email_sent", **result}}


def _proxmox_vm_action_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    host_id, node, vmid = str(args.get("host_id") or ""), str(args.get("node") or ""), str(args.get("vmid") or "")
    action = str(args.get("action") or "").strip().lower()
    if not host_id or not node or not vmid or action not in {"start", "stop", "restart"}:
        return {"reply": "I need a host, node, VM id, and a start/stop/restart action.", "data": {"route": "tool_error", "error": "missing_args"}}
    try:
        result = ctx.deps["proxmox_vm_action"](host_id, node, vmid, action)
    except HTTPException as exc:
        return {"reply": f"I can't do that: {exc.detail}", "data": {"route": "tool_error", "error": "proxmox_error", "detail": exc.detail}}
    return {"reply": f"Done. VM {vmid}: {action}.", "data": {"route": "proxmox_vm_action", "result": result}}


def _proxmox_lxc_action_handler(ctx: ToolExecutionContext, args: dict) -> dict:
    host_id, node, vmid = str(args.get("host_id") or ""), str(args.get("node") or ""), str(args.get("vmid") or "")
    action = str(args.get("action") or "").strip().lower()
    if not host_id or not node or not vmid or action not in {"start", "stop", "restart"}:
        return {"reply": "I need a host, node, container id, and a start/stop/restart action.", "data": {"route": "tool_error", "error": "missing_args"}}
    try:
        result = ctx.deps["proxmox_lxc_action"](host_id, node, vmid, action)
    except HTTPException as exc:
        return {"reply": f"I can't do that: {exc.detail}", "data": {"route": "tool_error", "error": "proxmox_error", "detail": exc.detail}}
    return {"reply": f"Done. Container {vmid}: {action}.", "data": {"route": "proxmox_lxc_action", "result": result}}


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
    registry.register(Tool(
        name="list_tasks",
        description="List the user's tasks, optionally filtered by status (open, in_progress, done).",
        parameters={
            "type": "object",
            "properties": {"status": {"type": "string", "description": "Optional filter: 'open', 'in_progress', or 'done'."}},
        },
        required_permission="tasks.read",
        risk=RiskLevel.READ,
        handler=_list_tasks_handler,
    ))
    registry.register(Tool(
        name="create_task",
        description="Add a new task to the user's task list.",
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The task's title."},
                "due_at": {"type": "integer", "description": "Optional due date as a Unix epoch timestamp."},
            },
            "required": ["title"],
        },
        required_permission="tasks.write",
        risk=RiskLevel.WRITE,
        handler=_create_task_handler,
    ))
    registry.register(Tool(
        name="complete_task",
        description="Mark a task as complete, given its task_id (from list_tasks).",
        parameters={
            "type": "object",
            "properties": {"task_id": {"type": "string", "description": "The task's id, from list_tasks."}},
            "required": ["task_id"],
        },
        required_permission="tasks.write",
        risk=RiskLevel.WRITE,
        handler=_complete_task_handler,
    ))
    registry.register(Tool(
        name="list_calendar_events",
        description="List the user's upcoming personal calendar events.",
        parameters={"type": "object", "properties": {}},
        required_permission="calendar.read",
        risk=RiskLevel.READ,
        handler=_list_calendar_events_handler,
    ))
    registry.register(Tool(
        name="create_calendar_event",
        description=(
            "Create a personal calendar event. If it overlaps an existing event, this returns the conflict "
            "instead of double-booking — relay that to the user and ask them to pick another time."
        ),
        parameters={
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "The event's title."},
                "start": {"type": "integer", "description": "Start time as a Unix epoch timestamp."},
                "end": {"type": "integer", "description": "End time as a Unix epoch timestamp."},
            },
            "required": ["title", "start", "end"],
        },
        required_permission="calendar.write",
        risk=RiskLevel.WRITE,
        handler=_create_calendar_event_handler,
    ))
    registry.register(Tool(
        name="list_emails",
        description="List the user's recent email messages.",
        parameters={
            "type": "object",
            "properties": {"unread_only": {"type": "boolean", "description": "If true, only list unread messages."}},
        },
        required_permission="email.read",
        risk=RiskLevel.READ,
        handler=_list_emails_handler,
    ))
    registry.register(Tool(
        name="create_email_draft",
        description="Create an email draft held for the user's approval. Does not send anything.",
        parameters={
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient email address."},
                "subject": {"type": "string", "description": "Email subject."},
                "body": {"type": "string", "description": "Email body text."},
            },
            "required": ["to", "body"],
        },
        required_permission="email.write",
        risk=RiskLevel.WRITE,
        handler=_create_email_draft_handler,
    ))
    registry.register(Tool(
        name="send_email_draft",
        description="Send a previously created email draft, given its draft_id. This is a real, irreversible send — always confirm with the user before calling it.",
        parameters={
            "type": "object",
            "properties": {"draft_id": {"type": "string", "description": "The draft's id, from create_email_draft."}},
            "required": ["draft_id"],
        },
        required_permission="email.write",
        risk=RiskLevel.WRITE,
        handler=_send_email_draft_handler,
    ))
    registry.register(Tool(
        name="proxmox_vm_action",
        description="Start, stop, or restart a Proxmox VM. This is a real action on real infrastructure — always confirm with the user before calling it.",
        parameters={
            "type": "object",
            "properties": {
                "host_id": {"type": "string", "description": "The configured Proxmox host id."},
                "node": {"type": "string", "description": "The Proxmox node name."},
                "vmid": {"type": "string", "description": "The VM id."},
                "action": {"type": "string", "description": "One of: start, stop, restart."},
            },
            "required": ["host_id", "node", "vmid", "action"],
        },
        required_permission="proxmox.manage",
        risk=RiskLevel.WRITE,
        handler=_proxmox_vm_action_handler,
    ))
    registry.register(Tool(
        name="proxmox_lxc_action",
        description="Start, stop, or restart a Proxmox LXC container. This is a real action on real infrastructure — always confirm with the user before calling it.",
        parameters={
            "type": "object",
            "properties": {
                "host_id": {"type": "string", "description": "The configured Proxmox host id."},
                "node": {"type": "string", "description": "The Proxmox node name."},
                "vmid": {"type": "string", "description": "The container id."},
                "action": {"type": "string", "description": "One of: start, stop, restart."},
            },
            "required": ["host_id", "node", "vmid", "action"],
        },
        required_permission="proxmox.manage",
        risk=RiskLevel.WRITE,
        handler=_proxmox_lxc_action_handler,
    ))
    return registry
