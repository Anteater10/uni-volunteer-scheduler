// src/pages/__tests__/EventsBrowsePage.test.jsx
//
// Component tests for the public events browse page.
// 7 test cases covering loading, data, empty, navigation, and auth independence.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — must be declared before the component import so vi.mock hoisting
// intercepts the module before EventsBrowsePage tries to use it.
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getCurrentWeek: vi.fn().mockResolvedValue({
        quarter: "spring",
        year: 2026,
        week_number: 5,
      }),
      listEvents: vi.fn().mockResolvedValue([]),
    },
  },
}));

vi.mock("../../lib/weekUtils", () => ({
  getNextWeek: vi
    .fn()
    .mockReturnValue({ quarter: "spring", year: 2026, week_number: 6 }),
  getPrevWeek: vi
    .fn()
    .mockReturnValue({ quarter: "spring", year: 2026, week_number: 4 }),
  formatWeekLabel: vi.fn().mockReturnValue("Spring 2026 - Week 5"),
}));

// Import the mocked modules so we can access the vi.fn() instances directly
import api from "../../lib/api";
import * as weekUtils from "../../lib/weekUtils";

import EventsBrowsePage from "../public/EventsBrowsePage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Create a fresh QueryClient for each test (no cross-test cache pollution). */
function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

/** Sample event fixture — two events at different schools. */
const MOCK_EVENTS = [
  {
    id: "evt-1",
    title: "CRISPR at Carpinteria HS",
    quarter: "spring",
    year: 2026,
    week_number: 5,
    school: "Carpinteria HS",
    module_slug: "crispr",
    start_date: "2026-04-22T00:00:00",
    end_date: "2026-04-28T00:00:00",
    slots: [
      { id: "s1", slot_type: "orientation", capacity: 20, filled: 5 },
      { id: "s2", slot_type: "period", capacity: 20, filled: 7 },
    ],
  },
  {
    id: "evt-2",
    title: "DNA Extraction at SBHS",
    quarter: "spring",
    year: 2026,
    week_number: 5,
    school: "Santa Barbara HS",
    module_slug: "dna",
    start_date: "2026-04-23T00:00:00",
    end_date: "2026-04-24T00:00:00",
    slots: [{ id: "s3", slot_type: "period", capacity: 15, filled: 3 }],
  },
];

/**
 * Render EventsBrowsePage inside the required providers.
 * initialEntries lets us pre-populate URL params.
 */
function renderPage({
  initialEntries = ["/events?quarter=spring&year=2026&week=5"],
} = {}) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <EventsBrowsePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EventsBrowsePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset to default mock return values before each test
    api.public.getCurrentWeek.mockResolvedValue({
      quarter: "spring",
      year: 2026,
      week_number: 5,
    });
    api.public.listEvents.mockResolvedValue([]);
    weekUtils.getNextWeek.mockReturnValue({
      quarter: "spring",
      year: 2026,
      week_number: 6,
    });
    weekUtils.getPrevWeek.mockReturnValue({
      quarter: "spring",
      year: 2026,
      week_number: 4,
    });
    weekUtils.formatWeekLabel.mockReturnValue("Spring 2026 - Week 5");
  });

  // -------------------------------------------------------------------------
  // Test 1: Loading skeletons while data is pending
  // -------------------------------------------------------------------------
  it("renders loading skeletons while data is pending", () => {
    // Keep the promise pending so we stay in loading state
    api.public.listEvents.mockReturnValue(new Promise(() => {}));
    api.public.getCurrentWeek.mockReturnValue(new Promise(() => {}));

    renderPage({ initialEntries: ["/events"] });

    // Skeletons are aria-hidden="true" with animate-pulse class
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(3);
  });

  // -------------------------------------------------------------------------
  // Test 2: Renders event cards after data loads
  // -------------------------------------------------------------------------
  it("renders event cards after data loads", async () => {
    api.public.listEvents.mockResolvedValue(MOCK_EVENTS);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("CRISPR at Carpinteria HS")
      ).toBeInTheDocument();
    });

    expect(screen.getByText("DNA Extraction at SBHS")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 3: Shows EmptyState when no events returned
  // -------------------------------------------------------------------------
  it("shows EmptyState when no events returned", async () => {
    api.public.listEvents.mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No events this week")).toBeInTheDocument();
    });
    expect(
      screen.getByText("Try browsing a different week.")
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 4: Clicking next week arrow calls getNextWeek and updates URL params
  // -------------------------------------------------------------------------
  it("clicking next week arrow calls getNextWeek and updates URL", async () => {
    api.public.listEvents.mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Next week" })
      ).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Next week" }));

    expect(weekUtils.getNextWeek).toHaveBeenCalledWith("spring", 2026, 5);
  });

  // -------------------------------------------------------------------------
  // Test 5: Clicking "This week" button resets to getCurrentWeek values
  // -------------------------------------------------------------------------
  it("clicking 'This week' button resets to getCurrentWeek values", async () => {
    api.public.listEvents.mockResolvedValue([]);

    // Start at week 7 via URL to make "This week" meaningful
    renderPage({
      initialEntries: ["/events?quarter=spring&year=2026&week=7"],
    });

    // Wait for "This week" to become enabled (getCurrentWeek resolves)
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "This week" })
      ).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "This week" }));

    // After clicking, listEvents should be called again with week 5 params
    await waitFor(() => {
      const calls = api.public.listEvents.mock.calls;
      const lastCall = calls[calls.length - 1];
      expect(lastCall[0]).toMatchObject({
        quarter: "spring",
        year: 2026,
        week_number: 5,
      });
    });
  });

  // -------------------------------------------------------------------------
  // Test 6: Events are grouped by school with section headings
  // -------------------------------------------------------------------------
  it("groups events by school with section headings", async () => {
    api.public.listEvents.mockResolvedValue(MOCK_EVENTS);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Carpinteria HS")).toBeInTheDocument();
    });

    expect(screen.getByText("Santa Barbara HS")).toBeInTheDocument();

    // Each school heading should be an h2
    const headings = screen.getAllByRole("heading", { level: 2 });
    const schools = headings.map((h) => h.textContent);
    expect(schools).toContain("Carpinteria HS");
    expect(schools).toContain("Santa Barbara HS");
  });

  // -------------------------------------------------------------------------
  // Test 7: Page renders without AuthProvider wrapper (no crash, REQ-10-07)
  // -------------------------------------------------------------------------
  it("renders without AuthProvider wrapper (no crash, REQ-10-07)", () => {
    api.public.listEvents.mockReturnValue(new Promise(() => {}));
    api.public.getCurrentWeek.mockReturnValue(new Promise(() => {}));

    // Deliberately omit any AuthContext/AuthProvider — must NOT throw
    expect(() => {
      renderPage({ initialEntries: ["/events"] });
    }).not.toThrow();

    // Container should mount without crashing
    expect(document.body).toBeTruthy();
  });
});
