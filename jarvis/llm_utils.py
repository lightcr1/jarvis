def trim_to_budget(messages: list[dict], budget: int = 4000) -> list[dict]:
    """Drop oldest messages until estimated token count fits within budget (keeps at least 2)."""
    total = sum(len(m.get("content", "")) // 4 for m in messages)
    while total > budget and len(messages) > 2:
        dropped = messages.pop(0)
        total -= len(dropped.get("content", "")) // 4
    return messages
