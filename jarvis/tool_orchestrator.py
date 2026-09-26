from __future__ import annotations

import json

from .tool_registry import ToolExecutionContext, execute_tool
from .untrusted import wrap_untrusted


def _append_tool_exchange(provider: str, convo: list[dict], call, tool_result: dict) -> list[dict]:
    payload = wrap_untrusted("tool", json.dumps(tool_result.get("data", {})))
    if provider == "anthropic":
        return convo + [
            {"role": "assistant", "content": [{"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": call.id, "content": payload}]},
        ]
    return convo + [
        {"role": "assistant", "content": None, "tool_calls": [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments)}},
        ]},
        {"role": "tool", "tool_call_id": call.id, "content": payload},
    ]


def run_chat_with_tools(
    router_obj,
    decision,
    *,
    messages: list[dict],
    system_prompt: str,
    registry,
    ctx: ToolExecutionContext,
    audit_log,
    membership_store,
    permission_store,
    max_tokens: int | None = None,
    max_rounds: int = 3,
) -> dict | None:
    """Run a chat turn with tool-calling. Returns None if no tools are available
    to this caller or the resolved provider doesn't support tool-calling — the
    caller should fall back to a plain router_obj.run_once() in that case."""
    if decision.provider not in router_obj.TOOL_CAPABLE_PROVIDERS:
        return None
    tools = registry.available_to(ctx.role, ctx.user_id, membership_store, permission_store)
    if not tools:
        return None

    convo = list(messages)
    total_input = 0
    total_output = 0
    trace: list[str] = []

    for _ in range(max_rounds):
        result = router_obj.run_with_tools(
            decision, messages=convo, system_prompt=system_prompt, tools=tools, max_tokens=max_tokens,
        )
        total_input += result.input_tokens
        total_output += result.output_tokens
        if not result.tool_calls:
            return {
                "reply": result.text,
                "data": {"tool_trace": trace},
                "input_tokens": total_input,
                "output_tokens": total_output,
            }
        call = result.tool_calls[0]
        tool = registry.get(call.name)
        trace.append(call.name)
        if tool is None:
            tool_result = {"reply": "", "data": {"route": "tool_error", "error": "unknown_tool"}}
        else:
            tool_result = execute_tool(
                tool, ctx, call.arguments,
                audit_log=audit_log, membership_store=membership_store, permission_store=permission_store,
                agent_grant_store=ctx.deps.get("agent_grant_store"),
            )
        # Tool-Ausgaben sind unvertraute Daten: ab jetzt T2-Aktionen eskalieren.
        if isinstance(ctx.deps, dict):
            ctx.deps["untrusted_context"] = True
        if (tool_result.get("data") or {}).get("route") in {"tool_confirmation_required", "tool_approval_required"}:
            # Don't feed a confirmation prompt back into the LLM as a tool result —
            # surface it as the turn's final reply and let the confirm/deny round-trip
            # happen at the chat-turn level (see pending_tool_call in api_auth_chat.py).
            return {
                "reply": tool_result["reply"],
                "data": {"tool_trace": trace, **tool_result["data"]},
                "input_tokens": total_input,
                "output_tokens": total_output,
            }
        convo = _append_tool_exchange(decision.provider, convo, call, tool_result)

    return {
        "reply": "I've reached my limit of tool steps for this request — could you narrow it down or rephrase?",
        "data": {"tool_trace": trace, "route": "tool_max_rounds"},
        "input_tokens": total_input,
        "output_tokens": total_output,
    }
