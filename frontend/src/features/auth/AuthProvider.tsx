/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  UserPreferences,
  UserProfile,
  clearAdminToken,
  clearStoredIdentity,
  fetchMe,
  getStoredPreferences,
  getStoredUser,
  issueAdminSession,
  login as loginRequest,
  logout as logoutRequest,
  savePreferences as savePreferencesRequest,
  setAdminToken,
  setStoredIdentity,
} from "../../shared/api/client";

type AuthContextValue = {
  user: UserProfile | null;
  preferences: UserPreferences;
  loading: boolean;
  isAdmin: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  savePreferences: (preferences: UserPreferences) => Promise<void>;
  ensureAdminAccess: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(getStoredUser());
  const [preferences, setPreferences] = useState<UserPreferences>(getStoredPreferences());
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    if (!getStoredUser()) {
      setLoading(false);
      return;
    }
    try {
      const me = await fetchMe();
      setUser(me.user);
      setPreferences(me.preferences || {});
      setStoredIdentity(localStorage.getItem("jarvis_user_session") || "", me.user, me.preferences || {});
    } catch {
      clearStoredIdentity();
      setUser(null);
      setPreferences({});
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = preferences.theme === "light" ? "light" : "dark";
  }, [preferences.theme]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    preferences,
    loading,
    isAdmin: user?.role === "admin",
    login: async (username, password) => {
      const payload = await loginRequest(username, password);
      setStoredIdentity(payload.session_token, payload.user, payload.preferences || {});
      setUser(payload.user);
      setPreferences(payload.preferences || {});
    },
    logout: async () => {
      await logoutRequest();
      clearAdminToken();
      setUser(null);
      setPreferences({});
    },
    refresh,
    savePreferences: async (nextPreferences) => {
      const result = await savePreferencesRequest(nextPreferences);
      setPreferences(result.preferences || {});
      if (user) {
        setStoredIdentity(localStorage.getItem("jarvis_user_session") || "", user, result.preferences || {});
      }
    },
    ensureAdminAccess: async () => {
      if (user?.role !== "admin") throw new Error("Admin role required");
      const payload = await issueAdminSession();
      setAdminToken(payload.token, payload.expires_in_sec);
    },
  }), [loading, preferences, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
