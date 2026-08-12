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

  // An admin part-way through laying out an event's slots loses everything if
  // the dialog closes: FormModal unmounts its children, so the form's state
  // goes with it. A stray click on the backdrop is not consent to throw that
  // away, so once the form reports itself dirty every exit asks first.
  describe("with unsaved changes", () => {
    const backdrop = () => screen.getByTestId("form-modal-backdrop");
    const panel = () => screen.getByRole("dialog");

    it("asks before discarding when the backdrop is clicked", () => {
      const onClose = vi.fn();
      render(
        <FormModal open dirty title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.mouseDown(backdrop());

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
      expect(screen.getByText("body")).toBeInTheDocument();
    });

    it("closes once the discard is confirmed", () => {
      const onClose = vi.fn();
      render(
        <FormModal open dirty title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.mouseDown(backdrop());
      fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));

      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("keeps the form when the discard is declined", () => {
      const onClose = vi.fn();
      render(
        <FormModal open dirty title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.mouseDown(backdrop());
      fireEvent.click(screen.getByRole("button", { name: "Keep editing" }));

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.queryByText("Discard changes?")).toBeNull();
      expect(screen.getByText("body")).toBeInTheDocument();
    });

    it("asks before discarding on Escape", () => {
      const onClose = vi.fn();
      render(
        <FormModal open dirty title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.keyDown(document, { key: "Escape" });

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
    });

    it("asks before discarding on the close button", () => {
      const onClose = vi.fn();
      render(
        <FormModal open dirty title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.click(screen.getByRole("button", { name: "Close" }));

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.getByText("Discard changes?")).toBeInTheDocument();
    });

    // A drag that starts in a text field and ends past the panel edge reports
    // its click on the backdrop. Listening for mousedown instead of click is
    // what keeps selecting text from reading as "clicked off the dialog".
    it("ignores a drag that starts inside the panel and ends on the backdrop", () => {
      const onClose = vi.fn();
      render(
        <FormModal open dirty title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.mouseDown(panel());
      fireEvent.click(backdrop());

      expect(onClose).not.toHaveBeenCalled();
      expect(screen.queryByText("Discard changes?")).toBeNull();
    });
  });

  describe("with a clean form", () => {
    it("closes straight away on a backdrop click", () => {
      const onClose = vi.fn();
      render(
        <FormModal open title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.mouseDown(screen.getByTestId("form-modal-backdrop"));

      expect(onClose).toHaveBeenCalledTimes(1);
      expect(screen.queryByText("Discard changes?")).toBeNull();
    });

    it("ignores a drag that ends on the backdrop", () => {
      const onClose = vi.fn();
      render(
        <FormModal open title="New event" onClose={onClose}>
          <p>body</p>
        </FormModal>,
      );

      fireEvent.mouseDown(screen.getByRole("dialog"));
      fireEvent.click(screen.getByTestId("form-modal-backdrop"));

      expect(onClose).not.toHaveBeenCalled();
    });
  });
});
