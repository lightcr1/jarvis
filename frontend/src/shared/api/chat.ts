import { apiRequest, buildApiHeaders } from "./client";

export type ChatSessionListItem = {
  id: string;
  title: string;
  updated_at: number;
  created_at: number;
  message_count: number;
};

export type ChatSessionMessage = {
  role: string;
  text: string;
  ts: number;
};

export type HomeAssistantPendingAction = {
  action: string;
  params?: Record<string, unknown>;
  missing_fields?: string[];
};

export type ChatSessionDetail = {
  id: string;
  messages: ChatSessionMessage[];
  pending_home_assistant_action?: HomeAssistantPendingAction | null;
};

export async function listChatSessions() {
  return apiRequest<{ sessions: ChatSessionListItem[] }>("/chat/sessions", { includeUser: true });
}

export async function getChatSession(sessionId: string) {
  const session = await apiRequest<ChatSessionDetail>(`/chat/sessions/${encodeURIComponent(sessionId)}`, { includeUser: true });
  return { session };
}

export async function createChatSession() {
  const session = await apiRequest<{ id: string }>("/chat/sessions", {
    method: "POST",
    includeUser: true,
    body: {},
  });
  return { session_id: session.id };
}

export async function deleteChatSession(sessionId: string) {
  return apiRequest<{ ok: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export async function renameChatSession(sessionId: string, title: string) {
  const session = await apiRequest<ChatSessionDetail & { title: string; updated_at: number; created_at: number }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PATCH",
    includeUser: true,
    body: { title },
  });
  return { session };
}

export async function clearPendingHomeAssistantAction(sessionId: string) {
  return apiRequest<{ ok: boolean }>(`/chat/sessions/${encodeURIComponent(sessionId)}/pending-home-assistant/clear`, {
    method: "POST",
    includeUser: true,
  });
}

export async function sendChatMessage(text: string, source = "web", mode: "chat" | "orb" = "chat", sessionId?: string | null) {
  return apiRequest<{ reply: string; session_id: string; data?: Record<string, unknown> }>("/chat", {
    method: "POST",
    includeUser: true,
    mode,
    body: { text, source, session_id: sessionId || undefined },
  });
}

export type StreamEvent =
  | { type: 'token'; token: string }
  | { type: 'done'; reply: string; session_id: string; data?: Record<string, unknown>; prefs_update?: Record<string, unknown> }
  | { type: 'error'; detail: string };

export async function* streamChatMessage(
  text: string,
  source = "web",
  mode: "chat" | "orb" = "chat",
  sessionId?: string | null,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const headers = buildApiHeaders({ includeUser: true, mode, body: { text } });
  const response = await fetch("/chat/stream", {
    method: "POST",
    headers,
    body: JSON.stringify({ text, source, session_id: sessionId || undefined }),
    signal,
  });
  if (!response.ok || !response.body) {
    const err = await response.text().catch(() => `HTTP ${response.status}`);
    throw new Error(err || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split("\n\n");
    buf = parts.pop()!;
    for (const part of parts) {
      const line = part.trim();
      if (line.startsWith("data: ")) {
        try {
          yield JSON.parse(line.slice(6)) as StreamEvent;
        } catch {
          // malformed SSE chunk — skip
        }
      }
    }
  }
}

export class SttError extends Error {
  kind: 'network' | 'rate_limit' | 'unknown';
  constructor(message: string, kind: 'network' | 'rate_limit' | 'unknown' = 'unknown') {
    super(message);
    this.name = 'SttError';
    this.kind = kind;
  }
}

export async function transcribeAudio(blob: Blob, mode: "chat" | "orb" = "chat") {
  const formData = new FormData();
  formData.append("file", blob, "audio.webm");
  let response: Response;
  try {
    response = await fetch("/stt", {
      method: "POST",
      body: formData,
      headers: buildApiHeaders({ includeUser: true, mode }),
    });
  } catch {
    throw new SttError("Network error", "network");
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (response.status === 429) throw new SttError(data.detail || "Rate limited", "rate_limit");
  if (!response.ok) throw new SttError(data.detail || text || `HTTP ${response.status}`, "unknown");
  return data as { text?: string };
}

export async function getDailyBriefing() {
  return apiRequest<{ text: string; date: string }>("/chat/daily-briefing", { includeUser: true });
}

export async function synthesizeSpeech(text: string, voice?: string) {
  const body: Record<string, unknown> = { text };
  if (voice) body.voice = voice;
  const response = await fetch("/tts", {
    method: "POST",
    headers: buildApiHeaders({ body }),
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `HTTP ${response.status}`);
  }
  return response.blob();
}

export type SystemMetrics = {
  cpu: { pct: number };
  ram: { pct: number; used_gb: number; total_gb: number };
  disk: { pct: number; used_gb: number; total_gb: number };
  uptime: string;
};

export async function getSystemMetrics() {
  return apiRequest<SystemMetrics>("/sys/metrics", { includeUser: true });
}

export type RagStatus = {
  counts: Record<string, number>;
  updated_at: number;
};

export async function getRagStatus() {
  return apiRequest<RagStatus>("/rag/status", { includeUser: true });
}
