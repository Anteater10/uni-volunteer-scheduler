import React from "react";
import { render, screen } from "@testing-library/react";
import DesktopOnlyBanner from "../DesktopOnlyBanner";

describe("DesktopOnlyBanner", () => {
  it("renders the required plain-English message", () => {
    render(<DesktopOnlyBanner />);
    expect(
      screen.getByText(
        /This admin view is designed for screens ≥ 768px — please use a laptop or tablet\./i,
      ),
    ).toBeInTheDocument();
  });
});
