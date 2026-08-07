import React from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

import SessionRatingModal from "../SessionRatingModal";

vi.mock("../../lib/authStorage", () => ({
  default: { getToken: () => "test-token" },
  getToken: () => "test-token",
}));

function makeFetch(handler) {
  return vi.fn(async (url, opts = {}) => handler(url, opts));
}

describe("SessionRatingModal", () => {
  it("does not render when open is false", () => {
    const { container } = render(
      <SessionRatingModal sessionId="s1" open={false} />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("Submit is disabled until a value is chosen", () => {
    render(<SessionRatingModal sessionId="s1" open={true} />);
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
  });

  it("requires comment when value is 2 or fewer", () => {
    render(<SessionRatingModal sessionId="s1" open={true} />);
    fireEvent.click(screen.getByLabelText("2 stars"));
    expect(screen.getByRole("button", { name: /submit/i })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Session rating comment"), {
      target: { value: "bad" },
    });
    expect(screen.getByRole("button", { name: /submit/i })).not.toBeDisabled();
  });

  it("submits without comment when value is 3 or higher", async () => {
    const fetcher = makeFetch(async (url, opts) => {
      expect(url).toMatch(/\/sessions\/s1\/rating$/);
      expect(JSON.parse(opts.body)).toEqual({ value: 4 });
      return { ok: true, status: 201, json: async () => ({}) };
    });
    const onSubmitted = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onSubmitted={onSubmitted}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByLabelText("4 stars"));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await waitFor(() => expect(onSubmitted).toHaveBeenCalled());
  });

  it("Cancel close invokes onCancel without posting", () => {
    const fetcher = vi.fn();
    const onCancel = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onCancel={onCancel}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /cancel close/i }));
    expect(onCancel).toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// K32 — the modal used to have no exit that led out of the drawer. "Submit"
// and "Cancel close" both leave you inside it, and a failed POST closed the
// only door. These cover the ways out.
// ---------------------------------------------------------------------------
describe("SessionRatingModal — the user can always leave", () => {
  it("Close without rating dismisses the drawer and posts nothing", () => {
    const fetcher = vi.fn();
    const onDismiss = vi.fn();
    const onCancel = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onCancel={onCancel}
        onDismiss={onDismiss}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /close without rating/i }),
    );
    expect(onDismiss).toHaveBeenCalled();
    // Distinct from "Cancel close", which keeps the drawer open.
    expect(onCancel).not.toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("Escape backs out to the drawer rather than submitting", () => {
    const fetcher = vi.fn();
    const onCancel = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onCancel={onCancel}
        fetcher={fetcher}
      />,
    );
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onCancel).toHaveBeenCalled();
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("a failed rating POST leaves the exit usable", async () => {
    // The bug: onSubmitted was only called on success, so a 500 left the
    // user holding a modal whose only door was the one that just failed.
    const fetcher = makeFetch(async () => ({ ok: false, status: 500 }));
    const onSubmitted = vi.fn();
    const onDismiss = vi.fn();
    render(
      <SessionRatingModal
        sessionId="s1"
        open={true}
        onSubmitted={onSubmitted}
        onDismiss={onDismiss}
        fetcher={fetcher}
      />,
    );
    fireEvent.click(screen.getByLabelText("5 stars"));
    fireEvent.click(screen.getByRole("button", { name: /submit/i }));
    await screen.findByRole("alert");
    expect(onSubmitted).not.toHaveBeenCalled();

    const out = screen.getByRole("button", { name: /close without rating/i });
    expect(out).not.toBeDisabled();
    fireEvent.click(out);
    expect(onDismiss).toHaveBeenCalled();
  });

  it("keeps Tab inside the dialog", () => {
    render(
      <SessionRatingModal sessionId="s1" open={true} onCancel={() => {}} />,
    );
    // The trap focuses the first control on open, so Shift+Tab from there
    // must wrap to the last rather than escaping into the page behind.
    const focusables = Array.from(
      screen.getByRole("dialog").querySelectorAll("button, textarea"),
    ).filter((el) => !el.disabled);
    expect(document.activeElement).toBe(focusables[0]);
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(focusables[focusables.length - 1]);
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(focusables[0]);
  });

  it("gives focus back to whatever opened it", () => {
    const opener = document.createElement("button");
    document.body.appendChild(opener);
    opener.focus();
    const { rerender } = render(
      <SessionRatingModal sessionId="s1" open={true} onCancel={() => {}} />,
    );
    expect(document.activeElement).not.toBe(opener);
    rerender(
      <SessionRatingModal sessionId="s1" open={false} onCancel={() => {}} />,
    );
    expect(document.activeElement).toBe(opener);
    opener.remove();
  });
});
