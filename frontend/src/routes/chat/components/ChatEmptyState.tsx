import React from "react";

export function ChatEmptyState({ onPromptSelect }: { onPromptSelect: (prompt: string) => void }) {
  return (
    <div className="empty-state chat-empty-state">
      <div className="chat-empty-copy">
        <h3>How can Jarvis help?</h3>
        <p>Start with a prompt, use voice input, or pick one of the suggested actions below.</p>
      </div>
      <div className="suggestion-grid">
        <button className="suggestion-card" onClick={() => onPromptSelect("status jarvis")}>
          <span className="suggestion-title">Status check</span>
          <span className="suggestion-copy">Ask Jarvis for runtime, service and voice system status.</span>
        </button>
        <button className="suggestion-card" onClick={() => onPromptSelect("service restart local nginx")}>
          <span className="suggestion-title">Service action</span>
          <span className="suggestion-copy">Draft a controlled maintenance command with the right context.</span>
        </button>
        <button className="suggestion-card" onClick={() => onPromptSelect("summarize the current admin health state")}>
          <span className="suggestion-title">Summarize state</span>
          <span className="suggestion-copy">Generate a concise operational overview of the current system.</span>
        </button>
      </div>
    </div>
  );
}
