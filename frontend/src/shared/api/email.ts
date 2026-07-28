import { apiRequest } from "./client";

export type EmailMessage = {
  id: string;
  user_id: string;
  uid: string;
  folder: string;
  subject: string;
  sender: string;
  date: number;
  read: boolean;
  summary: string | null;
  synced_at: number;
};

export type EmailDraft = {
  id: string;
  user_id: string;
  to: string;
  subject: string;
  body: string;
  in_reply_to_message_id: string | null;
  status: "pending_approval" | "sent" | "discarded";
  created_at: number;
  updated_at: number;
  sent_at?: number;
};

export type EmailPolicy = {
  role: string;
  effective_permissions: string[];
};

export type EmailCredentialsStatus = {
  configured: boolean;
  field_names: string[];
  updated_at: number | null;
};

export function fetchEmailMessages(opts?: { folder?: string; unreadOnly?: boolean }) {
  const params = new URLSearchParams();
  if (opts?.folder) params.set("folder", opts.folder);
  if (opts?.unreadOnly) params.set("unread_only", "true");
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<{ policy: EmailPolicy; messages: EmailMessage[] }>(`/email/messages${query}`, { includeUser: true });
}

export function fetchEmailMessage(messageId: string) {
  return apiRequest<{ policy: EmailPolicy; message: EmailMessage }>(`/email/messages/${encodeURIComponent(messageId)}`, { includeUser: true });
}

export function fetchEmailBody(messageId: string) {
  return apiRequest<{ policy: EmailPolicy; message: EmailMessage; body: string }>(`/email/messages/${encodeURIComponent(messageId)}/body`, { includeUser: true });
}

export function markEmailRead(messageId: string) {
  return apiRequest<{ policy: EmailPolicy; message: EmailMessage }>(`/email/messages/${encodeURIComponent(messageId)}/read`, { method: "POST", includeUser: true });
}

export function summarizeEmail(messageId: string) {
  return apiRequest<{ policy: EmailPolicy; message: EmailMessage }>(`/email/messages/${encodeURIComponent(messageId)}/summarize`, { method: "POST", includeUser: true });
}

export function fetchEmailDrafts(status?: string) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<{ policy: EmailPolicy; drafts: EmailDraft[] }>(`/email/drafts${query}`, { includeUser: true });
}

export function createEmailDraft(body: { to: string; subject?: string; body: string; in_reply_to_message_id?: string }) {
  return apiRequest<{ policy: EmailPolicy; draft: EmailDraft }>("/email/drafts", { method: "POST", includeUser: true, body });
}

export function discardEmailDraft(draftId: string) {
  return apiRequest<{ policy: EmailPolicy; draft: EmailDraft }>(`/email/drafts/${encodeURIComponent(draftId)}`, { method: "DELETE", includeUser: true });
}

export function sendEmailDraft(draftId: string, confirm: boolean) {
  return apiRequest<{ policy: EmailPolicy; draft: EmailDraft; status: string }>(`/email/drafts/${encodeURIComponent(draftId)}/send`, {
    method: "POST", includeUser: true, body: { confirm },
  });
}

export function fetchEmailCredentialsStatus() {
  return apiRequest<{ policy: EmailPolicy; status: EmailCredentialsStatus }>("/email/credentials/status", { includeUser: true });
}

export function setEmailCredentials(body: {
  imap_host: string; imap_port: number | string; imap_username: string; imap_password: string;
  smtp_host: string; smtp_port: number | string; smtp_username: string; smtp_password: string;
}) {
  return apiRequest<{ policy: EmailPolicy; credentials: { integration: string; field_names: string[]; updated_at: number } }>("/email/credentials", {
    method: "PUT", includeUser: true, body,
  });
}

export function deleteEmailCredentials() {
  return apiRequest<{ policy: EmailPolicy; deleted: boolean }>("/email/credentials", { method: "DELETE", includeUser: true });
}

export function syncEmail() {
  return apiRequest<{ policy: EmailPolicy; synced_count: number }>("/email/sync", { method: "POST", includeUser: true });
}
