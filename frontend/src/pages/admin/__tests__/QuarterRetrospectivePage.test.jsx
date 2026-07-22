// Issue #38 — QuarterRetrospectivePage: read-only drill-in from the
// Quarters table showing how a past quarter's events ran (per-event
// signup/capacity/attended/no-show counts plus headline totals).

import React from "react";
import { render, screen, fireEvent, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const retrospectiveMock = vi.fn();

vi.mock("../../../lib/api", () => ({
  default: {
    admin: {
      quarters: {
        retrospective: (...a) => retrospectiveMock(...a),
      },
    },
  },
}));

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import QuarterRetrospectivePage from "../QuarterRetrospectivePage";

const PAYLOAD = {
  quarter: {
    id: "q1",
    season: "winter",
    year: 2026,
    label: "",
    start_date: "2026-01-05",
    end_date: "2026-03-20",
    weeks_in_quarter: 11,
    display_name: "Winter 2026",
    archived_at: "2026-07-01T00:00:00Z",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  totals: {
    events: 7,
    slots: 9,
    capacity: 42,
    signups: 24,
    attended: 18,
    no_shows: 5,
    attendance_rate: 0.75,
  },
  events: [
    {
      event_id: "e1",
      title: "Week 1 kickoff",
      start_date: "2026-01-06T17:00:00Z",
      week_number: 1,
      slot_count: 2,
      capacity: 20,
      signups: 16,
      attended: 12,
      no_shows: 3,
    },
    {
      event_id: "e2",
      title: "Legacy import",
      start_date: "2026-02-10T17:00:00Z",
      week_number: null,
      slot_count: 1,
      capacity: 10,
      signups: 8,
      attended: 6,
      no_shows: 2,
    },
  ],
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/admin/quarters/q1"]}>
        <Routes>
          <Route
            path="/admin/quarters/:quarterId"
            element={<QuarterRetrospectivePage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("QuarterRetrospectivePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    retrospectiveMock.mockResolvedValue(PAYLOAD);
  });

  it("renders headline totals for the quarter", async () => {
    renderPage();

    expect(await screen.findByText("Winter 2026")).toBeInTheDocument();
    expect(screen.getByText("Archived")).toBeInTheDocument();
    expect(retrospectiveMock).toHaveBeenCalledWith("q1");

    expect(screen.getByText("Events ran")).toBeInTheDocument();
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByText("24")).toBeInTheDocument();
    expect(screen.getByText("Capacity: 42")).toBeInTheDocument();
    expect(screen.getByText("18")).toBeInTheDocument();
    expect(screen.getByText("Attendance rate: 75%")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("renders a row per event with signup, capacity, attended and no-show counts", async () => {
    renderPage();

    const row = (await screen.findByText("Week 1 kickoff")).closest("tr");
    expect(within(row).getByText("16/20")).toBeInTheDocument();
    expect(within(row).getByText("12")).toBeInTheDocument();
    expect(within(row).getByText("3")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Week 1 kickoff" })).toHaveAttribute(
      "href",
      "/admin/events/e1",
    );
  });

  it("renders a dash for events without a week number", async () => {
    renderPage();

    const row = (await screen.findByText("Legacy import")).closest("tr");
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it("shows an empty state when the quarter ran no events", async () => {
    retrospectiveMock.mockResolvedValue({
      ...PAYLOAD,
      totals: {
        events: 0,
        slots: 0,
        capacity: 0,
        signups: 0,
        attended: 0,
        no_shows: 0,
        attendance_rate: 0.0,
      },
      events: [],
    });
    renderPage();

    expect(
      await screen.findByText("No events ran in this quarter"),
    ).toBeInTheDocument();
    // Tiles still render (as zeros) so the page keeps its shape.
    expect(screen.getByText("Events ran")).toBeInTheDocument();
  });

  it("shows an error state with retry when the request fails", async () => {
    retrospectiveMock.mockRejectedValueOnce(new Error("boom"));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("boom");

    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(await screen.findByText("Winter 2026")).toBeInTheDocument();
  });
});
