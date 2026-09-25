import React, { useEffect, useState, useCallback } from "react";
import {
  fetchAgentSessions,
  fetchOwnerRequests,
  fetchLoopVersion,
  fetchAgentPatches,
  fetchAgentPatch,
  fetchRoundMetrics,
  decideAgentPatch,
  requestLoopRollout,
  decideOwnerRequest,
  agentSessionAction,
  type AgentSession,
  type OwnerRequest,
  type LoopVersion,
  type AgentPatch,
  type RoundMetricsAggregate,
} from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

function fmtTs(ts?: string): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function AgentMonitorPage() {
  const J = useJ();
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [requests, setRequests] = useState<OwnerRequest[]>([]);
  const [loopVersion, setLoopVersion] = useState<LoopVersion | null>(null);
  const [patches, setPatches] = useState<AgentPatch[]>([]);
  const [openPatch, setOpenPatch] = useState<string | null>(null);
  const [patchDiff, setPatchDiff] = useState("");
  const [patchFeedback, setPatchFeedback] = useState("");
  const [roundMetrics, setRoundMetrics] = useState<RoundMetricsAggregate | null>(null);
  const [rolloutMsg, setRolloutMsg] = useState("");
  const [readonly, setReadonly] = useState(false);
  const [reqError, setReqError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [feedback, setFeedback] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [s, r] = await Promise.all([fetchAgentSessions(), fetchOwnerRequests()]);
      setSessions(s.sessions);
      setRequests(r.requests);
      setReadonly(r.readonly);
      setReqError(r.error ?? "");
      fetchLoopVersion().then(setLoopVersion).catch(() => setLoopVersion(null));
      fetchAgentPatches().then((p) => setPatches(p.patches)).catch(() => setPatches([]));
      fetchRoundMetrics().then((m) => setRoundMetrics(m.aggregate)).catch(() => setRoundMetrics(null));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Monitor could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), 15_000); // 15s auto refresh
    return () => window.clearInterval(id);
  }, [load]);

  const decide = useCallback(async (req: OwnerRequest, decision: "approved" | "rejected") => {
    setFeedback("");
    try {
      await decideOwnerRequest(req.number, decision);
      setFeedback(`Anfrage #${req.number} → ${decision === "approved" ? "angenommen ✅" : "abgelehnt ❌"}. Jarvis übernimmt das Label in seiner nächsten Runde.`);
      void load();
    } catch (e) {
      setFeedback(`Fehler: ${e instanceof Error ? e.message : "Entscheidung fehlgeschlagen"}`);
    }
  }, [load]);

  const actOn = useCallback(async (s: AgentSession, action: "pause" | "run" | "interrupt") => {
    setFeedback("");
    try {
      await agentSessionAction(s.id, action);
      setFeedback(`Session ${s.id.slice(0, 8)} → ${{ pause: "pausiert", run: "fortgesetzt", interrupt: "stoppt" }[action]}`);
      setTimeout(() => void load(), 1500);
    } catch (e) {
      setFeedback(`Fehler: ${e instanceof Error ? e.message : "Aktion fehlgeschlagen"}`);
    }
  }, [load]);

  const decidePatch = useCallback(async (patch: AgentPatch, approve: boolean) => {
    setPatchFeedback("");
    try {
      const result = await decideAgentPatch(patch.id, approve, patch.message);
      setPatchFeedback(approve ? `PR #${result.pr?.number ?? "?"} angelegt.` : "Patch abgelehnt.");
      void load();
    } catch (e) {
      setPatchFeedback(`Fehler: ${e instanceof Error ? e.message : "Aktion fehlgeschlagen"}`);
    }
  }, [load]);

  const togglePatch = useCallback(async (patch: AgentPatch) => {
    if (openPatch === patch.id) { setOpenPatch(null); return; }
    setOpenPatch(patch.id);
    setPatchDiff("Laedt…");
    try {
      const result = await fetchAgentPatch(patch.id);
      setPatchDiff(result.patch.patch ?? "(kein Diff)");
    } catch (e) {
      setPatchDiff(`Diff konnte nicht geladen werden: ${e instanceof Error ? e.message : ""}`);
    }
  }, [openPatch]);

  const requestRollout = useCallback(async () => {
    setRolloutMsg("");
    try {
      await requestLoopRollout();
      setRolloutMsg("Rollout angefordert — der Host-Timer installiert beim nächsten Lauf.");
    } catch (e) {
      setRolloutMsg(`Fehler: ${e instanceof Error ? e.message : "Anforderung fehlgeschlagen"}`);
    }
  }, []);

  const statusIcon = (s: AgentSession) => {
    if (s.status === "running" || s.status === "active" || s.status === "starting" || s.status === "pending") return "🟢";
    if (s.status === "paused") return "⏸️";
    if (s.status === "waiting_for_confirmation") return "🟡";
    if (s.status === "error") return "🔴";
    if (s.status === "finished") return "✅";
    return "⚪";
  };

  const card: React.CSSProperties = {
    background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 6, padding: "14px 16px", marginBottom: 12,
  };
  const badge = (color: string) => ({
    display: "inline-block", padding: "2px 8px", borderRadius: 10, fontSize: 11,
    background: color, color: "#101418", marginRight: 6,
  });

  return (
    <div style={{ maxWidth: 860 }}>
      <h2 style={{ margin: "0 0 4px" }}>Jarvis — Agent Monitor</h2>
      <p style={{ color: J.textMuted, margin: "0 0 16px", fontSize: 13 }}>
        Live-Übersicht aller OpenHands-Sessions (auch autonom gestartete) und
        Jarvis' Anfragen an dich. Auto-Refresh alle 15 s — nur Metadaten.
      </p>
      {error && <div style={{ color: "#ef4444", marginBottom: 10 }}>{error}</div>}
      {feedback && <div style={{ color: "#22c55e", marginBottom: 10, fontSize: 13 }}>{feedback}</div>}

      {loopVersion && (
        <div style={card}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Autonomy-Loop Version</div>
          {loopVersion.installed_sha256 ? (
            <div style={{ fontSize: 13, color: J.textMuted }}>
              installiert: <code>{loopVersion.installed_sha256.slice(0, 12)}</code>
              {" · "}Repo: <code>{loopVersion.repo_sha256 ? loopVersion.repo_sha256.slice(0, 12) : "—"}</code>
              {loopVersion.drift && (
                <div style={{ color: J.amber, marginTop: 6 }}>
                  ⚠️ Drift: Die installierte Loop-Kopie weicht von der versionierten Quelle ab.
                  Rollout mit <code>scripts/agent/install_loop.sh</code>.
                  <div style={{ marginTop: 6 }}>
                    <button onClick={() => void requestRollout()}
                      style={{ padding: "5px 10px", borderRadius: 6, border: `1px solid ${J.border}`, background: J.bg3, color: J.text, cursor: "pointer", fontSize: 12 }}>
                      Rollout anfordern
                    </button>
                    {rolloutMsg && <div style={{ color: J.textMuted, fontSize: 12, marginTop: 4 }}>{rolloutMsg}</div>}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div style={{ color: J.textMuted, fontSize: 13 }}>
              Installierter Hash nicht verfügbar — <code>JARVIS_AUTONOMY_STATE_PATH</code> oder{" "}
              <code>JARVIS_AUTONOMY_LOOP_PATH</code> setzen. Repo:{" "}
              <code>{loopVersion.repo_sha256 ? loopVersion.repo_sha256.slice(0, 12) : "—"}</code>
            </div>
          )}
        </div>
      )}

      {roundMetrics && roundMetrics.rounds > 0 && (
        <div style={card}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>Runden — Effizienz</div>
          <div style={{ fontSize: 13, color: J.textMuted }}>
            {roundMetrics.rounds} Runden · {roundMetrics.gpu_hours} GPU-h · {roundMetrics.total_tokens} Tokens
            {roundMetrics.submitted > 0 && <>{" · "}{roundMetrics.submitted} eingereicht</>}
            {roundMetrics.tokens_per_submitted != null && <>{" · "}~{roundMetrics.tokens_per_submitted} Tokens/Aufgabe</>}
            {roundMetrics.patches_per_gpu_hour != null && <>{" · "}{roundMetrics.patches_per_gpu_hour} Patches/GPU-h</>}
            {roundMetrics.cost_estimate > 0 && <>{" · "}${roundMetrics.cost_estimate}</>}
          </div>
        </div>
      )}

      {patches.length > 0 && (
        <div style={card}>
          <div style={{ fontWeight: 600, marginBottom: 6 }}>
            Eingereichte Agent-Patches ({patches.length})
          </div>
          {patchFeedback && (
            <div style={{ color: "#22c55e", fontSize: 12, marginBottom: 6 }}>{patchFeedback}</div>
          )}
          {patches.map((p) => (
            <div key={p.id} style={{ padding: "8px 0", borderBottom: `1px solid ${J.border}`, fontSize: 14 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <span style={{ flex: 1 }}>
                  <span style={badge(p.status === "pending" ? J.amberDim : J.bg3)}>{p.status}</span>
                  {p.branch} — {p.message}
                  <div style={{ color: J.textMuted, fontSize: 12, marginTop: 2 }}>
                    {p.repository} · {p.paths.join(", ")}
                  </div>
                </span>
                <span style={{ whiteSpace: "nowrap" }}>
                  <button onClick={() => togglePatch(p)} style={{ marginRight: 4, padding: "4px 8px", borderRadius: 6, border: `1px solid ${J.border}`, background: J.bg3, color: J.text, cursor: "pointer", fontSize: 12 }}>
                    {openPatch === p.id ? "Diff schließen" : "Diff"}
                  </button>
                  {p.status === "pending" && (
                    <>
                      <button onClick={() => decidePatch(p, true)} style={{ marginRight: 4, padding: "4px 8px", borderRadius: 6, border: `1px solid ${J.border}`, background: "#22c55e", color: "#fff", cursor: "pointer", fontSize: 12 }}>PR anlegen</button>
                      <button onClick={() => decidePatch(p, false)} style={{ padding: "4px 8px", borderRadius: 6, border: `1px solid ${J.border}`, background: "#b83232", color: "#fff", cursor: "pointer", fontSize: 12 }}>Ablehnen</button>
                    </>
                  )}
                </span>
              </div>
              {openPatch === p.id && (
                <pre style={{ marginTop: 6, maxHeight: 240, overflow: "auto", fontSize: 11, background: J.bg3, padding: 8, borderRadius: 6 }}>{patchDiff}</pre>
              )}
            </div>
          ))}
        </div>
      )}

      <div style={card}>
        <div style={{ fontWeight: 600, marginBottom: 8 }}>
          Sessions ({sessions.length})
        </div>
        {sessions.length === 0 && (
          <div style={{ color: J.textMuted, fontSize: 13 }}>
            Keine aktiven Sessions. Sobald Jarvis arbeitet (autonom oder auf deine Aufgabe), erscheinen sie hier.
          </div>
        )}
        {sessions.map((s) => (
          <div key={s.id || s.title} style={{ padding: "8px 0", borderBottom: `1px solid ${J.border}`, fontSize: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <span style={{ cursor: "pointer", flex: 1 }} onClick={() => setExpanded(expanded === s.id ? null : s.id)}>
                {statusIcon(s)} {s.title}
                {s.kind === "autonomy" && (
                  <span style={badge(s.focus === "ideas" ? "#a78bfa" : "#38bdf8")}>
                    {s.focus === "ideas" ? "✨ Ideen" : "🔧 Engineering"}
                  </span>
                )}
                {s.status === "waiting_for_confirmation" && (
                  <span style={badge("#fbbf24")}>wartet auf dich</span>
                )}
              </span>
              <span style={{ color: J.textMuted, fontSize: 12, whiteSpace: "nowrap" }}>
                {s.status} · {fmtTs(s.updated_at)}
              </span>
              {s.kind === "autonomy" && (
                <span style={{ whiteSpace: "nowrap" }}>
                  {s.status === "running" || s.status === "starting" || s.status === "pending" ? (
                    <button onClick={() => actOn(s, "pause")} style={{ marginRight: 4, padding: "4px 8px", borderRadius: 6, border: `1px solid ${J.border}`, background: J.bg3, color: J.text, cursor: "pointer", fontSize: 12 }}>⏸️ Pause</button>
                  ) : (s.status === "paused" ? (
                    <button onClick={() => actOn(s, "run")} style={{ marginRight: 4, padding: "4px 8px", borderRadius: 6, border: `1px solid ${J.border}`, background: "#22c55e", color: "#fff", cursor: "pointer", fontSize: 12 }}>▶️ Fortsetzen</button>
                  ) : null)}
                  <button onClick={() => actOn(s, "interrupt")} title="Sofort stoppen (beendet die Runde)" style={{ padding: "4px 8px", borderRadius: 6, border: `1px solid ${J.border}`, background: "#b83232", color: "#fff", cursor: "pointer", fontSize: 12 }}>
                    ⏹ Stopp
                  </button>
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>
          Anfragen & Vorschläge ({requests.length})
        </div>
        {readonly && (
          <div style={{ color: J.amber, fontSize: 12, marginBottom: 6 }}>
            Read-only: Für aktive Entscheidungen GITHUB_TOKEN in der jarvis.env setzen.
            {reqError ? ` (${reqError})` : ""}
          </div>
        )}
        {requests.length === 0 && (
          <div style={{ color: J.textMuted, fontSize: 13 }}>
            Keine offenen Anfragen. Jarvis meldet sich hier, wenn er deine Freigabe, Entscheidung oder einen Zugang braucht.
          </div>
        )}
        {requests.map((r) => (
          <div key={r.number} style={{ padding: "8px 0", borderBottom: `1px solid ${J.border}`, fontSize: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
              <span style={{ flex: 1 }}>
                <span style={badge(J.amberDim)}>#{r.number}</span> {r.title}
                <div style={{ color: J.textMuted, fontSize: 12, marginTop: 2 }}>
                  {r.labels.join(", ")} · {fmtTs(r.created_at)}
                  {r.url ? <> · <a href={r.url} target="_blank" rel="noreferrer" style={{ color: "#2474e5" }}>GitHub</a></> : null}
                </div>
              </span>
              <span style={{ whiteSpace: "nowrap" }}>
                {!readonly && (
                  <>
                    <button onClick={() => decide(r, "approved")} style={{ marginRight: 6, padding: "5px 10px", borderRadius: 6, border: "1px solid", borderColor: J.border, background: "#22c55e", color: "#fff", cursor: "pointer" }}>✅ Annehmen</button>
                    <button onClick={() => decide(r, "rejected")} style={{ padding: "5px 10px", borderRadius: 6, border: "1px solid", borderColor: J.border, background: "#b83232", color: "#fff", cursor: "pointer" }}>❌ Ablehnen</button>
                  </>
                )}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
