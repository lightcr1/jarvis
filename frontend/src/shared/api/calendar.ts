import { apiRequest } from "./client";

export type CalendarEvent = {
  id: string;
  user_id: string;
  uid: string;
  title: string;
  description: string;
  location: string;
  start: number;
  end: number;
  source: "caldav" | "local";
  created_at: number;
  updated_at: number;
};

export type CalendarPolicy = {
  role: string;
  effective_permissions: string[];
};

export type CalendarCredentialsStatus = {
  configured: boolean;
  field_names: string[];
  updated_at: number | null;
};

export function fetchCalendarEvents(start?: number, end?: number) {
  const params = new URLSearchParams();
  if (start !== undefined) params.set("start", String(start));
  if (end !== undefined) params.set("end", String(end));
  const query = params.toString() ? `?${params.toString()}` : "";
  return apiRequest<{ policy: CalendarPolicy; events: CalendarEvent[] }>(`/calendar/events${query}`, { includeUser: true });
}

export function createCalendarEvent(body: { title: string; start: number; end: number; description?: string; location?: string; force?: boolean }) {
  return apiRequest<{ policy: CalendarPolicy; event?: CalendarEvent; conflicts: CalendarEvent[]; created: boolean }>("/calendar/events", {
    method: "POST", includeUser: true, body,
  });
}

export function deleteCalendarEvent(eventId: string) {
  return apiRequest<{ policy: CalendarPolicy; deleted: boolean }>(`/calendar/events/${encodeURIComponent(eventId)}`, {
    method: "DELETE", includeUser: true,
  });
}

export function fetchCalendarCredentialsStatus() {
  return apiRequest<{ policy: CalendarPolicy; status: CalendarCredentialsStatus }>("/calendar/credentials/status", { includeUser: true });
}

export function setCalendarCredentials(body: { url: string; username: string; password: string }) {
  return apiRequest<{ policy: CalendarPolicy; credentials: { integration: string; field_names: string[]; updated_at: number } }>("/calendar/credentials", {
    method: "PUT", includeUser: true, body,
  });
}

export function deleteCalendarCredentials() {
  return apiRequest<{ policy: CalendarPolicy; deleted: boolean }>("/calendar/credentials", { method: "DELETE", includeUser: true });
}

export function syncCalendar() {
  return apiRequest<{ policy: CalendarPolicy; synced_count: number }>("/calendar/sync", { method: "POST", includeUser: true });
}
