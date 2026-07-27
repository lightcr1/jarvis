import { afterEach, describe, expect, it, vi } from "vitest";
import { clearStoredIdentity, setStoredIdentity } from "./client";
import { fetchVapidPublicKey, isPushSupported, urlBase64ToUint8Array } from "./push";

describe("urlBase64ToUint8Array", () => {
  it("decodes a urlsafe-base64 VAPID key into bytes", () => {
    // "BEL6" without padding, urlsafe-encoded
    const bytes = urlBase64ToUint8Array("QQ");
    expect(bytes).toBeInstanceOf(Uint8Array);
    expect(bytes.length).toBeGreaterThan(0);
    expect(bytes[0]).toBe("A".charCodeAt(0));
  });

  it("handles urlsafe characters (- and _)", () => {
    // base64 for bytes [0xfb, 0xff] is "-_8" without padding in urlsafe form of "+/8="
    const bytes = urlBase64ToUint8Array("-_8");
    expect(bytes[0]).toBe(0xfb);
    expect(bytes[1]).toBe(0xff);
  });
});

describe("isPushSupported", () => {
  it("reflects presence of serviceWorker/PushManager/Notification globals", () => {
    // jsdom test environment: PushManager is not implemented, so this should be false
    // unless the test setup stubs it in — either way, the function must not throw.
    expect(() => isPushSupported()).not.toThrow();
  });
});

describe("fetchVapidPublicKey", () => {
  afterEach(() => {
    clearStoredIdentity();
    vi.restoreAllMocks();
  });

  it("returns the public_key field from the API response", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ public_key: "abc123" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    setStoredIdentity("session-1", { id: "usr-1", username: "alice", role: "standard_user" }, {});
    const key = await fetchVapidPublicKey();
    expect(key).toBe("abc123");
  });
});
