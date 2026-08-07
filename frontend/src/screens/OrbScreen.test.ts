import { describe, expect, it } from "vitest";
import { shouldAutoStartOnWakeword, shouldAutoStopOnSilence, pickAlertToSpeak } from "./OrbScreen";
import type { JarvisAlert } from "../shared/api/alerts";

function makeAlert(overrides: Partial<JarvisAlert> = {}): JarvisAlert {
  return { id: "a1", level: "warning", title: "CPU", message: "CPU above 90% for 5 minutes.", source: "system", code: "cpu_high", ...overrides };
}

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

describe("pickAlertToSpeak", () => {
  it("picks a warning-level alert when idle and unmuted", () => {
    const alert = makeAlert({ level: "warning" });
    expect(pickAlertToSpeak([alert], "idle", false, new Set())).toBe(alert);
  });

  it("picks a critical-level alert too", () => {
    const alert = makeAlert({ level: "critical" });
    expect(pickAlertToSpeak([alert], "idle", false, new Set())).toBe(alert);
  });

  it("does not pick an info-level alert — not urgent enough to interrupt unprompted", () => {
    const alert = makeAlert({ level: "info" });
    expect(pickAlertToSpeak([alert], "idle", false, new Set())).toBeNull();
  });

  it("does not pick anything while not idle", () => {
    const alert = makeAlert();
    expect(pickAlertToSpeak([alert], "listening", false, new Set())).toBeNull();
    expect(pickAlertToSpeak([alert], "thinking", false, new Set())).toBeNull();
    expect(pickAlertToSpeak([alert], "speaking", false, new Set())).toBeNull();
  });

  it("does not pick anything when TTS is muted", () => {
    const alert = makeAlert();
    expect(pickAlertToSpeak([alert], "idle", true, new Set())).toBeNull();
  });

  it("skips an alert that was already spoken", () => {
    const alert = makeAlert({ id: "a1" });
    expect(pickAlertToSpeak([alert], "idle", false, new Set(["a1"]))).toBeNull();
  });

  it("picks the first eligible alert when several are pending", () => {
    const first = makeAlert({ id: "a1", level: "info" });
    const second = makeAlert({ id: "a2", level: "warning" });
    const third = makeAlert({ id: "a3", level: "critical" });
    expect(pickAlertToSpeak([first, second, third], "idle", false, new Set())).toBe(second);
  });

  it("returns null when there are no alerts", () => {
    expect(pickAlertToSpeak([], "idle", false, new Set())).toBeNull();
  });
});
