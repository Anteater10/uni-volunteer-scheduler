// src/pages/__tests__/EventsBrowsePage.test.jsx
//
// Component tests for the public events browse page — issue #24 rewrite.
// Navigation is quarter_id-driven over the admin-entered quarter rows;
// legacy ?quarter=&year=&week= links canonicalize; gap and unconfigured
// states render dedicated UI.

import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getCurrentWeek: vi.fn(),
      getQuarters: vi.fn(),
      listEvents: vi.fn().mockResolvedValue([]),
    },
  },
}));

import api from "../../lib/api";

import EventsBrowsePage from "../public/EventsBrowsePage";

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

const SPRING = {
  id: "spring-26",
  season: "spring",
  year: 2026,
  label: "",
  start_date: "2026-03-30",
  end_date: "2026-06-14",
  weeks_in_quarter: 11,
  display_name: "Spring 2026",
  archived_at: null,
};
const SESSION_A = {
  id: "summer-26-a",
  season: "summer",
  year: 2026,
  label: "Session A",
  start_date: "2026-06-22",
  end_date: "2026-07-31",
  weeks_in_quarter: 6,
  display_name: "Summer 2026 · Session A",
  archived_at: null,
};
const QUARTERS = [SPRING, SESSION_A];

const CURRENT_WEEK = {
  configured: true,
  quarter: "spring",
  year: 2026,
  week_number: 5,
  quarter_id: "spring-26",
  label: "",
  weeks_in_quarter: 11,
  is_gap: false,
  starts_on: null,
};

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
];

function renderPage({ initialEntries = ["/events"] } = {}) {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <EventsBrowsePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventsBrowsePage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getCurrentWeek.mockResolvedValue({ ...CURRENT_WEEK });
    api.public.getQuarters.mockResolvedValue(QUARTERS);
    api.public.listEvents.mockResolvedValue([]);
  });

  it("renders loading skeletons while data is pending", () => {
    api.public.listEvents.mockReturnValue(new Promise(() => {}));
    api.public.getCurrentWeek.mockReturnValue(new Promise(() => {}));
    api.public.getQuarters.mockReturnValue(new Promise(() => {}));

    renderPage();

    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThanOrEqual(3);
  });

  it("defaults to the current week and fetches events by quarter_id", async () => {
    api.public.listEvents.mockResolvedValue(MOCK_EVENTS);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("CRISPR at Carpinteria HS")).toBeInTheDocument();
    });
    expect(screen.getByText("Spring 2026 — Week 5")).toBeInTheDocument();
    expect(api.public.listEvents).toHaveBeenCalledWith({
      quarter_id: "spring-26",
      week_number: 5,
    });
  });

  it("shows EmptyState when no events returned", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Nothing scheduled this week")).toBeInTheDocument();
    });
  });

  it("next arrow advances one week within the quarter", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Next week" })).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole("button", { name: "Next week" }));

    await waitFor(() => {
      expect(api.public.listEvents).toHaveBeenCalledWith({
        quarter_id: "spring-26",
        week_number: 6,
      });
    });
  });

  it("canonicalizes legacy quarter/year/week URL params onto quarter_id", async () => {
    renderPage({ initialEntries: ["/events?quarter=summer&year=2026&week=2"] });

    await waitFor(() => {
      expect(api.public.listEvents).toHaveBeenCalledWith({
        quarter_id: "summer-26-a",
        week_number: 2,
      });
    });
    expect(await screen.findByText("Summer 2026 · Session A — Week 2")).toBeInTheDocument();
  });

  it("disables the next arrow at the last entered week", async () => {
    renderPage({ initialEntries: ["/events?quarter_id=summer-26-a&week=6"] });

    await waitFor(() => {
      expect(screen.getByText("Summer 2026 · Session A — Week 6")).toBeInTheDocument();
    });
    expect(screen.getByRole("button", { name: "Next week" })).toBeDisabled();
  });

  it("shows the gap banner pointing at the next quarter", async () => {
    api.public.getCurrentWeek.mockResolvedValue({
      configured: true,
      quarter: "summer",
      year: 2026,
      week_number: 1,
      quarter_id: "summer-26-a",
      label: "Session A",
      weeks_in_quarter: 6,
      is_gap: true,
      starts_on: "2026-06-22",
    });

    renderPage();

    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(/Summer 2026 · Session A/);
    expect(banner).toHaveTextContent(/starts June 22/);
  });

  // ---- issue #33: archived quarters ----

  const ARCHIVED_WINTER = {
    id: "winter-26",
    season: "winter",
    year: 2026,
    label: "",
    start_date: "2026-01-05",
    end_date: "2026-03-20",
    weeks_in_quarter: 11,
    display_name: "Winter 2026",
    archived_at: "2026-07-01T00:00:00Z",
  };

  it("lists archived quarters and navigates into week 1 on click", async () => {
    api.public.getQuarters.mockResolvedValue([ARCHIVED_WINTER, ...QUARTERS]);

    renderPage();

    fireEvent.click(await screen.findByText(/archived quarters/i));
    fireEvent.click(await screen.findByRole("button", { name: /winter 2026/i }));

    await waitFor(() => {
      expect(api.public.listEvents).toHaveBeenCalledWith({
        quarter_id: "winter-26",
        week_number: 1,
      });
    });
  });

  it("hides the archived list when nothing is archived", async () => {
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Nothing scheduled this week")).toBeInTheDocument();
    });
    expect(screen.queryByText(/archived quarters/i)).toBeNull();
  });

  it("deep link into an archived quarter shows the banner and clamps nav", async () => {
    api.public.getQuarters.mockResolvedValue([ARCHIVED_WINTER, ...QUARTERS]);

    renderPage({ initialEntries: ["/events?quarter_id=winter-26&week=1"] });

    expect(await screen.findByText("Winter 2026 — Week 1")).toBeInTheDocument();
    const banner = await screen.findByRole("status");
    expect(banner).toHaveTextContent(/archived/i);
    expect(banner).toHaveTextContent(/Winter 2026/);

    // Week 1 of 11: prev clamps (archived nav never leaves the quarter),
    // next moves within it.
    expect(screen.getByRole("button", { name: "Previous week" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Next week" })).not.toBeDisabled();
  });

  it("renders the coming-soon state when no quarters are configured", async () => {
    api.public.getCurrentWeek.mockResolvedValue({
      configured: false,
      quarter: null,
      year: null,
      week_number: null,
      quarter_id: null,
      label: "",
      weeks_in_quarter: null,
      is_gap: false,
      starts_on: null,
    });
    api.public.getQuarters.mockResolvedValue([]);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/schedule coming soon/i)).toBeInTheDocument();
    });
    expect(api.public.listEvents).not.toHaveBeenCalled();
  });
});

// K22 — the destination "show me orientation events" now sends people to.
// Before this filter existed the button had nowhere honest to go: the modal
// that offers it only renders on events with no orientation slots, so
// highlighting orientation slots in place highlighted nothing.
describe("EventsBrowsePage — ?only=orientation (K22)", () => {
  const ORIENTATION_EVENT = {
    ...MOCK_EVENTS[0],
    id: "evt-orient",
    title: "Orientation at Adams",
    school: "Adams Elementary",
    slots: [{ id: "o1", slot_type: "orientation", capacity: 20, filled: 2 }],
  };
  const PERIOD_ONLY_EVENT = {
    ...MOCK_EVENTS[0],
    id: "evt-period",
    title: "Rockets at Brandon",
    school: "Brandon Middle",
    slots: [{ id: "p1", slot_type: "period", capacity: 20, filled: 3 }],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getCurrentWeek.mockResolvedValue({ ...CURRENT_WEEK });
    api.public.getQuarters.mockResolvedValue(QUARTERS);
    api.public.listEvents.mockResolvedValue([
      ORIENTATION_EVENT,
      PERIOD_ONLY_EVENT,
    ]);
  });

  it("hides events with no orientation session", async () => {
    renderPage({ initialEntries: ["/volunteer?only=orientation"] });

    expect(await screen.findByText("Orientation at Adams")).toBeInTheDocument();
    expect(screen.queryByText("Rockets at Brandon")).toBeNull();
  });

  it("says the list is filtered rather than looking like the whole week", async () => {
    renderPage({ initialEntries: ["/volunteer?only=orientation"] });

    await screen.findByText("Orientation at Adams");
    expect(
      screen.getByText(/only events with an orientation session/i),
    ).toBeInTheDocument();
  });

  it("can be cleared back to the full week", async () => {
    renderPage({ initialEntries: ["/volunteer?only=orientation"] });
    await screen.findByText("Orientation at Adams");

    fireEvent.click(screen.getByRole("button", { name: /show everything/i }));

    expect(await screen.findByText("Rockets at Brandon")).toBeInTheDocument();
    expect(screen.queryByText(/only events with an orientation session/i)).toBeNull();
  });

  it("doesn't claim nothing is scheduled when the filter is what emptied it", async () => {
    api.public.listEvents.mockResolvedValue([PERIOD_ONLY_EVENT]);
    renderPage({ initialEntries: ["/volunteer?only=orientation"] });

    expect(
      await screen.findByText(/no orientation sessions this week/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/nothing scheduled this week/i)).toBeNull();
  });

  it("shows everything when the param is absent", async () => {
    renderPage({ initialEntries: ["/volunteer"] });

    expect(await screen.findByText("Rockets at Brandon")).toBeInTheDocument();
    expect(screen.getByText("Orientation at Adams")).toBeInTheDocument();
    expect(screen.queryByText(/only events with an orientation session/i)).toBeNull();
  });
});
