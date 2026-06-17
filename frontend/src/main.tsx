import React from "react";
import ReactDOM from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";

// Apply stored theme synchronously before first render to avoid flash
try {
  const raw = localStorage.getItem("jarvis_user_prefs");
  const prefs = raw ? JSON.parse(raw) : {};
  if (prefs.theme === "light") {
    document.body.style.background = "#ebebeb";
    document.body.style.color = "#0c0c0c";
    document.documentElement.style.colorScheme = "light";
  }
} catch { /* ignore */ }
import { AuthProvider } from "./features/auth/AuthProvider";
import { JarvisApp } from "./screens/JarvisApp";
import { AdminLoginPage } from "./routes/auth/AdminLoginPage";
import { AdminShell } from "./shared/layout/AdminShell";
import { DashboardPage } from "./routes/admin/pages/DashboardPage";
import { UsersPage } from "./routes/admin/pages/UsersPage";
import { GroupsPage } from "./routes/admin/pages/GroupsPage";
import { LogsPage } from "./routes/admin/pages/LogsPage";
import { SettingsPage } from "./routes/admin/pages/SettingsPage";
import { PermissionsPage } from "./routes/admin/pages/PermissionsPage";
import { StatusPage } from "./routes/admin/pages/StatusPage";
import { ProviderSettingsPage } from "./routes/admin/pages/ProviderSettingsPage";
import { UsagePage } from "./routes/admin/pages/UsagePage";
import { AdminDocsPage } from "./routes/admin/pages/AdminDocsPage";
import "./styles.css";

const router = createBrowserRouter([
  { path: "/dashboard/login", element: <AdminLoginPage /> },
  {
    path: "/dashboard",
    element: <AdminShell />,
    children: [
      { index: true,              element: <DashboardPage /> },
      { path: "users",            element: <UsersPage /> },
      { path: "groups",           element: <GroupsPage /> },
      { path: "permissions",      element: <PermissionsPage /> },
      { path: "status",           element: <StatusPage /> },
      { path: "logs",             element: <LogsPage /> },
      { path: "settings",         element: <SettingsPage /> },
      { path: "provider",         element: <ProviderSettingsPage /> },
      { path: "usage",            element: <UsagePage /> },
      { path: "docs",             element: <AdminDocsPage /> },
    ],
  },
  { path: "*", element: <JarvisApp /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </React.StrictMode>,
);
