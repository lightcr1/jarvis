import { apiRequest } from "./client";

export type TaskStatus = "open" | "in_progress" | "done";
export type TaskPriority = "low" | "medium" | "high";
export type TaskAccess = "owner" | "write" | "read";

export type Task = {
  id: string;
  owner_user_id: string;
  assignee_user_id: string | null;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_at: number | null;
  steps: string[];
  created_at: number;
  updated_at: number;
  access?: TaskAccess;
};

export type TaskPolicy = {
  role: string;
  effective_permissions: string[];
};

export type TaskListResponse = {
  policy: TaskPolicy;
  tasks: Task[];
};

export type TaskResponse = {
  policy: TaskPolicy;
  task: Task;
  access?: TaskAccess;
};

export function fetchTasks(status?: TaskStatus) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<TaskListResponse>(`/tasks${query}`, { includeUser: true });
}

export function createTask(body: {
  title: string; description?: string; priority?: TaskPriority; due_at?: number | null; steps?: string[]; assignee_user_id?: string | null;
}) {
  return apiRequest<TaskResponse>("/tasks", { method: "POST", includeUser: true, body });
}

export function updateTask(
  taskId: string,
  body: Partial<{
    title: string; description: string; status: TaskStatus; priority: TaskPriority; due_at: number | null; steps: string[]; assignee_user_id: string | null;
  }>,
) {
  return apiRequest<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}`, { method: "PATCH", includeUser: true, body });
}

export function completeTask(taskId: string) {
  return apiRequest<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/complete`, { method: "POST", includeUser: true });
}

export function deleteTask(taskId: string) {
  return apiRequest<{ policy: TaskPolicy; deleted: boolean }>(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE", includeUser: true });
}

export type TaskAssignableUser = { id: string; username: string };
export type TaskGroup = { id: string; name: string };
export type TaskShare = { id: string; task_id: string; group_id: string; permission: "read" | "write"; created_by: string; created_at: number; group_name: string };
export type TaskSharedEntry = { task: Task; owner_username?: string; access: "read" | "write" };

export function fetchAssignableUsers() {
  return apiRequest<{ policy: TaskPolicy; users: TaskAssignableUser[] }>("/tasks/assignable-users", { includeUser: true });
}

export function fetchMyTaskGroups() {
  return apiRequest<{ policy: TaskPolicy; groups: TaskGroup[] }>("/tasks/my-groups", { includeUser: true });
}

export function fetchTasksSharedWithMe() {
  return apiRequest<{ policy: TaskPolicy; shared: TaskSharedEntry[] }>("/tasks/shared-with-me", { includeUser: true });
}

export function shareTask(taskId: string, groupId: string, permission: "read" | "write") {
  return apiRequest<{ policy: TaskPolicy; share: TaskShare }>(`/tasks/${encodeURIComponent(taskId)}/shares`, {
    method: "POST", includeUser: true, body: { group_id: groupId, permission },
  });
}

export function fetchTaskShares(taskId: string) {
  return apiRequest<{ policy: TaskPolicy; shares: TaskShare[] }>(`/tasks/${encodeURIComponent(taskId)}/shares`, { includeUser: true });
}

export function unshareTask(shareId: string) {
  return apiRequest<{ policy: TaskPolicy; deleted: boolean }>(`/tasks/shares/${encodeURIComponent(shareId)}`, { method: "DELETE", includeUser: true });
}
