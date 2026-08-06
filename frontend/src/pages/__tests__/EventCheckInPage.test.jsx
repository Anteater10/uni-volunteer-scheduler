// src/pages/__tests__/EventCheckInPage.test.jsx
//
// Issue #31 UX rework — pick-your-shift QR check-in: the volunteer enters
// their email, sees THEIR shifts as cards (orientation vs module, with
// window verdicts), and taps the one they're here for. Only that shift is
// checked in. The pre-email banner shows the whole day's schedule.

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
      checkInLookup: vi.fn(),
      checkInSelected: vi.fn(),
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

// 2026-08-02 shifts: the row the volunteer taps is a "unit" — an orientation
// signup, or one session of a shift commitment. `unit_id` is what goes back to
// the server; the page never has to know which kind it held.
function shiftFixture({
  unitId,
  type,
  state,
  status = "confirmed",
  location,
  shiftName,
  sessionName,
}) {
  const start = new Date(Date.now() + 10 * MIN);
  const isSession = type === "period";
  return {
    unit_id: unitId,
    signup_id: isSession ? null : unitId,
    shift_signup_id: isSession ? `ss-${unitId}` : null,
    shift_id: isSession ? `shift-${unitId}` : null,
    shift_name: isSession ? (shiftName ?? "Tue 1:00pm") : null,
    session_name: isSession ? (sessionName ?? "Period 1") : null,
    slot_id: isSession ? unitId : `slot-${unitId}`,
    slot_type: type,
    slot_location: location ?? null,
    slot_start: start.toISOString(),
    slot_end: new Date(start.getTime() + 60 * MIN).toISOString(),
    status,
    window_state: state,
    window_opens_at: new Date(start.getTime() - 30 * MIN).toISOString(),
  };
}

function renderPage({ entry = "/events/evt-1/check-in?v=4321" } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[entry]}>
        <Routes>
          <Route path="/events/:eventId/check-in" element={<EventCheckInPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

async function submitEmail(user, email = "hungkhuu@ucsb.edu") {
  await user.type(await screen.findByLabelText("Email"), email);
  await user.click(screen.getByRole("button", { name: /find my shifts/i }));
}

describe("EventCheckInPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue({ id: "evt-1", title: "Bio @ Lincoln" });
    api.listSlots.mockResolvedValue([]);
  });

  it("shows the whole schedule with per-shift window verdicts before email entry", async () => {
    api.listSlots.mockResolvedValue([
      slotAt(-180 * MIN, { id: "s-past", type: "orientation", location: "Library" }),
      slotAt(5 * MIN, { id: "s-open", type: "period", location: "Room 4" }),
      slotAt(180 * MIN, { id: "s-later", type: "period", location: "Room 5" }),
    ]);

    renderPage();

    const box = await screen.findByTestId("checkin-window-status");
    expect(box.textContent).toMatch(/checking in now/i);
    expect(box.textContent).toMatch(/orientation/i);
    expect(box.textContent).toMatch(/check-in closed/i);
    expect(box.textContent).toMatch(/open now/i);
    expect(box.textContent).toMatch(/opens at/i);
  });

  it("lists the volunteer's shifts as cards after email lookup", async () => {
    api.public.checkInLookup.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Bio @ Lincoln",
      volunteer_name: "Thanh Khuu",
      shifts: [
        shiftFixture({ unitId: "su-1", type: "orientation", state: "open", location: "Library" }),
        shiftFixture({ unitId: "su-2", type: "period", state: "upcoming", location: "Room 4" }),
      ],
    });

    renderPage();
    const user = userEvent.setup();
    await submitEmail(user);

    expect(await screen.findByText("Thanh Khuu")).toBeInTheDocument();
    const orient = screen.getByTestId("shift-su-1");
    const period = screen.getByTestId("shift-su-2");
    expect(orient.textContent).toMatch(/orientation/i);
    expect(orient.textContent).toMatch(/tap to check in/i);
    expect(orient).not.toBeDisabled();
    expect(period.textContent).toMatch(/module/i);
    expect(period.textContent).toMatch(/check-in opens at/i);
    expect(period).toBeDisabled();
  });

  it("checks in only the tapped shift and flips its card", async () => {
    api.public.checkInLookup.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Bio @ Lincoln",
      volunteer_name: "Thanh Khuu",
      shifts: [
        shiftFixture({ unitId: "su-1", type: "orientation", state: "open", location: "Library" }),
        shiftFixture({ unitId: "su-2", type: "period", state: "open", location: "Room 4" }),
      ],
    });
    api.public.checkInSelected.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Bio @ Lincoln",
      volunteer_name: "Thanh Khuu",
      count_checked_in: 1,
      count_already_checked_in: 0,
      signups: [
        {
          unit_id: "su-1",
          signup_id: "su-1",
          slot_id: "slot-su-1",
          slot_type: "orientation",
          status: "checked_in",
          newly_checked_in: true,
        },
      ],
    });

    renderPage();
    const user = userEvent.setup();
    await submitEmail(user);

    await user.click(await screen.findByTestId("shift-su-1"));

    await waitFor(() =>
      expect(api.public.checkInSelected).toHaveBeenCalledWith(
        "evt-1",
        "hungkhuu@ucsb.edu",
        ["su-1"],
        "4321",
      ),
    );
    const orient = screen.getByTestId("shift-su-1");
    expect(orient.textContent).toMatch(/checked in ✓/i);
    // The other open shift stays untouched and tappable.
    const period = screen.getByTestId("shift-su-2");
    expect(period.textContent).toMatch(/tap to check in/i);
    expect(period).not.toBeDisabled();
  });

  it("passes the QR-carried venue code to the lookup call", async () => {
    api.public.checkInLookup.mockResolvedValue({
      event_id: "evt-1",
      event_title: "Bio @ Lincoln",
      volunteer_name: "Thanh Khuu",
      shifts: [],
    });

    renderPage();
    const user = userEvent.setup();
    await submitEmail(user);

    await waitFor(() =>
      expect(api.public.checkInLookup).toHaveBeenCalledWith(
        "evt-1",
        "hungkhuu@ucsb.edu",
        "4321",
      ),
    );
  });

  it("blocks the flow with an invalid-link screen when the URL has no venue code", async () => {
    renderPage({ entry: "/events/evt-1/check-in" });

    expect(
      await screen.findByText(/link is missing its check-in code/i),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  });

  it("shows a friendly error when the venue code is wrong", async () => {
    const err = new Error("Wrong venue code");
    err.code = "WRONG_VENUE_CODE";
    api.public.checkInLookup.mockRejectedValue(err);

    renderPage();
    const user = userEvent.setup();
    await submitEmail(user);

    expect(
      await screen.findByText(/ask the organizer to re-show the QR/i),
    ).toBeInTheDocument();
  });

  it("shows a friendly error for unknown emails", async () => {
    const err = new Error("No signup found for that email on this event");
    err.code = "NO_SIGNUP_FOR_EMAIL";
    api.public.checkInLookup.mockRejectedValue(err);

    renderPage();
    const user = userEvent.setup();
    await submitEmail(user, "ghost@example.com");

    expect(
      await screen.findByText(/couldn't find a signup for that email/i),
    ).toBeInTheDocument();
  });
});
