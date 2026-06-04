import { apiRequest } from "./client";

export type MemoryNote = {
  id: string;
  text: string;
  created_at: number;
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

export async function createNote(text: string): Promise<MemoryNote> {
  return apiRequest<MemoryNote>("/memory/notes", {
    method: "POST",
    includeUser: true,
    body: { text },
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
