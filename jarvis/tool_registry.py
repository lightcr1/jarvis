from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .authz import permission_decision, resolve_effective_permissions
from .jarvis_engine import RiskLevel, emergency_stop_enabled


@dataclass(frozen=True)
class ToolExecutionContext:
    user_id: str | None
    role: str | None
    deps: dict


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    required_permission: str
    risk: str
    handler: Callable[[ToolExecutionContext, dict], dict]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def available_to(self, role: str | None, user_id: str | None, membership_store, permission_store) -> list[Tool]:
        effective = resolve_effective_permissions(role, user_id, membership_store, permission_store)
        return [t for t in self._tools.values() if t.required_permission in effective]


def to_openai_schema(tools: list[Tool]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": t.name, "description": t.description, "parameters": t.parameters}}
        for t in tools
    ]


def to_anthropic_schema(tools: list[Tool]) -> list[dict]:
    return [{"name": t.name, "description": t.description, "input_schema": t.parameters} for t in tools]


# Trusted registry classification: never derive authorization scope from an
# LLM-provided argument or a self-declared tool label. Expand only with a
# reviewed target resolver per real tool.
_AGENT_AUTONOMOUS_TOOLS = {
    "create_task": ("workspace", "jarvis:tasks", "create_task"),
    "complete_task": ("workspace", "jarvis:tasks", "complete_task"),
}


def execute_tool(
    tool: Tool,
    ctx: ToolExecutionContext,
    args: dict,
    *,
    audit_log,
    membership_store,
    permission_store,
    confirm: bool = False,
    agent_grant_store=None,
) -> dict:
    decision = permission_decision(ctx.role, ctx.user_id, tool.required_permission, membership_store, permission_store)
    if not decision["allowed"]:
        if audit_log:
            audit_log.write("tool_permission_denied", {
                "tool": tool.name, "user_id": ctx.user_id, "role": ctx.role,
                "required_permission": tool.required_permission,
            })
        return {
            "reply": "I don't have permission to do that.",
            "data": {"route": "tool_denied", "tool": tool.name, "error": "permission_denied"},
        }

    if tool.risk != RiskLevel.READ and emergency_stop_enabled():
        if audit_log:
            audit_log.write("tool_emergency_stop_blocked", {"tool": tool.name, "user_id": ctx.user_id, "role": ctx.role})
        return {
            "reply": "Emergency stop is active — I can't take that action right now.",
            "data": {"route": "tool_denied", "tool": tool.name, "error": "emergency_stop"},
        }

    agent_authorized = False
    if ctx.role == "service_system" and tool.risk != RiskLevel.READ:
        scope = _AGENT_AUTONOMOUS_TOOLS.get(tool.name)
        agent_authorized = bool(scope and agent_grant_store and agent_grant_store.authorize(
            kind=scope[0], target=scope[1], operation=scope[2],
        ))
        if not agent_authorized:
            if audit_log:
                audit_log.write("tool_agent_grant_denied", {"tool": tool.name, "user_id": ctx.user_id})
            return {"reply": "Owner grant required for this agent action.",
                    "data": {"route": "tool_denied", "tool": tool.name, "error": "agent_grant_required"}}

    if tool.risk != RiskLevel.READ and not (confirm or agent_authorized):
        if audit_log:
            audit_log.write("tool_confirmation_requested", {"tool": tool.name, "args": args, "user_id": ctx.user_id, "role": ctx.role, "risk": tool.risk})
        return {
            "reply": f"This will {tool.description[0].lower()}{tool.description[1:]} Reply “yes” to confirm.",
            "data": {"route": "tool_confirmation_required", "tool": tool.name, "args": args, "risk": tool.risk},
        }

    if audit_log:
        audit_log.write("tool_call_started", {"tool": tool.name, "args": args, "user_id": ctx.user_id, "role": ctx.role})
    try:
        result = tool.handler(ctx, args)
    except (PermissionError, LookupError, ValueError) as exc:
        if audit_log:
            audit_log.write("tool_call_error", {"tool": tool.name, "user_id": ctx.user_id, "error": str(exc)})
        return {
            "reply": f"I couldn't do that: {exc}",
            "data": {"route": "tool_error", "tool": tool.name, "error": str(exc)},
        }
    if audit_log:
        audit_log.write("tool_call_completed", {
            "tool": tool.name, "user_id": ctx.user_id,
            "route": (result.get("data") or {}).get("route") if isinstance(result, dict) else None,
        })
    return result
