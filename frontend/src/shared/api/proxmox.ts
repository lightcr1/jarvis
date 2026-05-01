import { apiRequest } from "./client";

export type ProxmoxResource = {
  vmid: number | string;
  name?: string;
  status?: string;
  cpu?: number;
  maxcpu?: number;
  mem?: number;
  maxmem?: number;
  uptime?: number;
  type?: string;
};

export type ProxmoxNodeHealth = {
  node: string;
  status: string;
  online: boolean;
  cpu?: number;
  maxcpu?: number;
  mem?: number;
  maxmem?: number;
  vms: ProxmoxResource[];
  containers: ProxmoxResource[];
};

export type ProxmoxHostHealth = {
  id: string;
  name: string;
  base_url: string;
  verify_tls: boolean;
  healthy: boolean;
  error?: string;
  nodes: ProxmoxNodeHealth[];
};

export type ProxmoxHealthResponse = {
  configured: boolean;
  hosts: ProxmoxHostHealth[];
  summary: {
    hosts: number;
    nodes: number;
    vms: number;
    containers: number;
    running: number;
    stopped: number;
  };
  hint?: string;
};

export async function fetchProxmoxHealth() {
  return apiRequest<ProxmoxHealthResponse>("/proxmox/health", { includeUser: true });
}
