// QuarterSelectionContext.test.jsx — fix/ux-quarter-batch
//
// The admin-wide quarter selection: defaults to the quarter covering today,
// follows an explicit pick (persisted to localStorage), and degrades to an
// inert fallback outside the provider so bare-page tests keep working.

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => {
  const apiObj = { public: { getQuarters: vi.fn() } };
  return { api: apiObj, default: apiObj };
});

import api from "../../lib/api";
import {
  QuarterSelectionProvider,
  useSelectedQuarter,
  ALL_QUARTERS,
} from "../QuarterSelectionContext";

const today = new Date();
const iso = (d) => d.toISOString().slice(0, 10);
const daysFromNow = (n) => iso(new Date(Date.now() + n * 86400e3));

const PAST_Q = {
  id: "q-past",
  display_name: "Winter 2026",
  start_date: daysFromNow(-200),
  end_date: daysFromNow(-130),
  archived_at: "2026-04-01T00:00:00Z",
};
const CURRENT_Q = {
  id: "q-current",
  display_name: "Summer 2026",
  start_date: daysFromNow(-10),
  end_date: daysFromNow(60),
  archived_at: null,
};

function Probe() {
  const {
    selectedQuarter,
    isExplicitSelection,
    isViewingCurrent,
    viewingAll,
    setSelectedQuarterId,
  } = useSelectedQuarter();
  return (
    <div>
      <p data-testid="selected">{selectedQuarter?.display_name || "none"}</p>
      <p data-testid="explicit">{String(isExplicitSelection)}</p>
      <p data-testid="current">{String(isViewingCurrent)}</p>
      <p data-testid="all">{String(viewingAll)}</p>
      <button onClick={() => setSelectedQuarterId("q-past")}>pick past</button>
      <button onClick={() => setSelectedQuarterId(ALL_QUARTERS)}>pick all</button>
      <button onClick={() => setSelectedQuarterId(null)}>reset</button>
    </div>
  );
}

function renderWithProvider() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <QuarterSelectionProvider>
        <Probe />
      </QuarterSelectionProvider>
    </QueryClientProvider>,
  );
}

describe("QuarterSelectionContext", () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
    api.public.getQuarters.mockResolvedValue([PAST_Q, CURRENT_Q]);
  });

  it("defaults to the quarter covering today, marked as current", async () => {
    renderWithProvider();
    expect(await screen.findByText("Summer 2026")).toBeInTheDocument();
    expect(screen.getByTestId("explicit")).toHaveTextContent("false");
    expect(screen.getByTestId("current")).toHaveTextContent("true");
  });

  it("follows an explicit pick, persists it, and can reset to current", async () => {
    renderWithProvider();
    await screen.findByText("Summer 2026");

    fireEvent.click(screen.getByText("pick past"));
    expect(screen.getByTestId("selected")).toHaveTextContent("Winter 2026");
    expect(screen.getByTestId("explicit")).toHaveTextContent("true");
    expect(screen.getByTestId("current")).toHaveTextContent("false");
    expect(window.localStorage.getItem("admin.selectedQuarterId")).toBe("q-past");

    fireEvent.click(screen.getByText("reset"));
    expect(screen.getByTestId("selected")).toHaveTextContent("Summer 2026");
    expect(window.localStorage.getItem("admin.selectedQuarterId")).toBeNull();
  });

  it("supports the all-quarters sentinel without losing the stats fallback", async () => {
    renderWithProvider();
    await screen.findByText("Summer 2026");
    fireEvent.click(screen.getByText("pick all"));
    expect(screen.getByTestId("all")).toHaveTextContent("true");
    // Stats still have a quarter to describe (the current one).
    expect(screen.getByTestId("selected")).toHaveTextContent("Summer 2026");
    expect(screen.getByTestId("explicit")).toHaveTextContent("false");
  });

  it("falls back to a stale stored id gracefully", async () => {
    window.localStorage.setItem("admin.selectedQuarterId", "q-deleted");
    renderWithProvider();
    // Unknown id → follow the current quarter instead of an empty screen.
    expect(await screen.findByText("Summer 2026")).toBeInTheDocument();
    expect(screen.getByTestId("explicit")).toHaveTextContent("false");
  });

  it("returns the inert fallback outside the provider", () => {
    render(<Probe />);
    expect(screen.getByTestId("selected")).toHaveTextContent("none");
    expect(screen.getByTestId("all")).toHaveTextContent("false");
  });
});
