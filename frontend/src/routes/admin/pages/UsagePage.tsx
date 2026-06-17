import React, { useEffect, useState, useCallback } from "react";
import { fetchAdminUsage, type UsageSummary } from "../../../shared/api/billing";
import { useJ } from "../../../screens/jarvis-shared";

function fmtTs(ts: number): string {
  if (!ts) return "—";
  const d = new Date(ts > 1e10 ? ts : ts * 1000);
  return d.toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

function fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function DailyCostChart({ buckets, J }: {
  buckets: Array<{ bucket_ts: number; cost_chf: number; requests: number }>;
  J: ReturnType<typeof useJ>;
}) {
  const maxCost = Math.max(...buckets.map(b => b.cost_chf), 0.001);
  const W = 600, H = 60, padX = 2;
  const barW = buckets.length > 0 ? (W - padX * (buckets.length - 1)) / Math.max(buckets.length, 1) : W;

  if (buckets.length === 0) {
    return (
      <div style={{ height: H, display: "flex", alignItems: "center", justifyContent: "center", color: J.textMuted, fontSize: 12 }}>
        No usage data for this period.
      </div>
    );
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: H, display: "block" }}>
      {buckets.map((b, i) => {
        const barH = Math.max((b.cost_chf / maxCost) * (H - 12), b.cost_chf > 0 ? 3 : 1);
        const x = i * (barW + padX);
        const isCurrent = i === buckets.length - 1;
        return (
          <g key={b.bucket_ts}>
            <rect
              x={x} y={H - barH} width={barW} height={barH} rx={2}
              fill={isCurrent ? J.amber : J.amberDim.replace("0.1)", "0.35)")}
            />
            {i % Math.max(1, Math.floor(buckets.length / 7)) === 0 && (
              <text x={x + barW / 2} y={H - barH - 3} textAnchor="middle"
                fill={J.textMuted} fontSize={8} fontFamily="monospace">
                {fmtDate(b.bucket_ts)}
              </text>
            )}
            <title>{`${fmtDate(b.bucket_ts)} — CHF ${b.cost_chf.toFixed(4)} (${b.requests} req)`}</title>
          </g>
        );
      })}
    </svg>
  );
}

export function UsagePage() {
  const J = useJ();
  const [data, setData] = useState<UsageSummary | null>(null);
  const [loadedAt, setLoadedAt] = useState<Date | null>(null);
  const [error, setError] = useState("");
  const [filterUserId, setFilterUserId] = useState("");
  const [filterProvider, setFilterProvider] = useState("");
  const [filterDays, setFilterDays] = useState(7);

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await fetchAdminUsage({
        user_id: filterUserId.trim() || undefined,
        provider: filterProvider.trim() || undefined,
        days: filterDays,
      });
      setData(result);
      setLoadedAt(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load usage.");
    }
  }, [filterUserId, filterProvider, filterDays]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 30_000);
    return () => window.clearInterval(id);
  }, [load]);

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: "16px 18px",
  };
  const inp: React.CSSProperties = {
    padding: "5px 9px", fontSize: 12, borderRadius: 4,
    background: J.bg3, border: `1px solid ${J.border}`, color: J.text, outline: "none",
  };

  const PROVIDERS = ["", "openrouter", "anthropic", "openai", "gemini", "mistral", "deepseek", "local"];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>

      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: J.text }}>Usage</div>
          {loadedAt && (
            <div style={{ fontSize: 11, color: J.textMuted, marginTop: 2 }}>
              Updated {loadedAt.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
            </div>
          )}
        </div>
        <button
          onClick={() => void load()}
          style={{
            padding: "6px 14px", fontSize: 12, borderRadius: 4, cursor: "pointer",
            background: J.amberDim, color: J.amber, border: `1px solid ${J.borderAccent}`,
          }}
        >
          Refresh
        </button>
      </div>

      {/* Filter bar */}
      <div style={{ ...card, display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", padding: "12px 18px" }}>
        <span style={{ fontSize: 12, color: J.textSec, flexShrink: 0 }}>Filters:</span>
        <input
          style={{ ...inp, width: 160 }}
          placeholder="User ID"
          value={filterUserId}
          onChange={e => setFilterUserId(e.target.value)}
        />
        <select
          style={{ ...inp, width: 140 }}
          value={filterProvider}
          onChange={e => setFilterProvider(e.target.value)}
        >
          {PROVIDERS.map(p => (
            <option key={p} value={p}>{p || "All providers"}</option>
          ))}
        </select>
        <select
          style={{ ...inp, width: 100 }}
          value={filterDays}
          onChange={e => setFilterDays(Number(e.target.value))}
        >
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={30}>30 days</option>
        </select>
        <button
          onClick={() => void load()}
          style={{
            padding: "5px 14px", fontSize: 12, fontWeight: 600, borderRadius: 4, cursor: "pointer",
            background: J.amber, color: J.bg0, border: "none",
          }}
        >
          Apply
        </button>
        {error && <span style={{ fontSize: 12, color: J.error }}>{error}</span>}
      </div>

      {data ? (
        <>
          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 10 }}>
            {[
              { label: "Total requests", value: data.aggregate["request_count"] ?? 0 },
              { label: "Total tokens", value: (data.aggregate["total_tokens"] ?? 0).toLocaleString() },
              { label: "Total cost CHF", value: `CHF ${(data.aggregate["total_cost_chf"] ?? 0).toFixed(4)}`, accent: J.amber },
              { label: "Total cost USD", value: `$${(data.aggregate["total_cost_usd"] ?? 0).toFixed(4)}` },
              { label: "Input tokens", value: (data.aggregate["total_input_tokens"] ?? 0).toLocaleString() },
              { label: "Output tokens", value: (data.aggregate["total_output_tokens"] ?? 0).toLocaleString() },
            ].map(({ label, value, accent }) => (
              <div key={label} style={{ ...card, padding: "12px 16px" }}>
                <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>{label}</div>
                <div style={{ fontSize: 18, fontWeight: 700, color: (accent as string | undefined) || J.text }}>{value}</div>
              </div>
            ))}
          </div>

          {/* Daily cost chart */}
          <div style={card}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>
              Daily cost (last {filterDays} days)
            </div>
            <DailyCostChart buckets={data.daily_buckets} J={J} />
          </div>

          {/* Recent usage table */}
          <div style={card}>
            <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 12 }}>
              Recent requests ({(data.recent as unknown[]).length})
            </div>
            {(data.recent as unknown[]).length === 0 ? (
              <div style={{ color: J.textMuted, fontSize: 12, padding: "8px 0" }}>No recent usage.</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                  <thead>
                    <tr>
                      {["Time", "User", "Provider", "Model", "Tokens in", "Tokens out", "Cost CHF", "Status"].map(h => (
                        <th key={h} style={{ textAlign: "left", padding: "5px 8px", borderBottom: `1px solid ${J.border}`, color: J.textMuted, fontWeight: 500, whiteSpace: "nowrap" }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(data.recent as Array<Record<string, unknown>>).map((row, i) => {
                      const status = String(row["request_status"] ?? "ok");
                      const statusColor = status === "ok" ? J.success : status === "blocked" ? J.warn : J.error;
                      return (
                        <tr key={i} style={{ borderBottom: `1px solid ${J.border}` }}>
                          <td style={{ padding: "5px 8px", color: J.textSec, whiteSpace: "nowrap" }}>{fmtTs(Number(row["ts"] ?? 0))}</td>
                          <td style={{ padding: "5px 8px", color: J.textSec, fontFamily: "monospace", maxWidth: 120, overflow: "hidden", textOverflow: "ellipsis" }}>
                            {String(row["user_id"] ?? "—").slice(0, 12)}
                          </td>
                          <td style={{ padding: "5px 8px", color: J.text }}>{String(row["provider"] ?? "—")}</td>
                          <td style={{ padding: "5px 8px", color: J.textSec, fontFamily: "monospace", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis" }}>{String(row["model"] ?? "—")}</td>
                          <td style={{ padding: "5px 8px", color: J.textSec }}>{String(row["input_tokens"] ?? 0)}</td>
                          <td style={{ padding: "5px 8px", color: J.textSec }}>{String(row["output_tokens"] ?? 0)}</td>
                          <td style={{ padding: "5px 8px", color: J.amber, fontFamily: "monospace" }}>
                            {Number(row["estimated_cost_chf"] ?? 0).toFixed(6)}
                          </td>
                          <td style={{ padding: "5px 8px", color: statusColor, fontWeight: 500 }}>{status}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      ) : (
        <div style={{ color: J.textMuted, fontSize: 13, padding: "24px 0" }}>Loading…</div>
      )}
    </div>
  );
}
