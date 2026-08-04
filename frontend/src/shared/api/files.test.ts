import { afterEach, describe, expect, it, vi } from "vitest";
import { clearStoredIdentity, setStoredIdentity } from "./client";
import {
  createShareLink,
  downloadPublicShare,
  fetchPublicShareInfo,
  listShareLinks,
  revokeShareLink,
  shareLinkUrl,
} from "./files";

describe("share links API", () => {
  afterEach(() => {
    clearStoredIdentity();
    localStorage.clear();
    sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("createShareLink sends session header and optional password/expiry", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ policy: {}, share: { id: "s1", token: "tok1" } }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    setStoredIdentity("session-1", { id: "usr-1", username: "alice", role: "standard_user" }, {});

    await createShareLink("file-1", { password: "hunter2", expiresAt: 12345 });

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe("/files/file-1/share-links");
    const headers = options?.headers as Record<string, string>;
    expect(headers["X-Jarvis-Session"]).toBe("session-1");
    const body = JSON.parse(options?.body as string);
    expect(body).toEqual({ expires_at: 12345, password: "hunter2" });
  });

  it("listShareLinks and revokeShareLink hit the expected endpoints", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ policy: {}, shares: [] }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    await listShareLinks("file-1");
    expect(fetchSpy.mock.calls[0][0]).toBe("/files/file-1/share-links");

    fetchSpy.mockResolvedValue(
      new Response(JSON.stringify({ policy: {}, deleted: true }), { status: 200, headers: { "Content-Type": "application/json" } }),
    );
    await revokeShareLink("share-1");
    const [url, options] = fetchSpy.mock.calls[1];
    expect(url).toBe("/files/share-links/share-1");
    expect(options?.method).toBe("DELETE");
  });

  it("fetchPublicShareInfo does not send a session header", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ filename: "a.txt", size_bytes: 5, mime_type: "text/plain", requires_password: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    setStoredIdentity("session-1", { id: "usr-1", username: "alice", role: "standard_user" }, {});

    const info = await fetchPublicShareInfo("tok1");

    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe("/public/files/shared/tok1");
    const headers = options?.headers as Record<string, string>;
    expect(headers["X-Jarvis-Session"]).toBeUndefined();
    expect(info.filename).toBe("a.txt");
  });

  it("downloadPublicShare posts the password and triggers a browser download", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(new Blob(["file bytes"]), { status: 200 }),
    );
    const createObjectURL = vi.fn().mockReturnValue("blob:mock");
    const revokeObjectURL = vi.fn();
    (URL as unknown as { createObjectURL: typeof createObjectURL }).createObjectURL = createObjectURL;
    (URL as unknown as { revokeObjectURL: typeof revokeObjectURL }).revokeObjectURL = revokeObjectURL;
    const clickSpy = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    vi.spyOn(document, "createElement").mockImplementation((tag: string) => {
      const el = originalCreateElement(tag);
      if (tag === "a") el.click = clickSpy;
      return el;
    });

    await downloadPublicShare("tok1", "secret.txt", "hunter2");

    const fetchSpy = vi.mocked(globalThis.fetch);
    const [url, options] = fetchSpy.mock.calls[0];
    expect(url).toBe("/public/files/shared/tok1/download");
    expect(options?.method).toBe("POST");
    expect(JSON.parse(options?.body as string)).toEqual({ password: "hunter2" });
    expect(clickSpy).toHaveBeenCalled();
  });

  it("throws with the server detail message when the download fails", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid password" }), { status: 403 }),
    );
    await expect(downloadPublicShare("tok1", "secret.txt", "wrong")).rejects.toThrow("invalid password");
  });

  it("shareLinkUrl builds a full URL rooted at the current origin", () => {
    expect(shareLinkUrl("abc123")).toBe(`${window.location.origin}/s/abc123`);
  });
});
