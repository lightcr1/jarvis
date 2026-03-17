import React, { useEffect, useState } from "react";
import { apiRequest } from "../../../shared/api/client";
import { fetchAdminStatusSummary } from "../../../shared/api/admin";

type HealthPayload = { ok?: boolean };
type RagStatusPayload = { updated_at?: number; counts?: Record<string, number> };

export function StatusPage() {
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [rag, setRag] = useState<RagStatusPayload | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    Promise.all([
      apiRequest<HealthPayload>("/health"),
      apiRequest<RagStatusPayload>("/rag/status"),
      fetchAdminStatusSummary(),
    ]).then(([healthData, ragData, summaryData]) => {
      setHealth(healthData);
      setRag(ragData);
      setSummary(summaryData.settings || null);
    }).catch(() => undefined);
  }, []);

  const totalSources = Object.values(rag?.counts || {}).reduce((sum, value) => sum + Number(value || 0), 0);

  return (
    <div className="page-stack">
      <div className="dashboard-grid">
        <div className="panel metric-card">
          <div className="eyebrow">Backend</div>
          <strong>{health?.ok === false ? "down" : "ok"}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">RAG sources</div>
          <strong>{totalSources}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Last refresh</div>
          <strong>{rag?.updated_at ? "ready" : "unknown"}</strong>
        </div>
        <div className="panel metric-card">
          <div className="eyebrow">Health endpoint</div>
          <strong>/health</strong>
        </div>
      </div>
      <div className="dashboard-grid">
        <div className="panel">
          <div className="eyebrow">Backend health</div>
          <pre>{JSON.stringify(health || { ok: false }, null, 2)}</pre>
        </div>
        <div className="panel span-2">
          <div className="eyebrow">RAG status</div>
          <pre>{JSON.stringify(rag || {}, null, 2)}</pre>
        </div>
      </div>
      <div className="panel">
        <div className="eyebrow">Effective settings snapshot</div>
        <pre>{JSON.stringify(summary || {}, null, 2)}</pre>
      </div>
    </div>
  );
}
