// src/pages/__tests__/EventCheckInPage.test.jsx
//
// Issue #31 — QR event check-in is slot-scoped: the page names which shift
// (orientation vs module) is open for check-in right now, and the result
// list labels each checked-in shift by kind.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => {
  const api = {
    listSlots: vi.fn(),
    public: {
      getEvent: vi.fn(),
      checkInByEmail: vi.fn(),
    },
  };
  return { api, default: api };
});

import { api } from "../../lib/api";
import EventCheckInPage from "../EventCheckInPage";

const MIN = 60 * 1000;

function slotAt(offsetMs, { id, type, location, durMs = 60 * MIN }) {
  const start = new Date(Date.now() + offsetMs);
  const end = new Date(start.getTime() + durMs);
  return {
    id,
    slot_type: type,
    start_time: start.toISOString(),
    end_time: end.toISOString(),
    capacity: 10,
    current_count: 1,
    location: location ?? null,
    date: start.toISOString().slice(0, 10),
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/events/evt-1/check-in"]}>
        <Routes>
          <Route path="/events/:eventId/check-in" element={<EventCheckInPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventCheckInPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue({ id: "evt-1", title: "Bio @ Lincoln" });
  });

  it("names the open shift when a slot's check-in window is live", async () => {
    // Orientation starts in 5 min (window open: -15/+30); module in 2 hours.
    api.listSlots.mockResolvedValue([
      slotAt(5 * MIN, { id: "s-orient", type: "orientation", location: "Library" }),
      slotAt(120 * MIN, { id: "s-period", type: "period", location: "Room 4" }),
    ]);

    renderPage();

    const box = await screen.findByTestId("checkin-window-status");
    expect(box.textContent).toMatch(/checking in now/i);
    expect(box.textContent).toMatch(/orientation/i);
    expect(box.textContent).toMatch(/library/i);
    // The far-off module period is NOT advertised as open.
    expect(box.textContent).not.toMatch(/room 4/i);
  });

  it("says when the next shift opens if nothing is live yet", async () => {
    api.listSlots.mockResolvedValue([
      slotAt(120 * MIN, { id: "s-period", type: "period", location: "Room 4" }),
    ]);

    renderPage();

    const box = await screen.findByTestId("checkin-window-status");
    expect(box.textContent).toMatch(/opens for check-in at/i);
    expect(box.textContent).toMatch(/module/i);
  });

  it("labels each checked-in shift by kind in the result list", async () => {
    api.listSlots.mockResolvedValue([
      slotAt(5 * MIN, { id: "s-orient", type: "orientation", location: "Library" }),
    ]);
    api.public.checkInByEmail.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Bio @ Lincoln",
      volunteer_name: "Thanh Khuu",
      count_checked_in: 1,
      count_already_checked_in: 0,
      signups: [
        {
          signup_id: "su-1",
          slot_id: "s-orient",
          slot_type: "orientation",
          slot_location: "Library",
          slot_start: new Date(Date.now() + 5 * MIN).toISOString(),
          slot_end: new Date(Date.now() + 65 * MIN).toISOString(),
          status: "checked_in",
          newly_checked_in: true,
        },
      ],
    });

    renderPage();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText("Email"), "hungkhuu@ucsb.edu");
    await user.click(screen.getByRole("button", { name: /check in/i }));

    await waitFor(() =>
      expect(api.public.checkInByEmail).toHaveBeenCalledWith(
        "evt-1",
        "hungkhuu@ucsb.edu",
      ),
    );
    expect(await screen.findByText(/checked in, thanh khuu/i)).toBeInTheDocument();
    const rows = screen.getAllByRole("listitem");
    expect(rows[0].textContent).toMatch(/orientation/i);
    expect(rows[0].textContent).toMatch(/checked_in/i);
  });
});
