import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ChatComposer } from "./ChatComposer";

describe("ChatComposer", () => {
  it("sends on Enter without shift", () => {
    const onSend = vi.fn();
    render(
      <ChatComposer
        input="status jarvis"
        busy={false}
        voiceBusy={false}
        userLoggedIn
        onInputChange={vi.fn()}
        onSend={onSend}
        onMic={vi.fn()}
        onClear={vi.fn()}
        onPromptSelect={vi.fn()}
      />,
    );

    fireEvent.keyDown(screen.getByPlaceholderText("Message Jarvis…"), { key: "Enter" });

    expect(onSend).toHaveBeenCalledTimes(1);
  });

  it("shows guest copy when no user is logged in", () => {
    render(
      <ChatComposer
        input=""
        busy={false}
        voiceBusy={false}
        userLoggedIn={false}
        onInputChange={vi.fn()}
        onSend={vi.fn()}
        onMic={vi.fn()}
        onClear={vi.fn()}
        onPromptSelect={vi.fn()}
      />,
    );

    expect(screen.getByText("Guest mode is temporary. Login to save preferences.")).toBeTruthy();
  });
});
