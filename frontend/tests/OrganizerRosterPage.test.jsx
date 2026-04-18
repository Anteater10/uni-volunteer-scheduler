import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the roster API
vi.mock("../src/api/roster", () => ({
  fetchRoster: vi.fn(),
  checkInSignup: vi.fn(),
  resolveEvent: vi.fn(),
}));

// Mock authStorage
vi.mock("../src/lib/authStorage", () => ({
  default: {
    getToken: () => "mock-token",
    getRefreshToken: () => null,
    setToken: vi.fn(),
    setRefreshToken: vi.fn(),
    clearAll: vi.fn(),
  },
}));

import OrganizerRosterPage from "../src/pages/OrganizerRosterPage";
import { fetchRoster, checkInSignup, resolveEvent } from "../src/api/roster";

const MOCK_ROSTER = {
  event_id: "evt-1",
  event_name: "Test Event",
  venue_code: "1234",
  total: 3,
  checked_in_count: 1,
  rows: [
    {
      signup_id: "s1",
      student_name: "Alice",
      status: "confirmed",
      slot_time: "2026-04-10T10:00:00Z",
      checked_in_at: null,
    },
    {
      signup_id: "s2",
      student_name: "Bob",
      status: "checked_in",
      slot_time: "2026-04-10T10:00:00Z",
      checked_in_at: "2026-04-10T10:05:00Z",
    },
    {
      signup_id: "s3",
      student_name: "Carol",
      status: "confirmed",
      slot_time: "2026-04-10T11:00:00Z",
      checked_in_at: null,
    },
  ],
};

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/organizer/events/evt-1/roster"]}>
        <Routes>
          <Route
            path="/organizer/events/:eventId/roster"
            element={<OrganizerRosterPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OrganizerRosterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    fetchRoster.mockResolvedValue(MOCK_ROSTER);
    checkInSignup.mockResolvedValue({ status: "checked_in" });
    resolveEvent.mockResolvedValue(MOCK_ROSTER);
  });

  it("shows checked-in count in header", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText(/1 of 3 checked in/)).toBeInTheDocument();
    });
  });

  it("calls checkInSignup when clicking a confirmed row", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("Alice")).toBeInTheDocument();
    });
    // Alice's row button — find the button containing Alice
    const aliceButton = screen.getByText("Alice").closest("button");
    await user.click(aliceButton);
    expect(checkInSignup).toHaveBeenCalledWith("s1");
  });

  it("opens resolve modal with End event button", async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("End event")).toBeInTheDocument();
    });
    await user.click(screen.getByText("End event"));
    await waitFor(() => {
      // Modal should show the resolve dialog with role="dialog"
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      // Alice and Carol appear in both roster and modal, so use getAllByText
      expect(screen.getAllByText("Alice").length).toBeGreaterThanOrEqual(2);
      expect(screen.getAllByText("Carol").length).toBeGreaterThanOrEqual(2);
    });
  });

  it("polls with refetchInterval", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderPage();
    await waitFor(() => {
      expect(fetchRoster).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      vi.advanceTimersByTime(5000);
    });
    await waitFor(() => {
      expect(fetchRoster.mock.calls.length).toBeGreaterThanOrEqual(2);
    });

    vi.useRealTimers();
  });
});
