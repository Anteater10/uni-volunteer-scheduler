import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";

// Mock the checkIn API
vi.mock("../src/api/checkIn", () => ({
  getSignupEvent: vi.fn(),
  selfCheckIn: vi.fn(),
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

import SelfCheckInPage from "../src/pages/SelfCheckInPage";
import { getSignupEvent, selfCheckIn } from "../src/api/checkIn";

const MOCK_SIGNUP = {
  id: "signup-1",
  user_id: "user-1",
  slot_id: "slot-1",
  status: "confirmed",
  timestamp: "2026-04-10T10:00:00Z",
  event_id: "event-1",
  event_title: "Test Volunteer Event",
  slot_start_time: "2026-04-10T10:00:00Z",
  slot_end_time: "2026-04-10T12:00:00Z",
  answers: [],
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
      <MemoryRouter initialEntries={["/check-in/signup-1"]}>
        <Routes>
          <Route path="/check-in/:signupId" element={<SelfCheckInPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SelfCheckInPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getSignupEvent.mockResolvedValue(MOCK_SIGNUP);
  });

  it("shows form and submits successfully", async () => {
    selfCheckIn.mockResolvedValue({ status: "checked_in" });
    const user = userEvent.setup();
    renderPage();

    // Wait for the form
    await waitFor(() => {
      expect(screen.getByLabelText(/4-digit venue code/i)).toBeInTheDocument();
    });

    // Type venue code
    await user.type(screen.getByLabelText(/4-digit venue code/i), "1234");

    // Click "Check me in"
    await user.click(screen.getByRole("button", { name: /check me in/i }));

    expect(selfCheckIn).toHaveBeenCalledWith("event-1", "signup-1", "1234");

    // Should show confirmation screen with "Thanks for volunteering!"
    await waitFor(() => {
      expect(screen.getByText(/thanks for volunteering/i)).toBeInTheDocument();
    });
  });

  it("shows wrong venue code error", async () => {
    const err = new Error("Wrong venue code");
    err.status = 403;
    err.response = { status: 403, data: { code: "WRONG_VENUE_CODE" } };
    selfCheckIn.mockRejectedValue(err);

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText(/4-digit venue code/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/4-digit venue code/i), "9999");
    await user.click(screen.getByRole("button", { name: /check me in/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/not the right code/i),
      ).toBeInTheDocument();
    });
  });

  it("shows outside window error (not yet open)", async () => {
    // Page heuristic compares `new Date()` to slot.start_time to distinguish
    // "not yet open" from "closed". Use a far-future slot so the test stays
    // deterministic regardless of system clock.
    const futureStart = new Date(Date.now() + 60 * 60 * 1000).toISOString();
    const futureEnd = new Date(Date.now() + 3 * 60 * 60 * 1000).toISOString();
    getSignupEvent.mockResolvedValue({
      ...MOCK_SIGNUP,
      slot_start_time: futureStart,
      slot_end_time: futureEnd,
    });

    const err = new Error("Outside window");
    err.status = 403;
    err.response = { status: 403, data: { code: "OUTSIDE_WINDOW" } };
    selfCheckIn.mockRejectedValue(err);

    const user = userEvent.setup();
    renderPage();

    await waitFor(() => {
      expect(screen.getByLabelText(/4-digit venue code/i)).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText(/4-digit venue code/i), "1234");
    await user.click(screen.getByRole("button", { name: /check me in/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/15 minutes before/i),
      ).toBeInTheDocument();
    });
  });

  it("shows already checked in state immediately", async () => {
    getSignupEvent.mockResolvedValue({
      ...MOCK_SIGNUP,
      status: "checked_in",
      checked_in_at: "2026-04-10T10:05:00Z",
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/thanks for volunteering/i)).toBeInTheDocument();
    });

    // The form should NOT be rendered
    expect(screen.queryByLabelText(/4-digit venue code/i)).not.toBeInTheDocument();
  });
});
