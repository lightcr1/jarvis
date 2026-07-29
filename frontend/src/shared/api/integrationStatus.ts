import { useEffect, useState } from "react";
import { apiRequest, getSessionToken, isGuestMode } from "./client";

export type IntegrationStatus = "checking" | "not_configured" | "online" | "offline" | "connected";

export type IntegrationStatusMap = {
  proxmox: IntegrationStatus;
  ha: IntegrationStatus;
};

type ProxmoxHealth = { configured: boolean; hosts: Array<{ healthy: boolean }> };
type HomeAssistantHealth = { integration: { configured: boolean } };

export function useIntegrationStatus(): IntegrationStatusMap {
  const [status, setStatus] = useState<IntegrationStatusMap>({ proxmox: "checking", ha: "checking" });

  useEffect(() => {
    if (!getSessionToken() && !isGuestMode()) return;
    let cancelled = false;
    Promise.allSettled([
      apiRequest<ProxmoxHealth>("/proxmox/health", { includeUser: true }),
      apiRequest<HomeAssistantHealth>("/home-assistant/health", { includeUser: true }),
    ]).then(([px, ha]) => {
      if (cancelled) return;

      let proxmox: IntegrationStatus = "offline";
      if (px.status === "fulfilled") {
        const data = px.value;
        proxmox = !data.configured ? "not_configured" : data.hosts.some(h => h.healthy) ? "online" : "offline";
      }

      let haStatus: IntegrationStatus = "offline";
      if (ha.status === "fulfilled") {
        haStatus = ha.value.integration?.configured ? "connected" : "not_configured";
      }

      setStatus({ proxmox, ha: haStatus });
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}
