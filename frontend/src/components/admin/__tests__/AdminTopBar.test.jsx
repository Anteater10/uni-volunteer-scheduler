import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AdminTopBar from "../AdminTopBar";

function renderBar(props = {}) {
  const defaults = {
    crumbs: [
      { label: "Admin", to: "/admin" },
      { label: "Users" },
    ],
  };
  return render(
    <MemoryRouter>
      <AdminTopBar {...defaults} {...props} />
    </MemoryRouter>,
  );
}

describe("AdminTopBar", () => {
  it("renders breadcrumbs with the leading crumb as a link and the last as the current page", () => {
    renderBar();
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute(
      "href",
      "/admin",
    );
    const currentCrumb = screen.getByText("Users");
    expect(currentCrumb).toBeInTheDocument();
    expect(currentCrumb).toHaveAttribute("aria-current", "page");
  });

  it("renders the optional centerSlot when provided", () => {
    renderBar({ centerSlot: <span data-testid="center">CENTER</span> });
    expect(screen.getByTestId("center")).toBeInTheDocument();
  });
});
