import { apiRequest } from "./client";

export type TaskStatus = "open" | "in_progress" | "done";
export type TaskPriority = "low" | "medium" | "high";

export type Task = {
  id: string;
  owner_user_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: TaskPriority;
  due_at: number | null;
  steps: string[];
  created_at: number;
  updated_at: number;
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
};

export function fetchTasks(status?: TaskStatus) {
  const query = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiRequest<TaskListResponse>(`/tasks${query}`, { includeUser: true });
}

export function createTask(body: { title: string; description?: string; priority?: TaskPriority; due_at?: number | null; steps?: string[] }) {
  return apiRequest<TaskResponse>("/tasks", { method: "POST", includeUser: true, body });
}

export function updateTask(
  taskId: string,
  body: Partial<{ title: string; description: string; status: TaskStatus; priority: TaskPriority; due_at: number | null; steps: string[] }>,
) {
  return apiRequest<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}`, { method: "PATCH", includeUser: true, body });
}

export function completeTask(taskId: string) {
  return apiRequest<TaskResponse>(`/tasks/${encodeURIComponent(taskId)}/complete`, { method: "POST", includeUser: true });
}

export function deleteTask(taskId: string) {
  return apiRequest<{ policy: TaskPolicy; deleted: boolean }>(`/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE", includeUser: true });
}
