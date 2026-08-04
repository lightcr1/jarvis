import { describe, expect, it } from "vitest";
import { shouldAutoStartOnWakeword, shouldAutoStopOnSilence } from "./OrbScreen";

describe("shouldAutoStartOnWakeword", () => {
  it("returns false when there is no event", () => {
    expect(shouldAutoStartOnWakeword(null, null, "idle")).toBe(false);
    expect(shouldAutoStartOnWakeword(undefined, null, "idle")).toBe(false);
  });

  it("returns false for event kinds other than wakeword", () => {
    expect(shouldAutoStartOnWakeword({ kind: "briefing_ready", ts: 100 }, null, "idle")).toBe(false);
  });

  it("returns true for a fresh wakeword event while idle", () => {
    expect(shouldAutoStartOnWakeword({ kind: "wakeword", ts: 100 }, null, "idle")).toBe(true);
  });

  it("returns false when the orb is not idle", () => {
    expect(shouldAutoStartOnWakeword({ kind: "wakeword", ts: 100 }, null, "listening")).toBe(false);
    expect(shouldAutoStartOnWakeword({ kind: "wakeword", ts: 100 }, null, "thinking")).toBe(false);
    expect(shouldAutoStartOnWakeword({ kind: "wakeword", ts: 100 }, null, "speaking")).toBe(false);
  });

  it("returns false when the event was already handled (reconnect replay)", () => {
    expect(shouldAutoStartOnWakeword({ kind: "wakeword", ts: 100 }, 100, "idle")).toBe(false);
  });

  it("returns true for a new event timestamp after a previous one was handled", () => {
    expect(shouldAutoStartOnWakeword({ kind: "wakeword", ts: 200 }, 100, "idle")).toBe(true);
  });
});

describe("shouldAutoStopOnSilence", () => {
  it("does not stop before the minimum recording duration, even with long silence", () => {
    expect(shouldAutoStopOnSilence(2000, 200)).toBe(false);
  });

  it("does not stop while sound is recent, even after the minimum duration", () => {
    expect(shouldAutoStopOnSilence(300, 2000)).toBe(false);
  });

  it("stops once both the minimum duration and silence threshold are exceeded", () => {
    expect(shouldAutoStopOnSilence(1300, 500)).toBe(true);
    expect(shouldAutoStopOnSilence(5000, 5000)).toBe(true);
  });

  it("does not stop right at the boundary minus one", () => {
    expect(shouldAutoStopOnSilence(1299, 500)).toBe(false);
    expect(shouldAutoStopOnSilence(1300, 499)).toBe(false);
  });
});
