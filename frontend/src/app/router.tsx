import React from "react";
import { createBrowserRouter, Navigate } from "react-router-dom";
import { ChatPage } from "../routes/chat/ChatPage";
import { OrbPage } from "../routes/orb/OrbPage";
import { LoginPage } from "../routes/auth/LoginPage";
import { AdminLoginPage } from "../routes/auth/AdminLoginPage";
import { AdminShell } from "../shared/layout/AdminShell";
import { DashboardPage } from "../routes/admin/pages/DashboardPage";
import { UsersPage } from "../routes/admin/pages/UsersPage";
import { GroupsPage } from "../routes/admin/pages/GroupsPage";
import { LogsPage } from "../routes/admin/pages/LogsPage";
import { SettingsPage } from "../routes/admin/pages/SettingsPage";
import { PermissionsPage } from "../routes/admin/pages/PermissionsPage";
import { StatusPage } from "../routes/admin/pages/StatusPage";

export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/chat" replace /> },
  { path: "/chat", element: <ChatPage /> },
  { path: "/orb", element: <OrbPage /> },
  { path: "/login", element: <LoginPage /> },
  { path: "/dashboard/login", element: <AdminLoginPage /> },
  {
    path: "/dashboard",
    element: <AdminShell />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "users", element: <UsersPage /> },
      { path: "groups", element: <GroupsPage /> },
      { path: "permissions", element: <PermissionsPage /> },
      { path: "status", element: <StatusPage /> },
      { path: "logs", element: <LogsPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },
]);
