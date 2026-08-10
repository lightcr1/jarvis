import { describe, expect, it } from "vitest";
import { pickAmbientAlertToSpeak } from "./AmbientDisplayScreen";
import type { JarvisAlert } from "../shared/api/alerts";

function makeAlert(overrides: Partial<JarvisAlert> = {}): JarvisAlert {
  return { id: "a1", level: "warning", title: "CPU", message: "CPU above 90% for 5 minutes.", source: "system", code: "cpu_high", ...overrides };
}

describe("pickAmbientAlertToSpeak", () => {
  it("picks a warning-level alert", () => {
    const alert = makeAlert({ level: "warning" });
    expect(pickAmbientAlertToSpeak([alert], new Set())).toBe(alert);
  });

  it("picks a critical-level alert too", () => {
    const alert = makeAlert({ level: "critical" });
    expect(pickAmbientAlertToSpeak([alert], new Set())).toBe(alert);
  });

  it("does not pick an info-level alert", () => {
    const alert = makeAlert({ level: "info" });
    expect(pickAmbientAlertToSpeak([alert], new Set())).toBeNull();
  });

  it("skips an alert that was already spoken", () => {
    const alert = makeAlert({ id: "a1" });
    expect(pickAmbientAlertToSpeak([alert], new Set(["a1"]))).toBeNull();
  });

  it("picks the first eligible alert when several are pending", () => {
    const first = makeAlert({ id: "a1", level: "info" });
    const second = makeAlert({ id: "a2", level: "warning" });
    const third = makeAlert({ id: "a3", level: "critical" });
    expect(pickAmbientAlertToSpeak([first, second, third], new Set())).toBe(second);
  });

  it("returns null when there are no alerts", () => {
    expect(pickAmbientAlertToSpeak([], new Set())).toBeNull();
  });
});
