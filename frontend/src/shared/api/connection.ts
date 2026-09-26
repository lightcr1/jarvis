import { useEffect, useState } from "react";

export type ConnectionLevel = "live" | "reconnecting" | "offline";

export function isOnline(): boolean {
  if (typeof navigator === "undefined") return true;
  return navigator.onLine !== false;
}

export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState<boolean>(isOnline);
  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    // Re-read once on mount in case the value changed before the listener attached.
    setOnline(isOnline());
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);
  return online;
}

/**
 * "offline" = the device has no network; "reconnecting" = online but the live
 * channel is down; "live" = both up. Actions are never queued for replay while
 * not live, so a reconnect cannot silently repeat an earlier action.
 */
export function connectionLevel(online: boolean, connected: boolean): ConnectionLevel {
  if (!online) return "offline";
  return connected ? "live" : "reconnecting";
}

export const CONNECTION_LABEL: Record<ConnectionLevel, string> = {
  live: "Live",
  reconnecting: "Reconnecting",
  offline: "Offline",
};

export function connectionColor(level: ConnectionLevel): string {
  if (level === "live") return "#22c55e";
  if (level === "reconnecting") return "#f59e0b";
  return "#ef4444";
}
