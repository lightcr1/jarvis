import { apiRequest, buildApiHeaders } from "./client";

export type FileFolder = {
  id: string;
  parent_id: string | null;
  name: string;
  owner_user_id: string;
  jarvis_access_granted: boolean;
  created_at: number;
  updated_at: number;
};

export type FileEntry = {
  id: string;
  folder_id: string | null;
  filename: string;
  size_bytes: number;
  mime_type: string;
  owner_user_id: string;
  created_at: number;
  updated_at: number;
};

export type FilesPolicy = {
  role: string;
  effective_permissions: string[];
};

export type BreadcrumbItem = { id: string; name: string };

export type FolderAccess = "owner" | "read" | "write";

export type BrowseResponse = {
  policy: FilesPolicy;
  parent_id: string | null;
  breadcrumb: BreadcrumbItem[];
  folders: FileFolder[];
  files: FileEntry[];
  owner_user_id: string;
  owner_username: string | null;
  access: FolderAccess;
};

export type QuotaResponse = {
  policy: FilesPolicy;
  used_bytes: number;
  quota_bytes: number;
};

export type MyGroup = { id: string; name: string };

export type ShareGrant = {
  id: string;
  folder_id: string;
  group_id: string;
  group_name: string;
  permission: "read" | "write";
  created_by: string;
  created_at: number;
};

export type SharedWithMeEntry = {
  folder: FileFolder;
  owner_username: string | null;
  access: "read" | "write";
};

export function browseFiles(parentId?: string | null) {
  const query = parentId ? `?parent_id=${encodeURIComponent(parentId)}` : "";
  return apiRequest<BrowseResponse>(`/files/browse${query}`, { includeUser: true });
}

export function fetchQuotaStatus() {
  return apiRequest<QuotaResponse>("/files/quota", { includeUser: true });
}

export function createFolder(name: string, parentId?: string | null) {
  return apiRequest<{ policy: FilesPolicy; folder: FileFolder }>("/files/folders", {
    method: "POST",
    includeUser: true,
    body: { name, parent_id: parentId ?? null },
  });
}

export function renameFolder(folderId: string, name: string) {
  return apiRequest<{ policy: FilesPolicy; folder: FileFolder }>(`/files/folders/${encodeURIComponent(folderId)}`, {
    method: "PATCH",
    includeUser: true,
    body: { name },
  });
}

export function moveFolder(folderId: string, parentId: string | null) {
  return apiRequest<{ policy: FilesPolicy; folder: FileFolder }>(`/files/folders/${encodeURIComponent(folderId)}`, {
    method: "PATCH",
    includeUser: true,
    body: { parent_id: parentId },
  });
}

export function deleteFolder(folderId: string) {
  return apiRequest<{ policy: FilesPolicy; deleted: boolean; freed_bytes: number }>(`/files/folders/${encodeURIComponent(folderId)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export function setJarvisFolderAccess(folderId: string, granted: boolean) {
  return apiRequest<{ policy: FilesPolicy; folder: FileFolder }>(`/files/folders/${encodeURIComponent(folderId)}/jarvis-access`, {
    method: "PUT",
    includeUser: true,
    body: { granted },
  });
}

export function renameFile(fileId: string, filename: string) {
  return apiRequest<{ policy: FilesPolicy; file: FileEntry }>(`/files/${encodeURIComponent(fileId)}`, {
    method: "PATCH",
    includeUser: true,
    body: { filename },
  });
}

export function moveFile(fileId: string, folderId: string | null) {
  return apiRequest<{ policy: FilesPolicy; file: FileEntry }>(`/files/${encodeURIComponent(fileId)}`, {
    method: "PATCH",
    includeUser: true,
    body: { folder_id: folderId },
  });
}

export function deleteFile(fileId: string) {
  return apiRequest<{ policy: FilesPolicy; deleted: boolean }>(`/files/${encodeURIComponent(fileId)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export async function uploadFile(file: File, folderId?: string | null): Promise<{ policy: FilesPolicy; file: FileEntry }> {
  const formData = new FormData();
  formData.append("file", file, file.name);
  if (folderId) formData.append("folder_id", folderId);
  const response = await fetch("/files/upload", {
    method: "POST",
    body: formData,
    headers: buildApiHeaders({ includeUser: true }),
  });
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (!response.ok) throw new Error(data.detail || text || `HTTP ${response.status}`);
  return data;
}

export async function downloadFile(fileId: string, filename: string): Promise<void> {
  const response = await fetch(`/files/${encodeURIComponent(fileId)}/download`, {
    headers: buildApiHeaders({ includeUser: true }),
  });
  if (!response.ok) {
    const text = await response.text();
    let detail = text;
    try {
      detail = JSON.parse(text).detail || text;
    } catch {
      // response body wasn't JSON — fall back to raw text
    }
    throw new Error(detail || `HTTP ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function fetchMyGroups() {
  return apiRequest<{ policy: FilesPolicy; groups: MyGroup[] }>("/files/my-groups", { includeUser: true });
}

export function fetchSharedWithMe() {
  return apiRequest<{ policy: FilesPolicy; shared: SharedWithMeEntry[] }>("/files/shared-with-me", { includeUser: true });
}

export function shareFolder(folderId: string, groupId: string, permission: "read" | "write") {
  return apiRequest<{ policy: FilesPolicy; share: ShareGrant }>(`/files/folders/${encodeURIComponent(folderId)}/shares`, {
    method: "POST",
    includeUser: true,
    body: { group_id: groupId, permission },
  });
}

export function listFolderShares(folderId: string) {
  return apiRequest<{ policy: FilesPolicy; shares: ShareGrant[] }>(`/files/folders/${encodeURIComponent(folderId)}/shares`, {
    includeUser: true,
  });
}

export function unshareFolder(shareId: string) {
  return apiRequest<{ policy: FilesPolicy; deleted: boolean }>(`/files/shares/${encodeURIComponent(shareId)}`, {
    method: "DELETE",
    includeUser: true,
  });
}

export function formatBytes(bytes: number): string {
  if (bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);
  return `${value >= 10 || exponent === 0 ? Math.round(value) : value.toFixed(1)} ${units[exponent]}`;
}
