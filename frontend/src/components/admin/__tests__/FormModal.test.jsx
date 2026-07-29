// FormModal is the shell behind New event / Edit event / Event settings.
//
// It trapped Escape: the only ways out were the X and a backdrop click. That
// stranded keyboard users, and because the backdrop is a full-screen overlay it
// also silently swallowed the next click anywhere on the page — a browser
// walkthrough of the organizer surface hung on exactly that.
//
// Vitest globals are imported rather than taken from the config, which declares
// none.
import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import FormModal from "../FormModal";

describe("FormModal", () => {
  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <FormModal open title="Event settings" onClose={onClose}>
        <p>body</p>
      </FormModal>,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("ignores other keys", () => {
    const onClose = vi.fn();
    render(
      <FormModal open title="Event settings" onClose={onClose}>
        <p>body</p>
      </FormModal>,
    );

    fireEvent.keyDown(document, { key: "Enter" });
    fireEvent.keyDown(document, { key: "a" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("stops listening once closed, so a later Escape doesn't fire onClose", () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <FormModal open title="Event settings" onClose={onClose}>
        <p>body</p>
      </FormModal>,
    );
    rerender(
      <FormModal open={false} title="Event settings" onClose={onClose}>
        <p>body</p>
      </FormModal>,
    );

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });

  it("is announced as a modal dialog named by its title", () => {
    render(
      <FormModal open title="New event" onClose={() => {}}>
        <p>body</p>
      </FormModal>,
    );

    const dialog = screen.getByRole("dialog", { name: "New event" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
  });

  it("renders nothing when closed", () => {
    render(
      <FormModal open={false} title="New event" onClose={() => {}}>
        <p>hidden body</p>
      </FormModal>,
    );

    expect(screen.queryByText("hidden body")).toBeNull();
  });

  it("renders the subtitle under the title when provided", () => {
    render(
      <FormModal
        open
        title="New event"
        subtitle="Schedule the visit and lay out the volunteer slots."
        onClose={() => {}}
      >
        <p>body</p>
      </FormModal>,
    );

    expect(
      screen.getByText("Schedule the visit and lay out the volunteer slots."),
    ).toBeInTheDocument();
  });

  it("omits the subtitle line when not provided", () => {
    render(
      <FormModal open title="New event" onClose={() => {}}>
        <p>body</p>
      </FormModal>,
    );

    expect(document.querySelector("[data-testid='form-modal-subtitle']")).toBeNull();
  });
});
