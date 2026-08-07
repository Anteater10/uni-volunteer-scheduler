// K5 — a dialog taller than the phone screen used to be a dead end.
//
// Modal's backdrop is `position: fixed; inset: 0`, which pins it to exactly
// one screen. With no overflow rule, a panel taller than that screen simply
// ran off the bottom: the page behind couldn't scroll (it's covered), the
// backdrop wouldn't scroll (no overflow), and the panel wasn't its own scroll
// container either. Whatever sat at the bottom of the dialog — which is where
// Confirm and Cancel live — was unreachable.
//
// jsdom has no layout engine, so it can't measure "off the screen". What it
// can check is the contract the fix rests on: the backdrop is the scroll
// container, and the panel no longer has an unescapable fixed top offset.

import React from "react";
import { render, screen } from "@testing-library/react";
import Modal from "../ui/Modal";

function backdropOf(dialog) {
  return dialog.parentElement;
}

describe("Modal — tall content stays reachable (K5)", () => {
  it("makes the backdrop the scroll container", () => {
    render(
      <Modal open onClose={() => {}} title="A very long form">
        <p>body</p>
      </Modal>,
    );

    const backdrop = backdropOf(screen.getByRole("dialog"));
    expect(backdrop.className).toMatch(/\boverflow-y-auto\b/);
    // Still the full-screen fixed backdrop — the fix must not turn it into a
    // normal flow element, or the page behind starts scrolling instead.
    expect(backdrop.className).toMatch(/\bfixed\b/);
    expect(backdrop.className).toMatch(/\binset-0\b/);
  });

  it("pads the backdrop so a grown panel doesn't touch the screen edges", () => {
    render(
      <Modal open onClose={() => {}}>
        <p>body</p>
      </Modal>,
    );

    expect(backdropOf(screen.getByRole("dialog")).className).toMatch(/\bp-4\b/);
  });

  it("gives the panel margin below it, not just above", () => {
    render(
      <Modal open onClose={() => {}}>
        <p>body</p>
      </Modal>,
    );

    const panel = screen.getByRole("dialog");
    // `mt-[15vh]` alone left the bottom of a scrolled panel flush against the
    // viewport edge with nothing after it. A symmetric margin scrolls clear.
    expect(panel.className).toContain("my-[10vh]");
    expect(panel.className).not.toContain("mt-[15vh]");
  });

  it("still closes on a backdrop click after the layout change", async () => {
    const onClose = vi.fn();
    const { default: userEvent } = await import("@testing-library/user-event");
    const user = userEvent.setup();
    render(
      <Modal open onClose={onClose}>
        <p>body</p>
      </Modal>,
    );

    await user.pointer({
      keys: "[MouseLeft>]",
      target: backdropOf(screen.getByRole("dialog")),
    });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
