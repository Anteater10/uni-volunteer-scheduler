// src/pages/__tests__/OrganizerRosterPage.checkinqr.test.jsx
//
// The check-in QR has to be reachable from an organizer's phone, not just a
// laptop. It lived only on AdminEventPage, and every /admin/* route renders
// DesktopOnlyBanner below the desktop breakpoint — so on the device an
// organizer actually brings to a school, there was no way to display the code
// volunteers scan. These cover the roster surface having it, and the QR
// carrying the venue code the public check-in endpoints gate on.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../api/roster", () => ({
  fetchRoster: vi.fn(),
  checkInSignup: vi.fn(),
  undoCheckInSignup: vi.fn(),
  checkInSession: vi.fn(),
  undoCheckInSession: vi.fn(),
  reopenEvent: vi.fn(),
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({ role: "organizer" }),
}));

import { fetchRoster } from "../../api/roster";
import OrganizerRosterPage from "../OrganizerRosterPage";

const ROSTER = {
  event_name: "Best Bread Demo Event",
  venue_code: "8951",
  total: 1,
  checked_in_count: 0,
  rows: [
    {
      signup_id: "s1",
      student_name: "Alina Rahman",
      status: "confirmed",
      slot_id: "slot-1",
      slot_type: "period",
      slot_time: "2026-09-11T15:00:00Z",
      slot_end: "2026-09-11T18:00:00Z",
      slot_location: "Room 12",
    },
  ],
};

// The QR modal's own query is gated on the :eventId route param — it builds
// the URL volunteers scan — so this has to render inside a real route rather
// than bare, or the modal renders empty.
function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/organizer/events/ev-1/roster"]}>
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

describe("OrganizerRosterPage — check-in QR", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("offers the check-in QR to an organizer", async () => {
    fetchRoster.mockResolvedValue(ROSTER);

    renderPage();

    expect(
      await screen.findByRole("button", { name: /Check-in QR/i }),
    ).toBeEnabled();
  });

  it("shows a QR carrying the event's venue code when opened", async () => {
    fetchRoster.mockResolvedValue(ROSTER);

    renderPage();
    await userEvent.click(
      await screen.findByRole("button", { name: /Check-in QR/i }),
    );

    // The venue code is the whole point: the public check-in endpoints gate on
    // ?v=, and a volunteer scanning the poster never types it.
    await waitFor(() => {
      const link = screen.getByRole("link", {
        name: /event-check-in/i,
      });
      expect(link).toHaveAttribute(
        "href",
        expect.stringContaining("?v=8951"),
      );
    });
    // Named in the modal as well as the page header, so whoever props the
    // phone up at the table can see it is the right event.
    expect(screen.getAllByText(ROSTER.event_name).length).toBeGreaterThan(1);
  });

  it("does not open the QR until asked", async () => {
    fetchRoster.mockResolvedValue(ROSTER);

    renderPage();
    await screen.findByRole("button", { name: /Check-in QR/i });

    expect(
      screen.queryByText(/Volunteers scan this code/i),
    ).not.toBeInTheDocument();
  });
});
