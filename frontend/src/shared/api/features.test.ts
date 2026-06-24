import { describe, expect, it } from "vitest";
import { serializeChatToMarkdown } from "../../screens/ChatScreen";
import { metricsToHealthTier } from "../../screens/OrbScreen";

describe("serializeChatToMarkdown", () => {
  it("includes session title and export date in header", () => {
    const md = serializeChatToMarkdown("My Session", []);
    expect(md).toContain("# JARVIS Chat — My Session");
    expect(md).toContain("Exported");
    expect(md).toContain("---");
  });

  it("labels user and jarvis roles correctly", () => {
    const msgs = [
      { role: "user", content: "Hello", time: "12:00" },
      { role: "jarvis", content: "Hi there", time: "12:01" },
    ];
    const md = serializeChatToMarkdown("Test", msgs);
    expect(md).toContain("**You:** Hello");
    expect(md).toContain("**JARVIS:** Hi there");
  });

  it("strips streaming cursor from content", () => {
    const msgs = [{ role: "jarvis", content: "Thinking...▋", time: "12:00" }];
    const md = serializeChatToMarkdown("Test", msgs);
    expect(md).toContain("Thinking...");
    expect(md).not.toContain("▋");
  });

  it("returns only header when messages array is empty", () => {
    const md = serializeChatToMarkdown("Empty", []);
    expect(md).toContain("# JARVIS Chat — Empty");
    expect(md).not.toContain("**You:**");
    expect(md).not.toContain("**JARVIS:**");
  });
});

describe("metricsToHealthTier", () => {
  it("returns good when all metrics are low", () => {
    expect(metricsToHealthTier({ cpu_percent: 10, ram_percent: 20, disk_percent: 30 })).toBe("good");
  });

  it("returns warn when any metric exceeds 75", () => {
    expect(metricsToHealthTier({ cpu_percent: 80, ram_percent: 20, disk_percent: 30 })).toBe("warn");
    expect(metricsToHealthTier({ cpu_percent: 10, ram_percent: 76, disk_percent: 30 })).toBe("warn");
    expect(metricsToHealthTier({ cpu_percent: 10, ram_percent: 20, disk_percent: 76 })).toBe("warn");
  });

  it("returns critical when any metric exceeds 90", () => {
    expect(metricsToHealthTier({ cpu_percent: 91, ram_percent: 20, disk_percent: 30 })).toBe("critical");
    expect(metricsToHealthTier({ cpu_percent: 10, ram_percent: 92, disk_percent: 30 })).toBe("critical");
    expect(metricsToHealthTier({ cpu_percent: 10, ram_percent: 20, disk_percent: 95 })).toBe("critical");
  });

  it("returns critical when multiple metrics are critical", () => {
    expect(metricsToHealthTier({ cpu_percent: 95, ram_percent: 95, disk_percent: 95 })).toBe("critical");
  });

  it("treats exactly 75 as warn boundary", () => {
    expect(metricsToHealthTier({ cpu_percent: 75.1, ram_percent: 0, disk_percent: 0 })).toBe("warn");
    expect(metricsToHealthTier({ cpu_percent: 75, ram_percent: 0, disk_percent: 0 })).toBe("good");
  });

  it("treats exactly 90 as critical boundary", () => {
    expect(metricsToHealthTier({ cpu_percent: 90.1, ram_percent: 0, disk_percent: 0 })).toBe("critical");
    expect(metricsToHealthTier({ cpu_percent: 90, ram_percent: 0, disk_percent: 0 })).toBe("warn");
  });
});
