import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AdminTopBar from "../AdminTopBar";

function renderBar(props = {}) {
  const defaults = {
    crumbs: [
      { label: "Admin", to: "/admin" },
      { label: "Users" },
    ],
    user: { name: "Andy", email: "andy@example.com", role: "admin" },
    onSignOut: vi.fn(),
  };
  return render(
    <MemoryRouter>
      <AdminTopBar {...defaults} {...props} />
    </MemoryRouter>,
  );
}

describe("AdminTopBar", () => {
  it("renders breadcrumbs, help link, and user name", () => {
    renderBar();
    // "Admin" appears in breadcrumb AND as RoleBadge text — just assert the breadcrumb link
    expect(screen.getByRole("link", { name: "Admin" })).toHaveAttribute("href", "/admin");
    expect(screen.getByText("Users")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /help/i })).toHaveAttribute(
      "href",
      "/admin/help",
    );
    expect(screen.getByText("Andy")).toBeInTheDocument();
  });

  it("opens account menu and calls onSignOut", () => {
    const onSignOut = vi.fn();
    renderBar({ onSignOut });
    fireEvent.click(screen.getByText("Andy"));
    const signOutBtn = screen.getByRole("menuitem", { name: /sign out/i });
    fireEvent.click(signOutBtn);
    expect(onSignOut).toHaveBeenCalledTimes(1);
  });
});
