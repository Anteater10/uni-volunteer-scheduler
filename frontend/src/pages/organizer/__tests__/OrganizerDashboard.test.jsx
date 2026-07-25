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

  it("keeps a today event that already ended out of Past and Upcoming", async () => {
    // Freeze only Date (real timers stay live so RTL polling works): noon,
    // so a morning event has already ended but is still "today".
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date(2030, 5, 15, 12, 0, 0));
    try {
      api.events.list.mockResolvedValue([
        {
          id: "evt-today-done",
          title: "Morning Event",
          start_date: at(8),
          end_date: at(10),
        },
        {
          id: "evt-old",
          title: "Last Week Event",
          start_date: at(9, 0, -7),
          end_date: at(12, 0, -7),
        },
      ]);

      renderPage();
      // Today owns the whole day — the ended morning event still shows here.
      await screen.findByText("Morning Event");

      fireEvent.click(screen.getByRole("tab", { name: /past/i }));
      await waitFor(() => {
        expect(screen.getByText("Last Week Event")).toBeInTheDocument();
        expect(screen.queryByText("Morning Event")).toBeNull();
      });

      fireEvent.click(screen.getByRole("tab", { name: /upcoming/i }));
      await waitFor(() => {
        expect(screen.queryByText("Morning Event")).toBeNull();
      });
    } finally {
      vi.useRealTimers();
    }
  });

  it("controlled embedded mode uses the scope prop and hides its own header/tabs", async () => {
    api.events.list.mockResolvedValue([
      {
        id: "evt-today",
        title: "Today Event",
        start_date: at(9),
        end_date: at(23),
      },
      {
        id: "evt-future",
        title: "Next Week",
        start_date: at(9, 0, 7),
        end_date: at(12, 0, 7),
      },
    ]);

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter>
          <OrganizerDashboard embedded scope="upcoming" />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Next Week");
    expect(screen.queryByText("Today Event")).toBeNull();
    // Host (Operations page) owns the header and the tab bar.
    expect(screen.queryByRole("tablist", { name: /event scope/i })).toBeNull();
    expect(
      screen.queryByRole("heading", { name: /organizer/i }),
    ).toBeNull();
  });
});
