import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { AppShell } from "../../shared/layout/AppShell";
import { apiRequest, UserPreferences, clearUnlockToken, setUnlockToken } from "../../shared/api/client";
import {
  createChatSession,
  deleteChatSession,
  getChatSession,
  listChatSessions,
  sendChatMessage,
  transcribeAudio,
} from "../../shared/api/chat";
import type { ChatSessionListItem } from "../../shared/api/chat";
import { OverlayDialog } from "../../shared/ui/OverlayDialog";
import { ChatComposer } from "./components/ChatComposer";
import { ChatEmptyState } from "./components/ChatEmptyState";
import { SidebarSection } from "./components/SidebarSection";

function formatRelativeTime(timestamp: number) {
  if (!timestamp) return "just now";
  const deltaMin = Math.max(1, Math.round((Date.now() - timestamp * 1000) / 60000));
  if (deltaMin < 60) return `${deltaMin}m ago`;
  const deltaHours = Math.round(deltaMin / 60);
  if (deltaHours < 24) return `${deltaHours}h ago`;
  const deltaDays = Math.round(deltaHours / 24);
  return `${deltaDays}d ago`;
}

export function ChatPage() {
  const { user, preferences, savePreferences, isAdmin } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const conversationId = searchParams.get("c");
  const [sessions, setSessions] = useState<ChatSessionListItem[]>([]);
  const [messages, setMessages] = useState<Array<{ role: string; text: string }>>([]);
  const [input, setInput] = useState("");
  const [activeId, setActiveId] = useState<string | null>(conversationId || null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [prefsOpen, setPrefsOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [draftPrefs, setDraftPrefs] = useState<UserPreferences>(preferences);
  const [voiceBusy, setVoiceBusy] = useState(false);
  const [workspaceOpen, setWorkspaceOpen] = useState(true);
  const [conversationsOpen, setConversationsOpen] = useState(true);

  const canSavePrefs = !!user;

  async function deleteSession(id: string) {
    await deleteChatSession(id);

    const nextSessions = sessions.filter((session) => session.id !== id);
    setSessions(nextSessions);

    if (activeId === id) {
      const nextId = nextSessions[0]?.id || null;
      setActiveId(nextId);
      if (nextId) {
        await loadSession(nextId);
      } else {
        setMessages([]);
        navigate("/chat");
      }
    }
  }

  const sidebar = (
    <>
      <button className="ui-button primary wide" onClick={() => createSession()}>New chat</button>
      <SidebarSection title="Workspaces" open={workspaceOpen} onToggle={() => setWorkspaceOpen((value) => !value)}>
        {workspaceOpen ? (
          <div className="workspace-links">
            <button className="sidebar-row-link" onClick={() => navigate("/orb")}>Orb</button>
            {isAdmin ? <button className="sidebar-row-link" onClick={() => navigate("/dashboard")}>Dashboard</button> : null}
          </div>
        ) : null}
      </SidebarSection>
      <SidebarSection title="Conversations" open={conversationsOpen} onToggle={() => setConversationsOpen((value) => !value)}>
        {conversationsOpen ? (
          <div className="conversation-list">
            {sessions.map((session) => (
              <div key={session.id} className={`conversation-card${session.id === activeId ? " active" : ""}`}>
                <button className="conversation-main" onClick={() => loadSession(session.id)}>
                  <span>{session.title}</span>
                  <small>{session.message_count} messages · {formatRelativeTime(session.updated_at || session.created_at)}</small>
                </button>
                <button className="conversation-delete" onClick={() => deleteSession(session.id)} aria-label={`Delete ${session.title}`}>×</button>
              </div>
            ))}
          </div>
        ) : null}
      </SidebarSection>
    </>
  );

  const topActions = useMemo(() => (
    <>
      <div className="status-chip">{activeId ? "Current chat" : "New chat"}</div>
      <div className="status-chip">{busy ? "Thinking…" : "Ready"}</div>
    </>
  ), [activeId, busy]);

  const refreshSessions = useCallback(async () => {
    const data = await listChatSessions();
    setSessions(data.sessions || []);
    if (!activeId && data.sessions?.length) {
      setActiveId(data.sessions[0].id);
    }
  }, [activeId]);

  async function createSession() {
    const created = await createChatSession();
    setActiveId(created.session_id);
    navigate(`/chat?c=${created.session_id}`);
    setMessages([]);
    await refreshSessions();
  }

  const loadSession = useCallback(async (id: string) => {
    const detail = await getChatSession(id);
    setActiveId(detail.session.id);
    setMessages(detail.session.messages.map((message) => ({
      role: message.role === "assistant" ? "assistant" : message.role,
      text: message.text,
    })));
    navigate(`/chat?c=${detail.session.id}`);
  }, [navigate]);

  async function sendMessage(text: string) {
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    const nextMessages = [...messages, { role: "user", text }];
    setMessages(nextMessages);
    setInput("");
    try {
      const response = await sendChatMessage(text, "text", "chat", activeId);
      setMessages([...nextMessages, { role: "assistant", text: response.reply }]);
      setActiveId(response.session_id);
      navigate(`/chat?c=${response.session_id}`);
      await refreshSessions();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function unlockDangerousActions() {
    const passphrase = window.prompt("Unlock passphrase for write actions:");
    if (!passphrase) return;
    const payload = await apiRequest<{ token: string; expires_in_sec: number }>("/unlock", {
      method: "POST",
      body: { passphrase },
    });
    setUnlockToken(payload.token, payload.expires_in_sec);
  }

  async function handleMic() {
    setVoiceBusy(true);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => chunks.push(event.data);
      recorder.onstop = async () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        const data = await transcribeAudio(blob, "chat");
        if (data.text) setInput(data.text);
      };
      recorder.start();
      setTimeout(() => recorder.stop(), 2500);
    } finally {
      setVoiceBusy(false);
    }
  }

  useEffect(() => {
    refreshSessions()
      .then(async () => {
        if (conversationId) {
          await loadSession(conversationId);
        }
      })
      .catch(() => setError("Failed to load chat history."));
  }, [conversationId, loadSession, refreshSessions]);

  useEffect(() => {
    setDraftPrefs(preferences);
  }, [preferences]);

  return (
    <AppShell sidebar={sidebar} actions={topActions} onProfileClick={() => setPrefsOpen(true)} onHelpClick={() => setHelpOpen(true)}>
      <div className={`chat-surface${preferences.compact_mode ? " compact-chat" : ""}`}>
        <section className="chat-thread">
          {!user ? (
            <div className="guest-inline-note">
              Guest mode is active. <button className="link-button" onClick={() => navigate("/login")}>Sign in</button> to save preferences, unlock Orb and keep your workspace.
            </div>
          ) : null}
          <div className="chat-workspace">
            <div className="chat-thread-header">
              <div className="chat-thread-meta">
                <div className="eyebrow">Conversation</div>
                <div className="chat-thread-title">{messages.length ? "Jarvis conversation" : "New chat"}</div>
              </div>
              <div className="inline-actions">
                <button className="ui-button ghost" onClick={() => clearUnlockToken()}>Lock write actions</button>
                <button className="ui-button ghost" onClick={() => unlockDangerousActions()}>Unlock actions</button>
              </div>
            </div>
            <div className="message-stack">
              {messages.length === 0 ? (
                <ChatEmptyState onPromptSelect={setInput} />
              ) : messages.map((message, index) => (
                <div key={`${message.role}-${index}`} className={`message-row ${message.role === "user" ? "user" : "assistant"}`}>
                  <div className="message-bubble">
                    <div className="message-label">{message.role === "user" ? "You" : "Jarvis"}</div>
                    <div>{message.text}</div>
                  </div>
                </div>
              ))}
              {busy ? (
                <div className="message-row assistant">
                  <div className="message-bubble thinking-bubble">
                    <div className="message-label">Jarvis</div>
                    <div className="thinking-dots"><span /><span /><span /></div>
                  </div>
                </div>
              ) : null}
            </div>
            <ChatComposer
              input={input}
              busy={busy}
              voiceBusy={voiceBusy}
              userLoggedIn={Boolean(user)}
              onInputChange={setInput}
              onSend={() => { void sendMessage(input); }}
              onMic={() => { void handleMic(); }}
              onClear={() => setInput("")}
              onPromptSelect={setInput}
            />
          </div>
          {error ? <div className="error-text">{error}</div> : null}
        </section>
      </div>

      {prefsOpen ? (
        <OverlayDialog
          eyebrow="User settings"
          title="Workspace preferences"
          onClose={() => setPrefsOpen(false)}
          actions={
            <>
              <button className="ui-button ghost" onClick={() => setPrefsOpen(false)}>Close</button>
              <button className="ui-button primary" disabled={!canSavePrefs} onClick={async () => { await savePreferences(draftPrefs); setPrefsOpen(false); }}>Save</button>
            </>
          }
        >
            {!canSavePrefs ? <p className="tiny-note">Guest users cannot save settings.</p> : null}
            <input className="ui-input" disabled={!canSavePrefs} value={draftPrefs.display_name || ""} onChange={(e) => setDraftPrefs({ ...draftPrefs, display_name: e.target.value })} placeholder="Display name" />
            <select className="ui-input" disabled={!canSavePrefs} value={draftPrefs.accent_color || "cyan"} onChange={(e) => setDraftPrefs({ ...draftPrefs, accent_color: e.target.value })}>
              <option value="cyan">cyan</option>
              <option value="amber">amber</option>
              <option value="blue">blue</option>
            </select>
            <select className="ui-input" disabled={!canSavePrefs} value={draftPrefs.theme || "dark"} onChange={(e) => setDraftPrefs({ ...draftPrefs, theme: e.target.value as "dark" | "light" })}>
              <option value="dark">dark theme</option>
              <option value="light">light theme</option>
            </select>
            <select className="ui-input" disabled={!canSavePrefs} value={draftPrefs.orb_detail || "medium"} onChange={(e) => setDraftPrefs({ ...draftPrefs, orb_detail: e.target.value })}>
              <option value="minimal">minimal orb detail</option>
              <option value="medium">medium orb detail</option>
              <option value="high">high orb detail</option>
            </select>
            <label className="settings-toggle">
              <input type="checkbox" checked={Boolean(draftPrefs.auto_play_voice)} onChange={(e) => setDraftPrefs({ ...draftPrefs, auto_play_voice: e.target.checked })} disabled={!canSavePrefs} />
              <span>Auto-play Orb voice replies</span>
            </label>
            <label className="settings-toggle">
              <input type="checkbox" checked={Boolean(draftPrefs.compact_mode)} onChange={(e) => setDraftPrefs({ ...draftPrefs, compact_mode: e.target.checked })} disabled={!canSavePrefs} />
              <span>Compact chat spacing</span>
            </label>
        </OverlayDialog>
      ) : null}

      {helpOpen ? (
        <OverlayDialog
          eyebrow="Help"
          title="Jarvis workspace help"
          onClose={() => setHelpOpen(false)}
          actions={<button className="ui-button primary" onClick={() => setHelpOpen(false)}>Close</button>}
        >
            <div className="page-stack">
              <p className="tiny-note">Use `New chat` to start a new conversation, click any history item to reopen it, and use the profile menu in the sidebar for settings and account actions.</p>
              <p className="tiny-note">Orb is voice-first mode. Dashboard is available only for admin users.</p>
            </div>
        </OverlayDialog>
      ) : null}
    </AppShell>
  );
}
