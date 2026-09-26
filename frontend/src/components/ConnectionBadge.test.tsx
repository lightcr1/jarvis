import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ConnectionBadge } from "./ConnectionBadge";
import { connectionLevel, CONNECTION_LABEL } from "../shared/api/connection";

describe("connectionLevel", () => {
  it("maps online/connected to a level", () => {
    expect(connectionLevel(false, false)).toBe("offline");
    expect(connectionLevel(false, true)).toBe("offline");
    expect(connectionLevel(true, false)).toBe("reconnecting");
    expect(connectionLevel(true, true)).toBe("live");
  });
});

describe("ConnectionBadge", () => {
  it("shows live when online and connected", () => {
    render(<ConnectionBadge online connected />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", `Connection: ${CONNECTION_LABEL.live}`);
  });

  it("shows reconnecting when online but the live channel is down", () => {
    render(<ConnectionBadge online connected={false} />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", `Connection: ${CONNECTION_LABEL.reconnecting}`);
  });

  it("shows offline with no network, even if the socket reported open", () => {
    render(<ConnectionBadge online={false} connected />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", `Connection: ${CONNECTION_LABEL.offline}`);
  });

  it("shows listening while live and active", () => {
    render(<ConnectionBadge online connected listening />);
    expect(screen.getByRole("status")).toHaveAttribute("aria-label", "Connection: Listening");
  });
});
