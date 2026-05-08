import React from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../lib/api", () => ({
  api: {
    events: {
      list: vi.fn(),
    },
  },
}));

import { api } from "../../../lib/api";
import OrganizerDashboard from "../OrganizerDashboard";

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <OrganizerDashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function at(hour, minute = 0, dayOffset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + dayOffset);
  d.setHours(hour, minute, 0, 0);
  return d.toISOString();
}

describe("OrganizerDashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows today's events by default and a link to the roster", async () => {
    api.events.list.mockResolvedValue([
      {
        id: "evt-today",
        title: "Today Event",
        start_date: at(9),
        end_date: at(12),
        location: "Lab A",
      },
      {
        id: "evt-future",
        title: "Next Week",
        start_date: at(9, 0, 7),
        end_date: at(12, 0, 7),
        location: "Lab B",
      },
    ]);

    renderPage();
    await screen.findByText("Today Event");
    expect(screen.queryByText("Next Week")).toBeNull();
    const rosterLink = screen.getByRole("link", { name: /open roster/i });
    expect(rosterLink).toHaveAttribute("href", "/organizer/events/evt-today/roster");
  });

  it("switches to Upcoming tab and shows future events", async () => {
    api.events.list.mockResolvedValue([
      {
        id: "evt-today",
        title: "Today Event",
        start_date: at(9),
        end_date: at(12),
      },
      {
        id: "evt-future",
        title: "Next Week",
        start_date: at(9, 0, 7),
        end_date: at(12, 0, 7),
      },
    ]);

    renderPage();
    await screen.findByText("Today Event");
    fireEvent.click(screen.getByRole("tab", { name: /upcoming/i }));
    await waitFor(() => {
      expect(screen.getByText("Next Week")).toBeInTheDocument();
      expect(screen.queryByText("Today Event")).toBeNull();
    });
  });

  it("renders empty state when no events match the selected scope", async () => {
    api.events.list.mockResolvedValue([]);
    renderPage();
    await screen.findByText(/no events scheduled for today/i);
  });
});
