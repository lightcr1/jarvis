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

export type AlertRule = {
  id: string;
  name: string;
  enabled: boolean;
  metric: "cpu" | "ram" | "disk" | "ha_health" | "ha_entity";
  condition: "above" | "below" | "equals" | "contains";
  threshold: number | string;
  duration_seconds: number;
  severity: "info" | "warning" | "critical";
  cooldown_seconds: number;
  ha_entity_id: string | null;
  ha_attribute: string | null;
  message_template: string;
};

export type AlertRuleCreate = Omit<AlertRule, "id">;
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

function wsUrl(path: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}

export type BriefingPush = { text: string; user_id: string; ts: number };

export function useJarvisAlerts() {
  const [alerts, setAlerts] = useState<JarvisAlert[]>([]);
  const [briefings, setBriefings] = useState<BriefingPush[]>([]);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) return;
    const currentUserId = getStoredUser()?.id ?? null;

    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(wsUrl(`/ws/alerts?session=${encodeURIComponent(token)}`));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as { type?: string; alerts?: JarvisAlert[]; user_id?: string; text?: string; ts?: number };
          if (payload.type === "alerts" && Array.isArray(payload.alerts) && payload.alerts.length) {
            setAlerts((prev) => [...prev, ...payload.alerts!]);
          } else if (payload.type === "briefing") {
            // Only show briefings addressed to the current user — prevents fan-out data leaks
            if (!currentUserId || payload.user_id === currentUserId) {
              setBriefings((prev) => [...prev, { text: payload.text ?? "", user_id: payload.user_id ?? "", ts: payload.ts ?? Date.now() }]);
            }
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

  return { alerts, dismissAlert, briefings, dismissBriefing };
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
