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

export async function listChatSessions() {
  return apiRequest<{ sessions: ChatSessionListItem[] }>("/chat/sessions", { includeUser: true });
}

export async function getChatSession(sessionId: string) {
  const session = await apiRequest<{ id: string; messages: ChatSessionMessage[] }>(`/chat/sessions/${encodeURIComponent(sessionId)}`, { includeUser: true });
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

export async function sendChatMessage(text: string, source = "web", mode: "chat" | "orb" = "chat", sessionId?: string | null) {
  return apiRequest<{ reply: string; session_id: string; data?: Record<string, unknown> }>("/chat", {
    method: "POST",
    includeUser: true,
    mode,
    body: { text, source, session_id: sessionId || undefined },
  });
}

export async function transcribeAudio(blob: Blob, mode: "chat" | "orb" = "chat") {
  const formData = new FormData();
  formData.append("file", blob, "audio.webm");
  const response = await fetch("/stt", {
    method: "POST",
    body: formData,
    headers: buildApiHeaders({ includeUser: true, mode }),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.detail || text || `HTTP ${response.status}`);
  return data as { text?: string };
}

export async function synthesizeSpeech(text: string) {
  const response = await fetch("/tts", {
    method: "POST",
    headers: buildApiHeaders({ body: { text } }),
    body: JSON.stringify({ text }),
  });
  if (!response.ok) {
    const payload = await response.text();
    throw new Error(payload || `HTTP ${response.status}`);
  }
  return response.blob();
}
