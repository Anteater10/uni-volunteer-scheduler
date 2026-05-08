// src/pages/admin/__tests__/OverviewSection.test.jsx
//
// Phase 16 Plan 04 Task 1 — Overview page regression tests.
// Includes the D-19 "no UUIDs visible" gate.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../../lib/api", () => {
  const summary = vi.fn();
  const auditLogs = vi.fn();
  const api = {
    admin: {
      summary,
      auditLogs,
    },
  };
  return { api, default: api };
});

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import { api } from "../../../lib/api";
import OverviewSection from "../OverviewSection";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SUMMARY_FIXTURE = {
  users_total: 5,
  users_quarter: 2,
  events_total: 12,
  events_quarter: 4,
  slots_total: 40,
  slots_quarter: 16,
  signups_total: 88,
  signups_quarter: 22,
  signups_confirmed_total: 60,
  signups_confirmed_quarter: 18,
  this_week_events: 3,
  this_week_open_slots: 11,
  volunteer_hours_quarter: 42,
  attendance_rate_quarter: 0.85,
  week_over_week: { users: 1, events: 2, signups: -3 },
  quarter_progress: { week: 3, of: 11, pct: 0.27 },
  fill_rate_attention: [
    {
      event_id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
      title: "CRISPR at Carpinteria HS",
      start_at: "2026-04-20T16:00:00Z",
      filled: 2,
      capacity: 20,
      status: "red",
    },
    {
      event_id: "11111111-2222-3333-4444-555555555555",
      title: "DNA Extraction at SBHS",
      start_at: "2026-04-22T15:00:00Z",
      filled: 8,
      capacity: 20,
      status: "amber",
    },
  ],
  last_updated: "2026-04-15T10:30:00Z",
};

// 20 humanized activity rows — no UUIDs in any rendered field.
const ACTIVITY_FIXTURE = {
  items: Array.from({ length: 20 }, (_, i) => ({
    id: `log-${i}`,
    timestamp: new Date(Date.now() - (i + 1) * 60_000).toISOString(),
    actor_label: `Admin User ${i}`,
    actor_role: i % 2 === 0 ? "admin" : "organizer",
    action_label: "Invited a new user",
    entity_label: `New Person ${i}`,
  })),
  total: 20,
  page: 1,
  page_size: 20,
  pages: 1,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderPage() {
  return render(
    <MemoryRouter>
      <QueryClientProvider client={makeQueryClient()}>
        <OverviewSection />
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("OverviewSection", () => {
  beforeEach(() => {
    api.admin.summary.mockReset();
    api.admin.auditLogs.mockReset();
    api.admin.summary.mockResolvedValue(SUMMARY_FIXTURE);
    api.admin.auditLogs.mockResolvedValue(ACTIVITY_FIXTURE);
  });

  it("renders the 5 StatCards with plain-English explainers", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/people can sign into this admin panel/i),
      ).toBeInTheDocument(),
    );
    expect(
      screen.getByText(/scheduled activities students can sign up for/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/time slots available across all events/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/students have signed up \(all time\)/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/confirmed \(ready to check in or done\)/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/This quarter:/i).length).toBeGreaterThanOrEqual(5);
  });

  it("renders quarter progress bar, hours headline, attendance, this-week, and footer", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/Week 3 of 11/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/through the quarter/i)).toBeInTheDocument();
    expect(screen.getByText(/Hours this quarter/i)).toBeInTheDocument();
    expect(screen.getByText("42")).toBeInTheDocument();
    expect(screen.getByText(/Attendance rate this quarter/i)).toBeInTheDocument();
    expect(screen.getByText("85%")).toBeInTheDocument();
    expect(screen.getByText(/This week/i)).toBeInTheDocument();
    expect(screen.getByText(/3 events in the next 7 days/i)).toBeInTheDocument();
    expect(screen.getByText(/Last updated/i)).toBeInTheDocument();
  });

  it("renders the fill-rate attention list with colored badges and event titles", async () => {
    renderPage();
    await waitFor(() =>
      expect(
        screen.getByText("CRISPR at Carpinteria HS"),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("DNA Extraction at SBHS")).toBeInTheDocument();
    expect(screen.getByText("2/20")).toBeInTheDocument();
    expect(screen.getByText("8/20")).toBeInTheDocument();
  });

  it("renders the recent activity feed with role badges and action labels (no UUIDs)", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText(/Recent activity/i)).toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByText("Admin User 0")).toBeInTheDocument(),
    );
    expect(
      screen.getAllByText("Invited a new user").length,
    ).toBeGreaterThanOrEqual(20);
  });

  it("D-19 gate: no UUIDs anywhere in rendered text", async () => {
    const { container } = renderPage();
    await waitFor(() =>
      expect(
        screen.getByText(/people can sign into this admin panel/i),
      ).toBeInTheDocument(),
    );
    const text = container.textContent || "";
    const uuidRe = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i;
    expect(uuidRe.test(text)).toBe(false);
  });

  it("requests exactly 20 activity rows", async () => {
    renderPage();
    await waitFor(() => expect(api.admin.auditLogs).toHaveBeenCalled());
    const firstCallArg = api.admin.auditLogs.mock.calls[0][0];
    expect(firstCallArg).toEqual(expect.objectContaining({ limit: 20 }));
  });
});
