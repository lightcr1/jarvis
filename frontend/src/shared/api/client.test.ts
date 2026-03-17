import { afterEach, describe, expect, it, vi } from "vitest";
import {
  apiRequest,
  clearAdminToken,
  clearStoredIdentity,
  clearUnlockToken,
  setAdminToken,
  setStoredIdentity,
  setUnlockToken,
} from "./client";

describe("apiRequest", () => {
  afterEach(() => {
    clearUnlockToken();
    clearStoredIdentity();
    clearAdminToken();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("sends session, guest and mode headers", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    setStoredIdentity("session-1", { id: "usr-1", username: "alice", role: "admin" }, { theme: "dark" });

    await apiRequest("/chat", { includeUser: true, mode: "orb" });

    const [, options] = fetchSpy.mock.calls[0];
    const headers = options?.headers as Record<string, string>;
    expect(headers["X-Jarvis-Session"]).toBe("session-1");
    expect(headers["X-Jarvis-Guest-Key"]).toMatch(/^guest-/);
    expect(headers["X-Jarvis-Mode"]).toBe("orb");
  });

  it("adds admin and unlock headers when requested", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    setStoredIdentity("session-2", { id: "usr-2", username: "admin", role: "admin" }, {});
    setAdminToken("admin-token", 60);
    setUnlockToken("unlock-token", 60);

    await apiRequest("/admin/users", { includeAdmin: true, includeUnlock: true });

    const [, options] = fetchSpy.mock.calls[0];
    const headers = options?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer admin-token");
    expect(headers["X-Jarvis-Role"]).toBe("admin");
    expect(headers["X-Jarvis-User-Id"]).toBe("usr-2");
  });
});
