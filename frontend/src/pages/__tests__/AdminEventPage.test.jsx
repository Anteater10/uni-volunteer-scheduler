// AdminEventPage.test.jsx
//
// Sweep remediation task 5: ended quarters are read-only history. The
// server rejects update_event/reopen_event against one (422
// QUARTER_READONLY), so the detail page surfaces that state instead of
// offering "Event settings" / "Reopen event" controls that would just
// 422. Duplicate is untouched — it targets a different (writable) quarter.
//
// Modal-ish subcomponents unrelated to this behavior are mocked away to
// keep this test focused on the header actions and completed-strip.

import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => {
  const apiMock = {
    admin: {
      eventAnalytics: vi.fn(async () => ({
        total_slots: 2,
        total_capacity: 20,
        confirmed_signups: 5,
        waitlisted_signups: 0,
      })),
      eventRoster: vi.fn(async () => []),
    },
    events: {
      get: vi.fn(),
    },
    public: {
      getQuarters: vi.fn(async () => []),
      getFormSchema: vi.fn(async () => ({ schema: [] })),
    },
  };
  return { api: apiMock, default: apiMock, downloadBlob: vi.fn() };
});

vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({ user: { role: "admin" } }),
}));

vi.mock("../admin/AdminLayout", () => ({
  useAdminPageTitle: vi.fn(),
}));

vi.mock("../../api/roster", () => ({
  reopenEvent: vi.fn(),
}));

vi.mock("../../components/admin/FormFieldsDrawer", () => ({
  default: () => null,
}));
vi.mock("../../components/admin/EventSettingsModal", () => ({
  default: () => null,
}));
vi.mock("../../components/admin/DuplicateEventModal", () => ({
  default: () => null,
}));
vi.mock("../../components/BroadcastModal", () => ({ default: () => null }));
vi.mock("../../components/admin/CheckInQRModal", () => ({
  default: () => null,
}));

import { api } from "../../lib/api";
import AdminEventPage from "../AdminEventPage";

function renderPage(eventId = "evt-1") {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/admin/events/${eventId}`]}>
        <Routes>
          <Route path="/admin/events/:eventId" element={<AdminEventPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ENDED_QUARTER = {
  id: "q-ended",
  display_name: "Winter 2020",
  season: "winter",
  year: 2020,
  start_date: "2020-01-06",
  end_date: "2020-03-15",
  archived_at: null,
};

const ACTIVE_QUARTER = {
  id: "q-active",
  display_name: "Current Quarter",
  season: "spring",
  year: new Date().getFullYear(),
  start_date: new Date(Date.now() - 30 * 86400e3).toISOString().slice(0, 10),
  end_date: new Date(Date.now() + 30 * 86400e3).toISOString().slice(0, 10),
  archived_at: null,
};

function baseEvent(overrides = {}) {
  return {
    id: "evt-1",
    title: "Test Event",
    location: "Room 1",
    visibility: "public",
    start_date: "2020-02-01T09:00:00Z",
    end_date: "2020-02-01T11:00:00Z",
    max_signups_per_user: null,
    created_at: "2020-01-15T00:00:00Z",
    description: "",
    completed_at: null,
    quarter_id: "q-ended",
    ...overrides,
  };
}

describe("AdminEventPage — ended-quarter read-only surfacing", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("replaces Event settings with a read-only indicator when the event's quarter has ended", async () => {
    api.public.getQuarters.mockResolvedValue([ENDED_QUARTER]);
    api.events.get.mockResolvedValue(baseEvent());

    renderPage();

    expect(await screen.findByText(/Read-only \(quarter ended\)/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /^Event settings$/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps Event settings active when the event's quarter is still active", async () => {
    api.public.getQuarters.mockResolvedValue([ACTIVE_QUARTER]);
    api.events.get.mockResolvedValue(baseEvent({ quarter_id: "q-active" }));

    renderPage();

    expect(
      await screen.findByRole("button", { name: /^Event settings$/i }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Read-only \(quarter ended\)/i)).not.toBeInTheDocument();
  });

  it("replaces Reopen event with a read-only note for a completed event in an ended quarter", async () => {
    api.public.getQuarters.mockResolvedValue([ENDED_QUARTER]);
    api.events.get.mockResolvedValue(
      baseEvent({ completed_at: "2020-02-01T12:00:00Z" }),
    );

    renderPage();

    expect(await screen.findByTestId("event-completed-strip")).toBeInTheDocument();
    expect(await screen.findByTestId("reopen-readonly-note")).toHaveTextContent(
      /Winter 2020 has ended/,
    );
    expect(
      screen.queryByRole("button", { name: /^Reopen event$/i }),
    ).not.toBeInTheDocument();
  });

  it("keeps an active Reopen event button for a completed event in an active quarter", async () => {
    api.public.getQuarters.mockResolvedValue([ACTIVE_QUARTER]);
    api.events.get.mockResolvedValue(
      baseEvent({ quarter_id: "q-active", completed_at: "2020-02-01T12:00:00Z" }),
    );

    renderPage();

    expect(
      await screen.findByRole("button", { name: /^Reopen event$/i }),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("reopen-readonly-note")).not.toBeInTheDocument();
  });
});
