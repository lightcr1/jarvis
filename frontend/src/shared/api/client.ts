export type UserProfile = {
  id: string;
  username: string;
  role: string;
  email?: string;
};

export type UserCapabilities = {
  home_assistant_access?: boolean;
};

export type UserPreferences = {
  display_name?: string;
  accent_color?: string;
  auto_play_voice?: boolean;
  compact_mode?: boolean;
  orb_detail?: string;
  theme?: "dark" | "light";
  location?: string;
  notes?: string[];
  tts_voice?: string;
};

export type RequestOptions = {
  method?: string;
  body?: unknown;
  includeUnlock?: boolean;
  includeUser?: boolean;
  includeAdmin?: boolean;
  mode?: "orb" | "chat";
};

const DEFAULT_THEME: NonNullable<UserPreferences["theme"]> = "dark";

const STORAGE_KEYS = {
  unlockToken: "jarvis_unlock_token",
  unlockExp: "jarvis_unlock_exp",
  sessionToken: "jarvis_user_session",
  user: "jarvis_user_profile",
  prefs: "jarvis_user_prefs",
  guestKey: "jarvis_guest_key",
  guestMode: "jarvis_guest_mode",
  adminToken: "jarvis_admin_token",
  adminExp: "jarvis_admin_exp",
};

let _pendingChatPrefill: string | null = null;
export function setPendingChatPrefill(text: string) { _pendingChatPrefill = text; }
export function consumePendingChatPrefill(): string | null { const t = _pendingChatPrefill; _pendingChatPrefill = null; return t; }

export function setGuestMode(): void {
  localStorage.setItem(STORAGE_KEYS.guestMode, "1");
}

export function clearGuestMode(): void {
  localStorage.removeItem(STORAGE_KEYS.guestMode);
}

export function isGuestMode(): boolean {
  return localStorage.getItem(STORAGE_KEYS.guestMode) === "1";
}

export function ensureGuestKey(): string {
  let key = localStorage.getItem(STORAGE_KEYS.guestKey);
  if (!key) {
    key = `guest-${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem(STORAGE_KEYS.guestKey, key);
  }
  return key;
}

export function getUnlockToken(): string | null {
  const token = sessionStorage.getItem(STORAGE_KEYS.unlockToken);
  const exp = Number(sessionStorage.getItem(STORAGE_KEYS.unlockExp) || "0");
  if (!token) return null;
  if (exp && Date.now() > exp) {
    clearUnlockToken();
    return null;
  }
  return token;
}

export function setUnlockToken(token: string, expiresInSec: number): void {
  sessionStorage.setItem(STORAGE_KEYS.unlockToken, token);
  sessionStorage.setItem(STORAGE_KEYS.unlockExp, String(Date.now() + expiresInSec * 1000));
}

export function clearUnlockToken(): void {
  sessionStorage.removeItem(STORAGE_KEYS.unlockToken);
  sessionStorage.removeItem(STORAGE_KEYS.unlockExp);
}

export function getSessionToken(): string {
  return localStorage.getItem(STORAGE_KEYS.sessionToken) || "";
}

export function getStoredUser(): UserProfile | null {
  const raw = localStorage.getItem(STORAGE_KEYS.user);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as UserProfile;
  } catch {
    return null;
  }
}

export function getStoredPreferences(): UserPreferences {
  const raw = localStorage.getItem(STORAGE_KEYS.prefs);
  if (!raw) return { theme: DEFAULT_THEME };
  try {
    const parsed = JSON.parse(raw) as UserPreferences;
    return { ...parsed, theme: parsed.theme === "light" ? "light" : DEFAULT_THEME };
  } catch {
    return { theme: DEFAULT_THEME };
  }
}

export function setStoredPreferences(preferences: UserPreferences): void {
  localStorage.setItem(STORAGE_KEYS.prefs, JSON.stringify({
    ...preferences,
    theme: preferences.theme === "light" ? "light" : DEFAULT_THEME,
  }));
}

export function setStoredIdentity(sessionToken: string, user: UserProfile, preferences: UserPreferences): void {
  localStorage.setItem(STORAGE_KEYS.sessionToken, sessionToken);
  localStorage.setItem(STORAGE_KEYS.user, JSON.stringify(user));
  setStoredPreferences(preferences || {});
}

export function clearStoredIdentity(): void {
  localStorage.removeItem(STORAGE_KEYS.sessionToken);
  localStorage.removeItem(STORAGE_KEYS.user);
  localStorage.removeItem(STORAGE_KEYS.prefs);
  clearAdminToken();
  clearGuestMode();
}

export function getAdminToken(): string | null {
  const token = sessionStorage.getItem(STORAGE_KEYS.adminToken);
  const exp = Number(sessionStorage.getItem(STORAGE_KEYS.adminExp) || "0");
  if (!token) return null;
  if (exp && Date.now() > exp) {
    clearAdminToken();
    return null;
  }
  return token;
}

export function setAdminToken(token: string, expiresInSec: number): void {
  sessionStorage.setItem(STORAGE_KEYS.adminToken, token);
  sessionStorage.setItem(STORAGE_KEYS.adminExp, String(Date.now() + expiresInSec * 1000));
}

export function clearAdminToken(): void {
  sessionStorage.removeItem(STORAGE_KEYS.adminToken);
  sessionStorage.removeItem(STORAGE_KEYS.adminExp);
}

export function buildApiHeaders(options: RequestOptions = {}): Record<string, string> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.includeUnlock) {
    const unlockToken = getUnlockToken();
    if (unlockToken) headers.Authorization = `Bearer ${unlockToken}`;
  }
  if (options.includeUser) {
    const sessionToken = getSessionToken();
    if (sessionToken) headers["X-Jarvis-Session"] = sessionToken;
  }
  headers["X-Jarvis-Guest-Key"] = ensureGuestKey();
  if (options.includeAdmin) {
    const adminToken = getAdminToken();
    const user = getStoredUser();
    if (adminToken) headers.Authorization = `Bearer ${adminToken}`;
    if (user) {
      headers["X-Jarvis-Role"] = "admin";
      headers["X-Jarvis-User-Id"] = user.id;
    }
  }
  if (options.mode) headers["X-Jarvis-Mode"] = options.mode;
  return headers;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = buildApiHeaders(options);
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 10_000);
  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method || "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: controller.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error("Request timed out");
    }
    throw err;
  } finally {
    clearTimeout(timeoutId);
  }
  const text = await response.text();
  const data = text ? JSON.parse(text) : {};
  if (response.status === 401) {
    clearStoredIdentity();
    window.dispatchEvent(new CustomEvent("jarvis:session-expired"));
  }
  if (!response.ok) throw new Error(data.detail || text || `HTTP ${response.status}`);
  return data as T;
}

export async function login(username: string, password: string) {
  return apiRequest<{ session_token: string; user: UserProfile; preferences: UserPreferences; capabilities?: UserCapabilities }>("/auth/login", {
    method: "POST",
    body: { username, password },
  });
}

export async function logout() {
  try {
    await apiRequest("/auth/logout", { method: "POST", includeUser: true });
  } finally {
    clearStoredIdentity();
  }
}

export async function fetchMe() {
  return apiRequest<{ user: UserProfile; preferences: UserPreferences; capabilities?: UserCapabilities }>("/auth/me", { includeUser: true });
}

export async function savePreferences(preferences: UserPreferences) {
  return apiRequest<{ preferences: UserPreferences }>("/auth/me/preferences", {
    method: "PUT",
    includeUser: true,
    body: preferences,
  });
}

export async function issueAdminSession() {
  return apiRequest<{ token: string; expires_in_sec: number; user_id: string; username: string; role: string }>("/admin/session", {
    method: "POST",
    includeUser: true,
  });
}

export async function getSignupConfig() {
  return apiRequest<{ enabled: boolean }>("/auth/signup/config");
}

export async function signupRequest(username: string, email: string, password: string) {
  return apiRequest<{ ok: boolean; email: string }>("/auth/signup", {
    method: "POST",
    body: { username, email, password },
  });
}

export async function verifySignup(email: string, code: string) {
  return apiRequest<{ session_token: string; user: UserProfile; preferences: UserPreferences; capabilities?: UserCapabilities }>("/auth/signup/verify", {
    method: "POST",
    body: { email, code },
  });
}

export async function resendSignupCode(email: string) {
  return apiRequest<{ ok: boolean; email: string }>("/auth/signup/resend", {
    method: "POST",
    body: { email },
  });
}
