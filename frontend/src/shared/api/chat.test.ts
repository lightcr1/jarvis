import { afterEach, describe, expect, it, vi } from "vitest";
import { createChatSession, getChatSession } from "./chat";

describe("chat api wrappers", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.clear();
    sessionStorage.clear();
  });

  it("normalizes create session response to session_id", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify({ id: "chat-123" }),
      }),
    );

    const data = await createChatSession();

    expect(data).toEqual({ session_id: "chat-123" });
  });

  it("normalizes session detail response to nested session shape", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        text: async () => JSON.stringify({ id: "chat-123", messages: [{ role: "user", text: "hi", ts: 1 }] }),
      }),
    );

    const data = await getChatSession("chat-123");

    expect(data).toEqual({
      session: {
        id: "chat-123",
        messages: [{ role: "user", text: "hi", ts: 1 }],
      },
    });
  });
});
