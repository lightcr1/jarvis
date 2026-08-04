import { useEffect, useState } from "react";
import { apiRequest, getSessionToken, getStoredUser } from "./client";

export type JarvisAlert = {
  id: string;
  level: string;
  title: string;
  message: string;
  source: string;
  code: string;
};

export type AlertMetric = "cpu" | "ram" | "disk" | "ha_health" | "ha_entity" | "presence_idle_minutes" | "calendar_upcoming_minutes";

export type AlertConditionClause = {
  metric: AlertMetric;
  condition: "above" | "below" | "equals" | "contains";
  threshold: number | string;
  ha_entity_id?: string | null;
  ha_attribute?: string | null;
};

export type AlertRule = {
  id: string;
  owner_user_id?: string | null;
  name: string;
  enabled: boolean;
  metric: AlertMetric;
  condition: "above" | "below" | "equals" | "contains";
  threshold: number | string;
  duration_seconds: number;
  severity: "info" | "warning" | "critical";
  cooldown_seconds: number;
  ha_entity_id: string | null;
  ha_attribute: string | null;
  message_template: string;
  conditions?: AlertConditionClause[] | null;
  combinator?: "and" | "or";
};

export type AlertRuleCreate = Omit<AlertRule, "id" | "owner_user_id">;
export type AlertRuleUpdate = Partial<AlertRuleCreate>;

export type AlertEvent = {
  type: "alert";
  alert_id: string;
  rule_id: string;
  rule_name: string;
  severity: "info" | "warning" | "critical";
  metric: string;
  current_value: number | string;
  threshold: number | string;
  message: string;
  timestamp: number;
};

export type SuggestionEvent = {
  type: "suggestion";
  suggestion_id: string;
  kind: string;
  message: string;
  timestamp: number;
};

function wsUrl(path: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}

export type BriefingPush = { text: string; user_id: string; ts: number };
export type DigestPush = { kind: "weekly_digest" | "nightly_summary"; text: string; user_id: string; ts: number };

type IncomingPayload = {
  type?: string;
  alerts?: JarvisAlert[];
  user_id?: string;
  text?: string;
  ts?: number;
  suggestion_id?: string;
  kind?: string;
  message?: string;
  timestamp?: number;
  last_briefing_seen_ts?: number;
};

function markBriefingSeenLocally(userId: string | null) {
  if (!userId) return;
  const today = new Date().toISOString().slice(0, 10);
  localStorage.setItem(`jarvis_briefing_${userId}_${today}`, "1");
}

export function useJarvisAlerts() {
  const [alerts, setAlerts] = useState<JarvisAlert[]>([]);
  const [briefings, setBriefings] = useState<BriefingPush[]>([]);
  const [suggestions, setSuggestions] = useState<SuggestionEvent[]>([]);
  const [digests, setDigests] = useState<DigestPush[]>([]);
  const [briefingSeenTs, setBriefingSeenTs] = useState<number | null>(null);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) return;
    const currentUserId = getStoredUser()?.id ?? null;
    const isForCurrentUser = (userId?: string) => !currentUserId || !userId || userId === currentUserId;

    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(wsUrl(`/ws/alerts?session=${encodeURIComponent(token)}`));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as IncomingPayload;
          if (payload.type === "alerts" && Array.isArray(payload.alerts) && payload.alerts.length) {
            setAlerts((prev) => [...prev, ...payload.alerts!]);
          } else if (payload.type === "briefing" && isForCurrentUser(payload.user_id)) {
            setBriefings((prev) => [...prev, { text: payload.text ?? "", user_id: payload.user_id ?? "", ts: payload.ts ?? Date.now() }]);
          } else if ((payload.type === "weekly_digest" || payload.type === "nightly_summary") && isForCurrentUser(payload.user_id)) {
            setDigests((prev) => [...prev, {
              kind: payload.type as DigestPush["kind"],
              text: payload.text ?? "",
              user_id: payload.user_id ?? "",
              ts: payload.ts ?? Date.now(),
            }]);
          } else if (payload.type === "suggestion") {
            setSuggestions((prev) => [...prev, {
              type: "suggestion",
              suggestion_id: payload.suggestion_id ?? `sugg-${Date.now()}`,
              kind: payload.kind ?? "",
              message: payload.message ?? "",
              timestamp: payload.timestamp ?? Date.now(),
            }]);
          } else if (payload.type === "briefing_seen") {
            markBriefingSeenLocally(currentUserId);
            setBriefingSeenTs(payload.last_briefing_seen_ts ?? Date.now());
          }
        } catch {
          // ignore malformed payloads
        }
      };
      socket.onclose = () => {
        if (closed) return;
        retryTimer = window.setTimeout(connect, 2500);
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      socket?.close();
    };
  }, []);

  const dismissAlert = (id: string) => {
    setAlerts((prev) => prev.filter((item) => item.id !== id));
  };
  const dismissBriefing = (ts: number) => {
    setBriefings((prev) => prev.filter((b) => b.ts !== ts));
  };
  const dismissSuggestion = (suggestionId: string) => {
    setSuggestions((prev) => prev.filter((s) => s.suggestion_id !== suggestionId));
  };
  const dismissDigest = (ts: number) => {
    setDigests((prev) => prev.filter((d) => d.ts !== ts));
  };

  return { alerts, dismissAlert, briefings, dismissBriefing, suggestions, dismissSuggestion, digests, dismissDigest, briefingSeenTs };
}

export function markBriefingSeen() {
  return apiRequest<{ preferences: { last_briefing_seen_ts: number } }>("/sync/briefing-seen", {
    method: "POST",
    includeUser: true,
  });
}

export function fetchAlertRules() {
  return apiRequest<{ rules: AlertRule[] }>("/admin/alerts/rules", { includeAdmin: true });
}

export function createAlertRule(body: AlertRuleCreate) {
  return apiRequest<{ rule: AlertRule }>("/admin/alerts/rules", {
    method: "POST",
    includeAdmin: true,
    body,
  });
}

export function updateAlertRule(ruleId: string, body: AlertRuleUpdate) {
  return apiRequest<{ rule: AlertRule }>(`/admin/alerts/rules/${encodeURIComponent(ruleId)}`, {
    method: "PATCH",
    includeAdmin: true,
    body,
  });
}

export function deleteAlertRule(ruleId: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/admin/alerts/rules/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
    includeAdmin: true,
  });
}

export function testAlertRule(ruleId: string) {
  return apiRequest<{ ok: boolean; event: AlertEvent }>(`/admin/alerts/rules/${encodeURIComponent(ruleId)}/test`, {
    method: "POST",
    includeAdmin: true,
  });
}

export function fetchAlertHistory(limit = 100) {
  return apiRequest<{ alerts: AlertEvent[] }>(`/admin/alerts/history?limit=${limit}`, {
    includeAdmin: true,
  });
}

export function fetchOwnAlertRules() {
  return apiRequest<{ rules: AlertRule[] }>("/alerts/rules", { includeUser: true });
}

export function createOwnAlertRule(body: AlertRuleCreate) {
  return apiRequest<{ rule: AlertRule }>("/alerts/rules", {
    method: "POST",
    includeUser: true,
    body,
  });
}

export function updateOwnAlertRule(ruleId: string, body: AlertRuleUpdate) {
  return apiRequest<{ rule: AlertRule }>(`/alerts/rules/${encodeURIComponent(ruleId)}`, {
    method: "PATCH",
    includeUser: true,
    body,
  });
}

export function deleteOwnAlertRule(ruleId: string) {
  return apiRequest<{ ok: boolean; id: string }>(`/alerts/rules/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export function testOwnAlertRule(ruleId: string) {
  return apiRequest<{ ok: boolean; event: AlertEvent }>(`/alerts/rules/${encodeURIComponent(ruleId)}/test`, {
    method: "POST",
    includeUser: true,
  });
}
