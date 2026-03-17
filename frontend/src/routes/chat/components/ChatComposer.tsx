import React from "react";

type ChatComposerProps = {
  input: string;
  busy: boolean;
  voiceBusy: boolean;
  userLoggedIn: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onMic: () => void;
  onClear: () => void;
  onPromptSelect: (prompt: string) => void;
};

export function ChatComposer({
  input,
  busy,
  voiceBusy,
  userLoggedIn,
  onInputChange,
  onSend,
  onMic,
  onClear,
  onPromptSelect,
}: ChatComposerProps) {
  return (
    <div className="composer-card">
      <div className="composer-toolbar">
        <div className="composer-shortcuts">
          <button className="toolbar-chip" onClick={() => onPromptSelect("status jarvis")}>Status</button>
          <button className="toolbar-chip" onClick={() => onPromptSelect("show active admin warnings")}>Warnings</button>
          <button className="toolbar-chip" onClick={() => onPromptSelect("summarize recent audit activity")}>Audit summary</button>
        </div>
        <button className="ui-button ghost" onClick={onMic} disabled={voiceBusy}>{voiceBusy ? "Listening…" : "Mic"}</button>
      </div>
      <div className="composer-input-shell">
        <div className="composer-input-label">Message</div>
        <textarea
          className="composer-input"
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              onSend();
            }
          }}
          placeholder="Message Jarvis…"
        />
      </div>
      <div className="composer-actions">
        <div className="tiny-note composer-note">
          {userLoggedIn ? "Preferences and personalization are saved to your account." : "Guest mode is temporary. Login to save preferences."}
        </div>
        <button className="ui-button ghost" onClick={onClear}>Clear</button>
        <button className="ui-button primary composer-send" onClick={onSend} disabled={busy}>Send</button>
      </div>
    </div>
  );
}
