from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable, Iterable

logger = logging.getLogger("jarvis.push")

# Returns True on success, False on a transient failure (retry-worthy), or None
# when the push service reports the subscription is gone (404/410 — caller should
# delete it).
PushSendFn = Callable[[dict, dict, dict], "bool | None"]


def send_web_push(subscription: dict, notification: dict, vapid_keys: dict) -> bool | None:
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush is not installed — push notification skipped.")
        return False

    try:
        webpush(
            subscription_info=subscription,
            data=json.dumps(notification),
            vapid_private_key=vapid_keys["private_key"],
            vapid_claims={"sub": vapid_keys.get("subject", "mailto:admin@localhost")},
        )
        return True
    except WebPushException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (404, 410):
            return None
        logger.warning("Web push delivery failed: %s", exc)
        return False
    except Exception as exc:
        logger.warning("Web push delivery failed: %s", exc)
        return False


def build_push_payload(event: dict) -> dict:
    kind = event.get("type", "alert")
    if kind == "alert":
        title = f"JARVIS — {str(event.get('severity', 'warning')).title()}"
        body = str(event.get("message") or "Alert triggered.")
    elif kind == "briefing":
        title = "Morning Briefing"
        body = str(event.get("text") or "")
    elif kind == "weekly_digest":
        title = "Weekly Digest"
        body = str(event.get("text") or "")
    elif kind == "nightly_summary":
        title = "Nightly Summary"
        body = str(event.get("text") or "")
    elif kind == "suggestion":
        title = "Suggestion"
        body = str(event.get("message") or "")
    else:
        title = "JARVIS"
        body = str(event.get("message") or event.get("text") or "")
    return {"title": title, "body": body, "tag": kind, "ts": event.get("timestamp") or event.get("ts")}


def _target_user_ids(payload: dict, all_subscribed: Iterable[str]) -> set[str]:
    user_id = payload.get("user_id")
    if user_id:
        return {user_id}
    return set(all_subscribed)


async def fanout_push(
    payload: dict,
    connected_user_ids: set[str],
    push_store: object,
    vapid_keys: dict,
    send_fn: PushSendFn = send_web_push,
) -> None:
    """Delivers `payload` as a webpush notification to any subscribed user not
    currently holding a live /ws/alerts WebSocket connection.

    Broadcast-style events (no `user_id`, e.g. alerts/suggestions) go to every
    subscribed user that isn't connected; user-scoped events (briefings, digests)
    go only to that user if they aren't connected.
    """
    if not vapid_keys.get("private_key"):
        return
    all_subscriptions = push_store.list_all()
    pending = _target_user_ids(payload, all_subscriptions.keys()) - connected_user_ids
    if not pending:
        return
    notification = build_push_payload(payload)
    loop = asyncio.get_event_loop()
    for user_id in pending:
        for subscription in all_subscriptions.get(user_id, []):
            result = await loop.run_in_executor(None, send_fn, subscription, notification, vapid_keys)
            if result is None:
                push_store.remove_by_endpoint(user_id, subscription.get("endpoint", ""))
