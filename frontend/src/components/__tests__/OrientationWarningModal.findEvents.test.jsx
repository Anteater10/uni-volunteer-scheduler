// K22 — "I haven't — show me orientation events" promised a search the app
// never performed.
//
// The advisory variant of this modal renders only when the event has *no*
// orientation slots. That button called onNo, whose handler set
// highlightOrientation on the event page behind it — a page with no
// orientation slots to highlight. The volunteer was returned to exactly where
// they started, having asked to be shown something else.

import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import OrientationWarningModal from "../OrientationWarningModal";

function renderAdvisory(props = {}) {
  return render(
    <OrientationWarningModal
      open
      required={false}
      onYes={() => {}}
      onNo={() => {}}
      {...props}
    />,
  );
}

describe("OrientationWarningModal — the advisory variant's escape hatch (K22)", () => {
  it("routes 'show me orientation events' away from onNo", async () => {
    const user = userEvent.setup();
    const onNo = vi.fn();
    const onFindOrientation = vi.fn();
    renderAdvisory({ onNo, onFindOrientation });

    await user.click(
      screen.getByRole("button", { name: /show me orientation events/i }),
    );

    expect(onFindOrientation).toHaveBeenCalledTimes(1);
    // onNo is dismissal. Conflating the two is what made the label a lie.
    expect(onNo).not.toHaveBeenCalled();
  });

  it("still falls back to onNo when no handler is supplied", async () => {
    const user = userEvent.setup();
    const onNo = vi.fn();
    renderAdvisory({ onNo });

    await user.click(
      screen.getByRole("button", { name: /show me orientation events/i }),
    );

    expect(onNo).toHaveBeenCalledTimes(1);
  });

  it("leaves 'I've done orientation' on the proceed path", async () => {
    const user = userEvent.setup();
    const onYes = vi.fn();
    const onFindOrientation = vi.fn();
    renderAdvisory({ onYes, onFindOrientation });

    await user.click(
      screen.getByRole("button", { name: /I've done orientation/i }),
    );

    expect(onYes).toHaveBeenCalledTimes(1);
    expect(onFindOrientation).not.toHaveBeenCalled();
  });

  it("spells the brand the way the rest of the product does", () => {
    // K20: this modal wrote "Sci Trek" in three places.
    renderAdvisory();
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("SciTrek");
    expect(dialog.textContent).not.toContain("Sci Trek");
  });
});
