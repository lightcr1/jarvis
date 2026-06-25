/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import {
  UserCapabilities,
  UserPreferences,
  UserProfile,
  clearAdminToken,
  clearStoredIdentity,
  fetchMe,
  getSessionToken,
  getStoredPreferences,
  getStoredUser,
  issueAdminSession,
  login as loginRequest,
  logout as logoutRequest,
  savePreferences as savePreferencesRequest,
  setAdminToken,
  setStoredIdentity,
  setStoredPreferences,
} from "../../shared/api/client";

type AuthContextValue = {
  user: UserProfile | null;
  preferences: UserPreferences;
  loading: boolean;
  isAdmin: boolean;
  hasHomeAssistantAccess: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refresh: () => Promise<void>;
  savePreferences: (preferences: UserPreferences) => Promise<void>;
  ensureAdminAccess: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function mergeThemePreference(nextPreferences: UserPreferences, fallbackPreferences?: UserPreferences): UserPreferences {
  const fallbackTheme = fallbackPreferences?.theme === "light" ? "light" : fallbackPreferences?.theme === "dark" ? "dark" : undefined;
  const nextTheme = nextPreferences.theme === "light" ? "light" : nextPreferences.theme === "dark" ? "dark" : undefined;
  return {
    ...nextPreferences,
    // Local (fallback) theme always wins over server default — the user's explicit
    // toggle should never be overwritten by a server refresh.
    theme: fallbackTheme || nextTheme || "light",
  };
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(getStoredUser());
  const [preferences, setPreferences] = useState<UserPreferences>(() => mergeThemePreference(getStoredPreferences()));
  const [capabilities, setCapabilities] = useState<UserCapabilities>({});
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!getStoredUser()) {
      setLoading(false);
      return;
    }
    try {
      const me = await fetchMe();
      const mergedPreferences = mergeThemePreference(me.preferences || { theme: "light" }, getStoredPreferences());
      setUser(me.user);
      setPreferences(mergedPreferences);
      setCapabilities(me.capabilities || {});
      setStoredIdentity(localStorage.getItem("jarvis_user_session") || "", me.user, mergedPreferences);
    } catch {
      // client.ts clears the session token on 401. If it's gone, the session
      // really expired — clear React state too. For network/5xx errors the
      // token is still present, so we keep the user logged in and fail silently.
      if (!getSessionToken()) {
        setUser(null);
        setPreferences(getStoredPreferences());
        setCapabilities({});
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh().catch(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    document.documentElement.dataset.theme = preferences.theme === "dark" ? "dark" : "light";
  }, [preferences.theme]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    preferences,
    loading,
    isAdmin: user?.role === "admin",
    hasHomeAssistantAccess: Boolean(capabilities.home_assistant_access),
    login: async (username, password) => {
      const payload = await loginRequest(username, password);
      const mergedPreferences = mergeThemePreference(payload.preferences || {}, getStoredPreferences());
      setStoredIdentity(payload.session_token, payload.user, mergedPreferences);
      setUser(payload.user);
      setPreferences(mergedPreferences);
      setCapabilities(payload.capabilities || {});
    },
    logout: async () => {
      const lastPreferences = preferences;
      await logoutRequest();
      clearAdminToken();
      setUser(null);
      setPreferences(lastPreferences);
      setCapabilities({});
      setStoredPreferences(lastPreferences);
    },
    refresh,
    savePreferences: async (nextPreferences) => {
      if (!user) {
        const mergedPreferences = mergeThemePreference(nextPreferences, preferences);
        setPreferences(mergedPreferences);
        setStoredPreferences(mergedPreferences);
        return;
      }
      const result = await savePreferencesRequest(nextPreferences);
      const mergedPreferences = mergeThemePreference(result.preferences || nextPreferences, nextPreferences);
      setPreferences(mergedPreferences);
      if (user) {
        setStoredIdentity(localStorage.getItem("jarvis_user_session") || "", user, mergedPreferences);
      }
    },
    ensureAdminAccess: async () => {
      // Read from localStorage (set synchronously during login) rather than the
      // React closure, which may still hold the pre-login null value on the first click.
      const role = getStoredUser()?.role;
      if (role !== "admin") throw new Error("Admin role required");
      const payload = await issueAdminSession();
      setAdminToken(payload.token, payload.expires_in_sec);
    },
  }), [capabilities.home_assistant_access, loading, preferences, refresh, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
