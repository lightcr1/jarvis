import { useEffect, useState } from "react";
import { getSessionToken } from "./client";

export type JarvisAlert = {
  id: string;
  level: string;
  title: string;
  message: string;
  source: string;
  code: string;
};

function wsUrl(path: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}

export function useJarvisAlerts() {
  const [alerts, setAlerts] = useState<JarvisAlert[]>([]);

  useEffect(() => {
    const token = getSessionToken();
    if (!token) return;

    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(wsUrl(`/ws/alerts?session=${encodeURIComponent(token)}`));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as { type?: string; alerts?: JarvisAlert[] };
          if (payload.type === "alerts" && Array.isArray(payload.alerts) && payload.alerts.length) {
            const incoming = payload.alerts;
            setAlerts((prev) => [...prev, ...incoming]);
          }
        } catch {
          // ignore malformed alert payloads
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

  return { alerts, dismissAlert };
}
