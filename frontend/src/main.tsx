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
import { PoliciesPage } from "./routes/admin/pages/PoliciesPage";
import { StatusPage } from "./routes/admin/pages/StatusPage";
import { ProviderSettingsPage } from "./routes/admin/pages/ProviderSettingsPage";
import { BillingPage } from "./routes/admin/pages/BillingPage";
import { UsagePage } from "./routes/admin/pages/UsagePage";
import { AdminDocsPage } from "./routes/admin/pages/AdminDocsPage";
import { IntegrationsPage } from "./routes/admin/pages/IntegrationsPage";
import { WorkspaceShell } from "./shared/layout/WorkspaceShell";
import { OverviewScreen } from "./screens/OverviewScreen";
import { FilesScreen } from "./screens/FilesScreen";
import { CommunicationScreen } from "./screens/CommunicationScreen";
import { DesktopScreen } from "./screens/DesktopScreen";
import { SharedFilePage } from "./routes/public/SharedFilePage";
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
      { path: "policies",         element: <PoliciesPage /> },
      { path: "status",           element: <StatusPage /> },
      { path: "logs",             element: <LogsPage /> },
      { path: "settings",         element: <SettingsPage /> },
      { path: "provider",         element: <ProviderSettingsPage /> },
      { path: "billing",          element: <BillingPage /> },
      { path: "usage",            element: <UsagePage /> },
      { path: "docs",             element: <AdminDocsPage /> },
      { path: "integrations",     element: <IntegrationsPage /> },
    ],
  },
  {
    path: "/workspace",
    element: <WorkspaceShell />,
    children: [
      { index: true,          element: <OverviewScreen /> },
      { path: "overview",     element: <OverviewScreen /> },
      { path: "files",        element: <FilesScreen /> },
      { path: "communication", element: <CommunicationScreen /> },
      { path: "desktop",      element: <DesktopScreen /> },
    ],
  },
  { path: "/s/:token", element: <SharedFilePage /> },
  { path: "*", element: <JarvisApp /> },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <AuthProvider>
      <RouterProvider router={router} />
    </AuthProvider>
  </React.StrictMode>,
);

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  });
}
