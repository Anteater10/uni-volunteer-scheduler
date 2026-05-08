import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import AdminLayout from "../AdminLayout";

// Mock useAuth so the layout renders without a real AuthProvider.
vi.mock("../../../state/useAuth", () => ({
  useAuth: () => ({
    user: { name: "Andy", email: "andy@example.com", role: "admin" },
    logout: vi.fn(),
  }),
}));

function renderAtDesktop(width = 1200) {
  Object.defineProperty(window, "innerWidth", {
    writable: true,
    configurable: true,
    value: width,
  });
  return render(
    <MemoryRouter initialEntries={["/admin"]}>
      <Routes>
        <Route path="/admin" element={<AdminLayout />}>
          <Route index element={<div data-testid="child-outlet">OUTLET CONTENT</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("AdminLayout", () => {
  it("renders the expected sidebar nav items (no Overrides, no Portals)", () => {
    renderAtDesktop();
    for (const label of [
      "Overview",
      "Events",
      "Users",
      "Audit Logs",
      "Exports",
      "Templates",
      "Imports",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(screen.queryByRole("link", { name: /overrides/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /portals/i })).toBeNull();
  });

  it("renders the child outlet when window width >= 768px", () => {
    renderAtDesktop(1200);
    expect(screen.getByTestId("child-outlet")).toBeInTheDocument();
    expect(
      screen.queryByText(
        /This admin view is designed for screens ≥ 768px/i,
      ),
    ).toBeNull();
  });

  it("renders DesktopOnlyBanner when window width < 768px", () => {
    renderAtDesktop(500);
    expect(
      screen.getByText(/This admin view is designed for screens ≥ 768px/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("child-outlet")).toBeNull();
  });
});
