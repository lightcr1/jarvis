import { useEffect, useState } from "react";

export type JarvisStatusEvent = { kind: string; ts: number };

export type JarvisLiveStatus = {
  state: "idle" | "recording" | "processing" | "speaking";
  version: number;
  updated_at: number;
  active: number;
  counts: Record<string, number>;
  lastEvent: JarvisStatusEvent | null;
  connected: boolean;
};

const DEFAULT_STATUS: JarvisLiveStatus = {
  state: "idle",
  version: 0,
  updated_at: 0,
  active: 0,
  counts: {},
  lastEvent: null,
  connected: false,
};

function wsUrl(path: string) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}${path}`;
}

export function useJarvisLiveStatus() {
  const [status, setStatus] = useState<JarvisLiveStatus>(DEFAULT_STATUS);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let retryTimer: number | null = null;
    let closed = false;

    const connect = () => {
      socket = new WebSocket(wsUrl("/ws/status"));
      socket.onopen = () => setStatus((prev) => ({ ...prev, connected: true }));
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data) as JarvisLiveStatus & { last_event?: JarvisStatusEvent | null };
          setStatus({
            state: payload.state || "idle",
            version: Number(payload.version || 0),
            updated_at: Number(payload.updated_at || 0),
            active: Number(payload.active || 0),
            counts: payload.counts || {},
            lastEvent: payload.last_event || null,
            connected: true,
          });
        } catch {
          // ignore malformed payloads
        }
      };
      socket.onclose = () => {
        setStatus((prev) => ({ ...prev, connected: false }));
        if (closed) return;
        retryTimer = window.setTimeout(connect, 1500);
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

  return status;
}
