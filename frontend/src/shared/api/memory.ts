import { apiRequest } from "./client";

export type DataClass = "public" | "personal" | "sensitive";

export type MemoryNote = {
  id: string;
  text: string;
  created_at: number;
  data_class: DataClass;
};

export type MemoryAlias = {
  alias: string;
  target: string;
  created_at: number;
};

export type MemorySummary = {
  notes: MemoryNote[];
  aliases: MemoryAlias[];
  note_count: number;
  alias_count: number;
};

export async function listNotes(): Promise<MemoryNote[]> {
  return apiRequest<MemoryNote[]>("/memory/notes", { includeUser: true });
}

export async function createNote(text: string, dataClass: DataClass = "personal"): Promise<MemoryNote> {
  return apiRequest<MemoryNote>("/memory/notes", {
    method: "POST",
    includeUser: true,
    body: { text, data_class: dataClass },
  });
}

export async function setNoteClass(id: string, dataClass: DataClass): Promise<MemoryNote> {
  return apiRequest<MemoryNote>(`/memory/notes/${id}`, {
    method: "PATCH",
    includeUser: true,
    body: { data_class: dataClass },
  });
}

export async function deleteNote(id: string): Promise<void> {
  await apiRequest<void>(`/memory/notes/${id}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export async function listAliases(): Promise<MemoryAlias[]> {
  return apiRequest<MemoryAlias[]>("/memory/aliases", { includeUser: true });
}

export async function createAlias(alias: string, target: string): Promise<MemoryAlias> {
  return apiRequest<MemoryAlias>("/memory/aliases", {
    method: "POST",
    includeUser: true,
    body: { alias, target },
  });
}

export async function deleteAlias(alias: string): Promise<void> {
  await apiRequest<void>(`/memory/aliases/${encodeURIComponent(alias)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export async function getMemorySummary(): Promise<MemorySummary> {
  return apiRequest<MemorySummary>("/memory/summary", { includeUser: true });
}

export async function clearAllMemory(): Promise<void> {
  await apiRequest<void>("/memory/all?confirm=true", {
    method: "DELETE",
    includeUser: true,
  });
}
