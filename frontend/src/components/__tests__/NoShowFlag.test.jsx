import React from "react";
import { render, screen } from "@testing-library/react";

import NoShowFlag, { NO_SHOW_FLAG_THRESHOLD } from "../NoShowFlag";

describe("NoShowFlag", () => {
  it("stays out of the way until the second no-show", () => {
    // One is an accident. Nobody should carry a red mark for a single
    // missed shift.
    for (const count of [undefined, 0, 1]) {
      const { unmount } = render(<NoShowFlag count={count} />);
      expect(screen.queryByTestId("no-show-flag")).toBeNull();
      unmount();
    }
  });

  it("appears on the second", () => {
    render(<NoShowFlag count={NO_SHOW_FLAG_THRESHOLD} />);
    expect(screen.getByTestId("no-show-flag")).toBeInTheDocument();
  });

  it("says what it means, because a bare red mark is an accusation with no evidence", () => {
    render(<NoShowFlag count={5} />);
    expect(
      screen.getByLabelText("5 no-shows in the last 12 months"),
    ).toBeInTheDocument();
  });
});
