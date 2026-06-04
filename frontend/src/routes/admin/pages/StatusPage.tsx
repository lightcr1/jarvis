import React, { useEffect, useState } from "react";
import { apiRequest } from "../../../shared/api/client";
import { fetchAdminStatusSummary } from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

type HealthPayload = { ok?: boolean; [key: string]: unknown };
type RagStatusPayload = { updated_at?: number; counts?: Record<string, number>; [key: string]: unknown };

function fmtTs(ts: number): string {
  if (!ts) return "—";
  return new Date(ts > 1e10 ? ts : ts * 1000).toLocaleString("en-GB", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

export function StatusPage() {
  const J = useJ();
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [rag, setRag] = useState<RagStatusPayload | null>(null);
  const [settings, setSettings] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchStatus = React.useCallback(() => {
    Promise.allSettled([
      apiRequest<HealthPayload>("/health"),
      apiRequest<RagStatusPayload>("/rag/status").catch(() => null),
      fetchAdminStatusSummary(),
    ]).then(([healthRes, ragRes, summaryRes]) => {
      if (healthRes.status === "fulfilled") setHealth(healthRes.value);
      if (ragRes.status === "fulfilled" && ragRes.value) setRag(ragRes.value);
      if (summaryRes.status === "fulfilled") setSettings(summaryRes.value.settings || null);
      setLastUpdated(new Date().toLocaleTimeString());
    }).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const ragCounts = Object.entries(rag?.counts || {});
  const totalRagSources = ragCounts.reduce((sum, [, v]) => sum + Number(v || 0), 0);

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6,
  };
  const eyebrow: React.CSSProperties = {
    fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
  };

  if (loading) {
    return <div style={{ padding: 40, color: J.textSec, fontSize: 13 }}>Loading status…</div>;
  }

  const backendOk = health?.ok !== false;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {lastUpdated && (
        <div style={{ fontSize: 11, color: J.textMuted, textAlign: "right" }}>Last updated: {lastUpdated}</div>
      )}

      {/* ── Metrics ── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 10 }}>
        {[
          { label: "Backend", value: backendOk ? "ok" : "down", accent: backendOk ? J.success : J.error },
          { label: "RAG sources", value: totalRagSources },
          { label: "Source types", value: ragCounts.length },
          { label: "RAG last sync", value: rag?.updated_at ? fmtTs(rag.updated_at) : "—", small: true },
        ].map(({ label, value, accent, small }) => (
          <div key={label} style={{ ...card, padding: "12px 16px" }}>
            <div style={{ ...eyebrow, marginBottom: 4 }}>{label}</div>
            <div style={{ fontSize: small ? 13 : 22, fontWeight: 700, color: (accent as string | undefined) || J.text }}>
              {value}
            </div>
          </div>
        ))}
      </div>

      {/* ── Backend health ── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr", gap: 14 }}>
        <div style={{ ...card, padding: "14px 18px" }}>
          <div style={{ ...eyebrow, marginBottom: 12 }}>Backend health</div>
          {health ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 0, borderRadius: 4, overflow: "hidden", border: `1px solid ${J.border}` }}>
              {Object.entries(health).map(([k, v], i, arr) => (
                <div key={k} style={{
                  display: "flex", justifyContent: "space-between", padding: "6px 10px",
                  borderBottom: i < arr.length - 1 ? `1px solid ${J.border}` : "none",
                  background: i % 2 === 1 ? J.bg1 : "transparent", fontSize: 12,
                }}>
                  <span style={{ color: J.textSec }}>{k}</span>
                  <strong style={{ color: k === "ok" ? (v ? J.success : J.error) : J.text, fontFamily: "monospace" }}>
                    {typeof v === "boolean" ? (v ? "true" : "false") : v == null ? "—" : String(v)}
                  </strong>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: J.error }}>Health endpoint unreachable.</div>
          )}
        </div>

        {/* ── RAG knowledge base ── */}
        <div style={{ ...card, padding: "14px 18px" }}>
          <div style={{ ...eyebrow, marginBottom: 12 }}>RAG knowledge base</div>
          {ragCounts.length > 0 ? (
            <>
              <div style={{ borderRadius: 4, overflow: "hidden", border: `1px solid ${J.border}` }}>
                <div style={{
                  display: "grid", gridTemplateColumns: "1fr 80px",
                  padding: "6px 10px", background: J.bg1, borderBottom: `1px solid ${J.border}`,
                  fontSize: 10, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em",
                }}>
                  <div>Source type</div><div>Documents</div>
                </div>
                {ragCounts.map(([k, v], i) => (
                  <div key={k} style={{
                    display: "grid", gridTemplateColumns: "1fr 80px",
                    padding: "7px 10px", borderBottom: i < ragCounts.length - 1 ? `1px solid ${J.border}` : "none",
                    background: i % 2 === 1 ? J.bg1 : "transparent",
                  }}>
                    <code style={{ fontSize: 11, fontFamily: "monospace", color: J.text }}>{k}</code>
                    <strong style={{ fontSize: 13, color: J.amber }}>{v}</strong>
                  </div>
                ))}
              </div>
              {rag?.updated_at && (
                <div style={{ fontSize: 10, color: J.textMuted, marginTop: 8 }}>Last indexed: {fmtTs(rag.updated_at)}</div>
              )}
            </>
          ) : (
            <div style={{ fontSize: 12, color: J.textMuted }}>RAG not configured or no documents indexed.</div>
          )}
        </div>
      </div>

      {/* ── Effective runtime settings ── */}
      {settings && (
        <div style={{ ...card, padding: "14px 18px" }}>
          <div style={{ ...eyebrow, marginBottom: 4 }}>Effective runtime settings</div>
          <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 12 }}>
            Environment variables + admin settings merged. Env vars take precedence.
          </div>
          <div style={{ borderRadius: 4, overflow: "hidden", border: `1px solid ${J.border}` }}>
            {Object.entries(settings).map(([k, v], i, arr) => (
              <div key={k} style={{
                display: "flex", gap: 12, padding: "7px 12px", alignItems: "baseline",
                borderBottom: i < arr.length - 1 ? `1px solid ${J.border}` : "none",
                background: i % 2 === 1 ? J.bg1 : "transparent",
              }}>
                <code style={{ flex: "0 0 220px", fontSize: 11, fontFamily: "monospace", color: J.textSec }}>{k}</code>
                <code style={{ fontSize: 11, fontFamily: "monospace", color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {typeof v === "boolean" ? (v ? "true" : "false") : v == null ? "—" : String(v)}
                </code>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
