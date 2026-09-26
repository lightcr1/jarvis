from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .authz import permission_decision, resolve_effective_permissions
from .capabilities import authorize_action
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
    # Optionaler Freigabe-Kern: Capability aus config/capabilities.json. Ohne
    # Angabe wird sie aus dem Risk-Level abgeleitet (READ -> T0, sonst T2),
    # sodass das bestehende Verhalten unveraendert bleibt.
    capability: str | None = None


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


def capability_for_tool(tool: Tool) -> str:
    """Capability fuer den Freigabe-Kern; READ -> T0, sonst fail-safe unclassified."""
    if getattr(tool, "capability", None):
        return str(tool.capability)
    return "status.read" if tool.risk == RiskLevel.READ else "unclassified.action"


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

    # Zentraler Freigabe-Kern (Plan Abschnitt 3): konservativ ergaenzt.
    capability = capability_for_tool(tool)
    target = str(args.get("target") or args.get("name") or "")
    grant = None
    if agent_grant_store is not None and tool.risk != RiskLevel.READ:
        try:
            grant = agent_grant_store.match_standing_grant(capability, target)
        except Exception:  # noqa: BLE001 - Freigabe darf die Pruefung nicht brechen
            grant = None
    verdict = authorize_action(
        capability,
        target=target,
        params=args,
        standing_grant=grant,
        untrusted_context=bool((ctx.deps or {}).get("untrusted_context")) if isinstance(ctx.deps, dict) else False,
        emergency_stop=emergency_stop_enabled(),
    )
    if verdict.decision == "deny":
        if audit_log:
            audit_log.write("tool_capability_denied", {"tool": tool.name, "tier": verdict.tier, "reason": verdict.reason})
        return {"reply": "I can't take that action right now.",
                "data": {"route": "tool_denied", "tool": tool.name, "error": "denied", "tier": verdict.tier}}
    single_confirm = verdict.tier == "T3"  # T3 immer einzeln, nie per Agent-Grant
    core_allowed = verdict.decision == "allow" and verdict.tier in ("T0", "T1")
    # T2 per stehender Freigabe gedeckt -> ohne Rueckfrage ausfuehren.
    grant_allowed = verdict.decision == "allow" and verdict.tier == "T2" and grant is not None
    pre_authorized = (not single_confirm) and (agent_authorized or core_allowed or grant_allowed)

    if (tool.risk != RiskLevel.READ or single_confirm) and not (confirm or pre_authorized):
        if audit_log:
            audit_log.write("tool_confirmation_requested", {"tool": tool.name, "args": args, "user_id": ctx.user_id, "role": ctx.role, "risk": tool.risk, "tier": verdict.tier})
        return {
            "reply": f"This will {tool.description[0].lower()}{tool.description[1:]} Reply “yes” to confirm.",
            "data": {"route": "tool_confirmation_required", "tool": tool.name, "args": args, "risk": tool.risk, "tier": verdict.tier},
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
    if grant_allowed and agent_grant_store is not None:
        try:
            agent_grant_store.consume_standing_grant(grant["id"])
        except Exception:  # noqa: BLE001 - Zaehler darf die Aktion nicht brechen
            pass
    if audit_log:
        audit_log.write("tool_call_completed", {
            "tool": tool.name, "user_id": ctx.user_id,
            "route": (result.get("data") or {}).get("route") if isinstance(result, dict) else None,
        })
    return result
