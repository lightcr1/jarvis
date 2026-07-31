import { apiRequest } from "./client";

export type EmailMessage = {
  id: string;
  user_id: string;
  account_id: string;
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
  account_id: string;
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

export type EmailAccount = {
  account_id: string;
  label: string;
  field_names: string[];
  updated_at: number | null;
  is_primary: boolean;
};

export type EmailAccountFields = {
  imap_host: string; imap_port: number | string; imap_username: string; imap_password: string;
  smtp_host: string; smtp_port: number | string; smtp_username: string; smtp_password: string;
};

export function fetchEmailAccounts() {
  return apiRequest<{ policy: EmailPolicy; accounts: EmailAccount[] }>("/email/accounts", { includeUser: true });
}

export function addEmailAccount(label: string, fields: EmailAccountFields) {
  return apiRequest<{ policy: EmailPolicy; account: EmailAccount }>("/email/accounts", {
    method: "POST", includeUser: true, body: { ...fields, label },
  });
}

export function updateEmailAccount(accountId: string, label: string, fields: EmailAccountFields) {
  return apiRequest<{ policy: EmailPolicy; account: EmailAccount }>(`/email/accounts/${encodeURIComponent(accountId)}`, {
    method: "PUT", includeUser: true, body: { ...fields, label },
  });
}

export function deleteEmailAccount(accountId: string) {
  return apiRequest<{ policy: EmailPolicy; deleted: boolean }>(`/email/accounts/${encodeURIComponent(accountId)}`, {
    method: "DELETE", includeUser: true,
  });
}

export function setPrimaryEmailAccount(accountId: string) {
  return apiRequest<{ policy: EmailPolicy; primary_account_id: string }>(`/email/accounts/${encodeURIComponent(accountId)}/primary`, {
    method: "POST", includeUser: true,
  });
}

export function fetchEmailMessages(opts?: { folder?: string; unreadOnly?: boolean; accountId?: string }) {
  const params = new URLSearchParams();
  if (opts?.folder) params.set("folder", opts.folder);
  if (opts?.unreadOnly) params.set("unread_only", "true");
  if (opts?.accountId) params.set("account_id", opts.accountId);
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

export function fetchEmailDrafts(status?: string, accountId?: string) {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (accountId) params.set("account_id", accountId);
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<{ policy: EmailPolicy; drafts: EmailDraft[] }>(`/email/drafts${query}`, { includeUser: true });
}

export function createEmailDraft(body: { to: string; subject?: string; body: string; in_reply_to_message_id?: string; account_id?: string }) {
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

export function syncEmail(accountId?: string) {
  const query = accountId ? `?account_id=${encodeURIComponent(accountId)}` : "";
  return apiRequest<{ policy: EmailPolicy; synced_count: number; account_id: string }>(`/email/sync${query}`, { method: "POST", includeUser: true });
}
