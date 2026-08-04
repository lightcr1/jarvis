import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { J, useJ, Spinner, IconFile, IconDownload, IconLock } from "../../screens/jarvis-shared";
import { PublicShareInfo, downloadPublicShare, fetchPublicShareInfo, formatBytes } from "../../shared/api/files";

export function SharedFilePage() {
  useJ();
  const { token } = useParams<{ token: string }>();
  const [info, setInfo] = useState<PublicShareInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [password, setPassword] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    fetchPublicShareInfo(token)
      .then(setInfo)
      .catch(err => setError(err instanceof Error ? err.message : "This link is invalid or has expired."))
      .finally(() => setLoading(false));
  }, [token]);

  const doDownload = async () => {
    if (!token || !info) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      await downloadPublicShare(token, info.filename, password || undefined);
    } catch (err) {
      setDownloadError(err instanceof Error ? err.message : "Download failed");
    } finally {
      setDownloading(false);
    }
  };

  const inp: React.CSSProperties = {
    width: "100%", boxSizing: "border-box", padding: "10px 12px", fontSize: 13,
    borderRadius: 6, background: "rgba(255,255,255,0.05)", border: `1px solid ${J.border}`,
    color: J.text, outline: "none",
  };

  return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minHeight: "100vh", background: J.bg0, padding: 24 }}>
      <div style={{ width: "100%", maxWidth: 420, background: J.bg2, border: `1px solid ${J.border}`, borderRadius: 12, padding: "32px 28px", boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
        <div style={{ width: 36, height: 36, borderRadius: 9, background: J.amberDim, border: `1px solid ${J.borderAccent}`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 16, fontWeight: 700, color: J.amber, marginBottom: 16 }}>J</div>
        <div style={{ fontSize: 11, color: J.textMuted, textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: 4 }}>Shared File</div>

        {loading && (
          <div style={{ display: "flex", alignItems: "center", gap: 8, color: J.textMuted, fontSize: 13, padding: "20px 0" }}>
            <Spinner size={14} /> Loading...
          </div>
        )}

        {!loading && error && (
          <div style={{ marginTop: 8, fontSize: 13, color: J.error, background: J.errorDim, border: `1px solid ${J.error}30`, borderRadius: 6, padding: "12px 14px" }}>
            {error}
          </div>
        )}

        {!loading && !error && info && (
          <>
            <div style={{ display: "flex", alignItems: "center", gap: 10, margin: "12px 0 20px" }}>
              <IconFile size={20} />
              <div style={{ minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, color: J.text, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{info.filename}</div>
                <div style={{ fontSize: 12, color: J.textMuted }}>{formatBytes(info.size_bytes)}</div>
              </div>
            </div>

            {info.requires_password && (
              <div style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 11, color: J.textMuted, marginBottom: 5, display: "flex", alignItems: "center", gap: 5 }}>
                  <IconLock size={11} /> Password required
                </div>
                <input
                  style={inp} type="password" value={password} autoFocus
                  onChange={e => setPassword(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") void doDownload(); }}
                  placeholder="Enter password"
                />
              </div>
            )}

            {downloadError && (
              <div style={{ fontSize: 12, color: J.error, background: J.errorDim, border: `1px solid ${J.error}30`, borderRadius: 5, padding: "8px 12px", marginBottom: 12 }}>
                {downloadError}
              </div>
            )}

            <button
              onClick={() => void doDownload()}
              disabled={downloading || (info.requires_password && !password)}
              style={{
                width: "100%", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                padding: "10px", fontSize: 13, fontWeight: 600, borderRadius: 6, cursor: "pointer",
                background: J.amber, color: J.bg0, border: "none",
                opacity: downloading || (info.requires_password && !password) ? 0.6 : 1,
              }}
            >
              {downloading ? <Spinner size={13} color={J.bg0} /> : <IconDownload size={14} />}
              {downloading ? "Downloading…" : "Download"}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
