import React, { useEffect, useState, useCallback } from "react";
import { fetchAutonomyStatus, updateAutonomyStatus, fetchAgentGrants, decideAgentGrant, revokeAgentGrant, type AgentGrantRequest, type AutonomyStatus } from "../../../shared/api/admin";
import { useJ } from "../../../screens/jarvis-shared";

export function AutonomyPage() {
  const J = useJ();
  const [status, setStatus] = useState<AutonomyStatus | null>(null);
  const [grants, setGrants] = useState<AgentGrantRequest[]>([]);
  const [grantError, setGrantError] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [ok, setOk] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const result = await fetchAutonomyStatus();
      setStatus(result.status);
      setNote(result.status.note ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Autonomy status could not be loaded.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const refreshGrants = useCallback(async () => {
    try {
      const result = await fetchAgentGrants();
      setGrants(result.requests);
      setGrantError("");
    } catch (e) {
      setGrantError(e instanceof Error ? e.message : "Freigaben konnten nicht geladen werden.");
    }
  }, []);

  useEffect(() => { void refreshGrants(); }, [refreshGrants]);

  const changeGrant = useCallback(async (id: string, action: "approve" | "reject" | "revoke") => {
    setSaving(true);
    try {
      if (action === "revoke") await revokeAgentGrant(id);
      else await decideAgentGrant(id, action === "approve");
      await refreshGrants();
    } catch (e) {
      setGrantError(e instanceof Error ? e.message : "Freigabe fehlgeschlagen.");
    } finally {
      setSaving(false);
    }
  }, [refreshGrants]);

  const toggle = useCallback(async (enabled: boolean) => {
    setSaving(true);
    setError("");
    setOk("");
    try {
      const result = await updateAutonomyStatus(enabled, note.trim());
      setStatus(result.status);
      setOk(enabled ? "Autonomes Arbeiten ist AKTIV — Jarvis beginnt bzw. setzt seine Runden fort." : "Autonomes Arbeiten ist PAUSIERT — Jarvis wartet auf explizite Aufgaben.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Toggle failed.");
    } finally {
      setSaving(false);
    }
  }, [note]);

  const card: React.CSSProperties = {
    background: J.bg2,
    border: `1px solid ${J.border}`,
    borderRadius: 6,
    padding: "16px 18px",
    marginBottom: 12,
  };

  return (
    <div style={{ maxWidth: 720 }}>
      <h2 style={{ margin: "0 0 4px" }}>Autonomie</h2>
      <p style={{ color: J.textMuted, margin: "0 0 16px", fontSize: 13 }}>
        Steuert, ob Jarvis von sich aus kontinuierlich arbeitet (Auto-Runden,
        Git-Verbesserungen, To-do-Queue). Deine eigenen Anweisungen haben immer
        Vorrang — dieser Schalter pausiert nur die Selbstständigkeit.
      </p>

      <div style={card}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <div>
            <div style={{ fontWeight: 600 }}>
              Autonomy Mode: <span style={{ color: status?.enabled ? "#22c55e" : J.amber }}>
                {status?.enabled ? "AN" : "AUS"}
              </span>
            </div>
            {status?.updated_at && (
              <div style={{ color: J.textMuted, fontSize: 12, marginTop: 4 }}>
                zuletzt geändert: {status.updated_at}
              </div>
            )}
            {error && <div style={{ color: "#ef4444", fontSize: 13, marginTop: 6 }}>{error}</div>}
            {ok && <div style={{ color: "#22c55e", fontSize: 13, marginTop: 6 }}>{ok}</div>}
          </div>
          <button
            disabled={saving}
            onClick={() => toggle(!status?.enabled)}
            style={{
              padding: "8px 14px",
              borderRadius: 6,
              border: "1px solid",
              borderColor: J.border,
              background: status?.enabled ? "#b83232" : "#2474e5",
              color: "#fff",
              cursor: "pointer",
              fontSize: 14,
            }}
          >
            {saving ? "…" : status?.enabled ? "Autonomie pausieren" : "Autonomie aktivieren"}
          </button>
        </div>
      </div>

      <div style={card}>
        <label style={{ display: "block", fontWeight: 600, marginBottom: 6 }} htmlFor="autonomy-note">
          Notiz (optional, wird im Log festgehalten)
        </label>
        <input
          id="autonomy-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="z. B. 'bin im Meeting, keine Runden bis morgen'"
          style={{
            width: "100%",
            padding: "8px 10px",
            borderRadius: 6,
            border: `1px solid ${J.border}`,
            background: J.bg2,
            color: J.text,
            fontSize: 14,
          }}
        />
        <p style={{ color: J.textMuted, fontSize: 12, margin: "8px 0 0" }}>
          Der Notiztext wird beim nächsten Toggle zusammen mit dem Schalter
          gespeichert und steht im Audit-Log.
        </p>
      </div>

      <div style={card}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>Projektfreigaben (begrenzter Freigabekern)</div>
        <p style={{ color: J.textMuted, fontSize: 12 }}>
          Hier kannst du konkrete Ziele und Operationen genehmigen oder widerrufen. Das ist
          keine pauschale Berechtigung für Zahlungen, Nachrichten oder beliebige externe Tools;
          ausführende Werkzeuge brauchen eine separate technische Prüfung.
        </p>
        {grantError && <p role="alert" style={{ color: "#ef4444" }}>{grantError}</p>}
        <button type="button" onClick={() => void refreshGrants()}>Aktualisieren</button>
        {grants.length === 0 && <p style={{ color: J.textMuted }}>Keine Anfragen vorhanden.</p>}
        {grants.map((grant) => (
          <div key={grant.id} style={{ borderTop: `1px solid ${J.border}`, padding: "10px 0" }}>
            <div><b>{grant.kind}</b>: {grant.target} – {grant.operation}</div>
            <div style={{ fontSize: 12, color: J.textMuted }}>{grant.reason}</div>
            <div style={{ fontSize: 12 }}>Status: {grant.status} · Gültig bis: {new Date(grant.expires_at * 1000).toLocaleString()}</div>
            {grant.status === "pending" && (
              <div>
                <button disabled={saving} type="button" onClick={() => void changeGrant(grant.id, "approve")}>Genehmigen</button>{" "}
                <button disabled={saving} type="button" onClick={() => void changeGrant(grant.id, "reject")}>Ablehnen</button>
              </div>
            )}
            {grant.status === "approved" && (
              <button disabled={saving} type="button" onClick={() => void changeGrant(grant.id, "revoke")}>Widerrufen</button>
            )}
          </div>
        ))}
      </div>

      <div style={card}>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>So funktioniert es</div>
        <ul style={{ color: J.textMuted, fontSize: 13, margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
          <li><b>AN:</b> Jarvis arbeitet selbstständig weiter — wann immer das Modell erreichbar ist (Pod läuft), sucht er sich Arbeit und erledigt sie (AGENTS.md: Autonomy Mode).</li>
          <li><b>AUS:</b> Keine neuen autonomen Runden; er wartet auf deine expliziten Aufgaben. Aktivitäts-Log wird weitergeführt.</li>
          <li>Deine direkten Anweisungen (Chat/Task) unterbrechen autonome Arbeit nur kurz und werden nie verworfen.</li>
        </ul>
      </div>
    </div>
  );
}
