import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatEmptyState } from "./ChatEmptyState";

describe("ChatEmptyState", () => {
  it("forwards prompt selection from suggestion cards", () => {
    const onPromptSelect = vi.fn();
    render(<ChatEmptyState onPromptSelect={onPromptSelect} />);

    fireEvent.click(screen.getByText("Status check"));

    expect(onPromptSelect).toHaveBeenCalledWith("status jarvis");
  });
});
