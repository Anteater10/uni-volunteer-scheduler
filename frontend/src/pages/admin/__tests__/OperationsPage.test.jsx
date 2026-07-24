// OperationsPage — the consolidated day-of console (former Preview +
// Reminders tabs). These tests lock the ?tab= URL contract that the legacy
// /admin/preview and /admin/reminders redirects in App.jsx depend on.
import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

// Stub both hosted sub-views so the test focuses on tab wiring, not on the
// sub-views' own data fetching (covered by their dedicated test files).
vi.mock("../../organizer/OrganizerDashboard", () => ({
  default: ({ embedded, scope }) => (
    <div data-testid="dashboard" data-embedded={String(embedded)} data-scope={scope} />
  ),
}));
vi.mock("../AdminRemindersPage", () => ({
  default: ({ embedded }) => (
    <div data-testid="reminders" data-embedded={String(embedded)} />
  ),
}));

import OperationsPage from "../OperationsPage";

function renderAt(url = "/admin/operations") {
  return render(
    <MemoryRouter initialEntries={[url]}>
      <OperationsPage />
    </MemoryRouter>,
  );
}

describe("OperationsPage", () => {
  it("defaults to the Today schedule scope", () => {
    renderAt();
    const dash = screen.getByTestId("dashboard");
    expect(dash).toHaveAttribute("data-scope", "today");
    expect(dash).toHaveAttribute("data-embedded", "true");
    expect(screen.getByRole("tab", { name: "Today" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.queryByTestId("reminders")).toBeNull();
  });

  it("renders the Reminders view for ?tab=reminders (legacy /admin/reminders redirect target)", () => {
    renderAt("/admin/operations?tab=reminders");
    expect(screen.getByTestId("reminders")).toHaveAttribute(
      "data-embedded",
      "true",
    );
    expect(screen.queryByTestId("dashboard")).toBeNull();
    expect(screen.getByRole("tab", { name: "Reminders" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("falls back to Today for an unknown ?tab value", () => {
    renderAt("/admin/operations?tab=bogus");
    expect(screen.getByTestId("dashboard")).toHaveAttribute(
      "data-scope",
      "today",
    );
    expect(screen.getByRole("tab", { name: "Today" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("switches between schedule scopes and Reminders via the flat tab bar", () => {
    renderAt();
    fireEvent.click(screen.getByRole("tab", { name: "Upcoming" }));
    expect(screen.getByTestId("dashboard")).toHaveAttribute(
      "data-scope",
      "upcoming",
    );

    fireEvent.click(screen.getByRole("tab", { name: "Reminders" }));
    expect(screen.getByTestId("reminders")).toBeInTheDocument();
    expect(screen.queryByTestId("dashboard")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Today" }));
    expect(screen.getByTestId("dashboard")).toHaveAttribute(
      "data-scope",
      "today",
    );
  });
});
