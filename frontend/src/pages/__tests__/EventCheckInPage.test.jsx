/* global process -- one test switches the machine's timezone */
// src/pages/__tests__/EventCheckInPage.test.jsx
//
// Issue #31 UX rework — pick-your-shift QR check-in: the volunteer enters
// their email, sees THEIR shifts as cards (orientation vs module, with
// window verdicts), and taps the one they're here for. Only that shift is
// checked in. The pre-email banner shows the day's schedule.
//
// Issue #189 follow-ups: the cards refresh themselves while a shift is
// upcoming, only today's units are shown, and a closed card says whether
// staff closed it or the self check-in window has passed.
//
// The clock is pinned to Thursday 2026-10-15 at noon Pacific, so "today"
// never flips under a test run near midnight.

import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../lib/api", () => {
  const api = {
    listSlots: vi.fn(),
    shifts: { list: vi.fn() },
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
const DAY = 24 * 60 * MIN;
// Thursday 15 Oct 2026, 12:00 PM Pacific.
const NOON_THU = new Date("2026-10-15T19:00:00Z");

function slotAt(offsetMs, { id, type, location, durMs = 60 * MIN, ...rest }) {
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
    shift_id: null,
    name: null,
    ...rest,
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
  offsetMs = 10 * MIN,
  staffClosed = false,
}) {
  const start = new Date(Date.now() + offsetMs);
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
    staff_closed: staffClosed,
  };
}

const lookupOf = (...shifts) => ({
  event_id: "evt-1",
  event_title: "Bio @ Lincoln",
  volunteer_name: "Thanh Khuu",
  shifts,
});

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

const setupUser = () => userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

async function submitEmail(user, email = "hungkhuu@ucsb.edu") {
  await user.type(await screen.findByLabelText("Email"), email);
  await user.click(screen.getByRole("button", { name: /find my shifts/i }));
}

async function tick(ms) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function setVisibility(state) {
  const spy = vi.spyOn(document, "visibilityState", "get").mockReturnValue(state);
  act(() => {
    document.dispatchEvent(new Event("visibilitychange", { bubbles: true }));
  });
  return spy;
}

describe("EventCheckInPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true, now: NOON_THU });
    api.public.getEvent.mockResolvedValue({ id: "evt-1", title: "Bio @ Lincoln" });
    api.listSlots.mockResolvedValue([]);
    api.shifts.list.mockResolvedValue([]);
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("shows the day's schedule with per-shift window verdicts before email entry", async () => {
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

  it("names each schedule item by date and shift / session, and hides past days", async () => {
    api.listSlots.mockResolvedValue([
      slotAt(-DAY, { id: "s-tue", type: "period", shift_id: "sh-2", name: "Tue" }),
      slotAt(5 * MIN, { id: "s-thu", type: "period", shift_id: "sh-2", name: "Thu" }),
      slotAt(60 * MIN, { id: "s-or", type: "orientation" }),
    ]);
    api.shifts.list.mockResolvedValue([{ id: "sh-2", name: "Shift 2" }]);

    renderPage();

    const box = await screen.findByTestId("checkin-window-status");
    await waitFor(() => expect(box.textContent).toMatch(/Shift 2 · Thu/));
    expect(box.textContent).toMatch(/Thu, Oct 15/);
    expect(box.textContent).toMatch(/orientation/i);
    // Tuesday's session is over and gone from the list.
    expect(box.textContent).not.toMatch(/Shift 2 · Tue/);
    expect(box.textContent).not.toMatch(/Oct 14/);
    expect(within(box).getAllByRole("listitem")).toHaveLength(2);
  });

  it("falls back to the session's own name when its shift is unknown", async () => {
    api.listSlots.mockResolvedValue([
      slotAt(5 * MIN, { id: "s-x", type: "period", shift_id: "sh-gone", name: "Period 3" }),
    ]);
    api.shifts.list.mockRejectedValue(new Error("not found"));

    renderPage();

    const box = await screen.findByTestId("checkin-window-status");
    expect(box.textContent).toMatch(/Period 3/);
  });

  it("says a staff-closed slot is closed even inside its window", async () => {
    // 2026-10-13: staff closed the session, so its attendance is locked; the
    // clock alone would still have said "Open now".
    api.listSlots.mockResolvedValue([
      {
        ...slotAt(5 * MIN, { id: "s-closed", type: "period", location: "Room 4" }),
        closed_at: new Date().toISOString(),
      },
    ]);

    renderPage();

    const box = await screen.findByTestId("checkin-window-status");
    expect(box.textContent).toMatch(/no shifts are open for check-in right now/i);
    expect(box.textContent).toMatch(/check-in closed/i);
    expect(box.textContent).not.toMatch(/open now/i);
  });

  it("lists the volunteer's shifts as cards after email lookup", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        shiftFixture({ unitId: "su-1", type: "orientation", state: "open", location: "Library" }),
        shiftFixture({ unitId: "su-2", type: "period", state: "upcoming", location: "Room 4" }),
      ),
    );

    renderPage();
    const user = setupUser();
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

  it("announces card changes politely to screen readers", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(shiftFixture({ unitId: "su-1", type: "orientation", state: "open" })),
    );

    renderPage();
    await submitEmail(setupUser());

    const card = await screen.findByTestId("shift-su-1");
    expect(card.closest("[aria-live]")).toHaveAttribute("aria-live", "polite");
  });

  it("says who closed a closed card", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        shiftFixture({ unitId: "su-1", type: "period", state: "closed", staffClosed: true }),
        shiftFixture({ unitId: "su-2", type: "period", state: "closed", offsetMs: -60 * MIN }),
      ),
    );

    renderPage();
    await submitEmail(setupUser());

    expect((await screen.findByTestId("shift-su-1")).textContent).toMatch(/closed by staff/i);
    expect(screen.getByTestId("shift-su-2").textContent).toMatch(
      /self check-in has ended — ask a staff member/i,
    );
  });

  it("shows only today's units after lookup", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        shiftFixture({ unitId: "tue", type: "period", state: "closed", offsetMs: -2 * DAY }),
        shiftFixture({ unitId: "now", type: "period", state: "open" }),
        shiftFixture({ unitId: "later", type: "period", state: "upcoming", offsetMs: 4 * 60 * MIN }),
        shiftFixture({ unitId: "next-week", type: "period", state: "upcoming", offsetMs: 7 * DAY }),
      ),
    );

    renderPage();
    await submitEmail(setupUser());

    expect(await screen.findByTestId("shift-now")).toBeInTheDocument();
    expect(screen.getByTestId("shift-later")).toBeInTheDocument();
    expect(screen.queryByTestId("shift-tue")).not.toBeInTheDocument();
    expect(screen.queryByTestId("shift-next-week")).not.toBeInTheDocument();
  });

  it("says so when none of the volunteer's shifts is today", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(shiftFixture({ unitId: "tue", type: "period", state: "closed", offsetMs: -2 * DAY })),
    );

    renderPage();
    await submitEmail(setupUser());

    expect(await screen.findByText(/no shifts today/i)).toBeInTheDocument();
  });

  it("checks in only the tapped shift and flips its card", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        shiftFixture({ unitId: "su-1", type: "orientation", state: "open", location: "Library" }),
        shiftFixture({ unitId: "su-2", type: "period", state: "open", location: "Room 4" }),
      ),
    );
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
    const user = setupUser();
    await submitEmail(user);
    // The refresh after the tap reports the server's view.
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        shiftFixture({
          unitId: "su-1", type: "orientation", state: "open", status: "checked_in",
        }),
        shiftFixture({ unitId: "su-2", type: "period", state: "open", location: "Room 4" }),
      ),
    );

    await user.click(await screen.findByTestId("shift-su-1"));

    await waitFor(() =>
      expect(api.public.checkInSelected).toHaveBeenCalledWith(
        "evt-1",
        "hungkhuu@ucsb.edu",
        ["su-1"],
        "4321",
      ),
    );
    await waitFor(() =>
      expect(screen.getByTestId("shift-su-1").textContent).toMatch(/checked in ✓/i),
    );
    // The other open shift stays untouched and tappable.
    const period = screen.getByTestId("shift-su-2");
    expect(period.textContent).toMatch(/tap to check in/i);
    expect(period).not.toBeDisabled();
  });

  it("greets with what this visit checked in, not lifetime totals", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        // Checked in earlier today (another visit): not counted.
        shiftFixture({
          unitId: "s1", type: "period", state: "open", status: "checked_in",
          shiftName: "Shift 1", offsetMs: -20 * MIN,
        }),
        shiftFixture({ unitId: "s2", type: "period", state: "open", shiftName: "Shift 2" }),
      ),
    );
    api.public.checkInSelected.mockResolvedValue({
      signups: [
        {
          unit_id: "s2", shift_name: "Shift 2", slot_type: "period",
          slot_start: new Date(Date.now() + 10 * MIN).toISOString(),
          status: "checked_in", newly_checked_in: true,
        },
      ],
    });

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    await screen.findByTestId("shift-s2");
    expect(screen.queryByText(/you're checked in for/i)).not.toBeInTheDocument();

    await user.click(screen.getByTestId("shift-s2"));

    expect(
      await screen.findByText("You're checked in for Shift 2 · Thursday."),
    ).toBeInTheDocument();
  });

  it("names a newly checked-in orientation in the greeting", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(shiftFixture({ unitId: "o1", type: "orientation", state: "open" })),
    );
    api.public.checkInSelected.mockResolvedValue({
      signups: [
        { unit_id: "o1", slot_type: "orientation", status: "checked_in", newly_checked_in: true },
        { unit_id: "o1", slot_type: "orientation", status: "checked_in", newly_checked_in: true },
        { unit_id: "o2", slot_type: "orientation", status: "checked_in", newly_checked_in: false },
      ],
    });

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    await user.click(await screen.findByTestId("shift-o1"));

    expect(await screen.findByText("You're checked in for Orientation.")).toBeInTheDocument();
  });

  it("passes the QR-carried venue code to the lookup call", async () => {
    api.public.checkInLookup.mockResolvedValue(lookupOf());

    renderPage();
    await submitEmail(setupUser());

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

  it("shows a friendly error and hides the schedule when the venue code is wrong", async () => {
    api.listSlots.mockResolvedValue([slotAt(5 * MIN, { id: "s-open", type: "orientation" })]);
    const err = new Error("Wrong venue code");
    err.code = "WRONG_VENUE_CODE";
    api.public.checkInLookup.mockRejectedValue(err);

    renderPage();
    await screen.findByTestId("checkin-window-status");
    await submitEmail(setupUser());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      /ask the organizer to re-show the QR/i,
    );
    expect(screen.queryByTestId("checkin-window-status")).not.toBeInTheDocument();
  });

  it("shows a friendly error for unknown emails", async () => {
    const err = new Error("No signup found for that email on this event");
    err.code = "NO_SIGNUP_FOR_EMAIL";
    api.public.checkInLookup.mockRejectedValue(err);

    renderPage();
    await submitEmail(setupUser(), "ghost@example.com");

    expect(
      await screen.findByText(/couldn't find a signup for that email/i),
    ).toBeInTheDocument();
  });

  it("shows the server's message for any other lookup error", async () => {
    api.public.checkInLookup.mockRejectedValue(new Error("Service unavailable"));

    renderPage();
    await submitEmail(setupUser());

    expect(await screen.findByRole("alert")).toHaveTextContent("Service unavailable");
  });

  it("prints venue (Pacific) times on a phone set to New York", async () => {
    const originalTz = process.env.TZ;
    process.env.TZ = "America/New_York";
    try {
      api.listSlots.mockResolvedValue([
        {
          id: "s-fixed",
          slot_type: "orientation",
          // 16:00Z is 9:00 AM Pacific, noon in New York.
          start_time: "2026-10-15T16:00:00Z",
          end_time: "2026-10-15T17:00:00Z",
          location: null,
        },
      ]);
      renderPage();
      const box = await screen.findByTestId("checkin-window-status");
      expect(box.textContent).toMatch(/9:00 AM – 10:00 AM/);
      expect(box.textContent).not.toMatch(/12:00 PM/);
    } finally {
      process.env.TZ = originalTz;
    }
  });

  it("ignores a blank email", async () => {
    renderPage();
    const input = await screen.findByLabelText("Email");
    fireEvent.submit(input.closest("form"));
    expect(api.public.checkInLookup).not.toHaveBeenCalled();
  });

  it("shows a failed check-in as an alert and lets someone else start over", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(shiftFixture({ unitId: "su-1", type: "orientation", state: "open" })),
    );
    api.public.checkInSelected.mockRejectedValue(
      Object.assign(new Error("Check-in failed on the server."), { code: "INVALID_TRANSITION" }),
    );

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    await user.click(await screen.findByTestId("shift-su-1"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Check-in failed on the server.");

    await user.click(screen.getByRole("button", { name: /check in someone else/i }));
    expect(await screen.findByLabelText("Email")).toHaveValue("");
    expect(screen.queryByTestId("shift-su-1")).not.toBeInTheDocument();
  });

  it("explains an out-of-date link on a tap", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(shiftFixture({ unitId: "su-1", type: "orientation", state: "open" })),
    );
    api.public.checkInSelected.mockRejectedValue(
      Object.assign(new Error("Wrong venue code"), { code: "WRONG_VENUE_CODE" }),
    );

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    await user.click(await screen.findByTestId("shift-su-1"));

    expect(await screen.findByRole("alert")).toHaveTextContent(/re-show the QR code/i);
  });

  it("falls back to a generic message when a failed tap has none", async () => {
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(shiftFixture({ unitId: "su-1", type: "orientation", state: "open" })),
    );
    api.public.checkInSelected.mockRejectedValue(new Error(""));

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    await user.click(await screen.findByTestId("shift-su-1"));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Check-in failed. Please try again.",
    );
  });

  it.each([
    ["SLOT_CLOSED", "Staff have closed check-in for this shift. Ask a staff member if you need to be checked in."],
    ["OUTSIDE_WINDOW", "That shift is not open for check-in right now"],
  ])("on %s shows the server's message and refreshes the cards", async (code, message) => {
    api.public.checkInLookup.mockResolvedValueOnce(
      lookupOf(shiftFixture({ unitId: "su-1", type: "period", state: "open" })),
    );
    api.public.checkInLookup.mockResolvedValue(
      lookupOf(
        shiftFixture({
          unitId: "su-1", type: "period", state: "closed",
          staffClosed: code === "SLOT_CLOSED", offsetMs: -45 * MIN,
        }),
      ),
    );
    api.public.checkInSelected.mockRejectedValue(Object.assign(new Error(message), { code }));

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    await user.click(await screen.findByTestId("shift-su-1"));

    expect(await screen.findByRole("alert")).toHaveTextContent(message);
    await waitFor(() => expect(api.public.checkInLookup).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByTestId("shift-su-1").textContent).toMatch(
        code === "SLOT_CLOSED" ? /closed by staff/i : /self check-in has ended/i,
      ),
    );
  });

  it("looks up again after an error when the same email is resubmitted", async () => {
    const err = new Error("No signup found for that email on this event");
    err.code = "NO_SIGNUP_FOR_EMAIL";
    api.public.checkInLookup.mockRejectedValueOnce(err).mockResolvedValue(lookupOf());

    renderPage();
    const user = setupUser();
    await submitEmail(user, "late@example.com");
    await screen.findByText(/couldn't find a signup for that email/i);

    await user.click(screen.getByRole("button", { name: /find my shifts/i }));
    expect(await screen.findByText("Thanh Khuu")).toBeInTheDocument();
    expect(api.public.checkInLookup).toHaveBeenCalledTimes(2);
  });

  it("looks up afresh when the same email comes back after 'Check in someone else'", async () => {
    api.public.checkInLookup
      .mockResolvedValueOnce(
        lookupOf(shiftFixture({ unitId: "su-1", type: "period", state: "open" })),
      )
      .mockResolvedValue(
        lookupOf(
          shiftFixture({ unitId: "su-1", type: "period", state: "open", status: "checked_in" }),
        ),
      );

    renderPage();
    const user = setupUser();
    await submitEmail(user);
    expect((await screen.findByTestId("shift-su-1")).textContent).toMatch(/tap to check in/i);

    await user.click(screen.getByRole("button", { name: /check in someone else/i }));
    await submitEmail(user);

    await waitFor(() => expect(api.public.checkInLookup).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByTestId("shift-su-1").textContent).toMatch(/checked in ✓/i),
    );
  });

  // Issue #189: the lookup used to freeze each card's window verdict, so a
  // student who scanned early stared at "Check-in opens at 9:24" forever.
  describe("auto re-lookup while a shift is upcoming", () => {
    const lookupWith = (state) =>
      lookupOf(shiftFixture({ unitId: "su-2", type: "period", state }));

    let user;
    beforeEach(() => {
      user = setupUser();
    });

    it("re-looks up every 30 seconds and the card becomes tappable", async () => {
      api.public.checkInLookup
        .mockResolvedValueOnce(lookupWith("upcoming"))
        .mockResolvedValue(lookupWith("open"));

      renderPage();
      await submitEmail(user);
      const card = await screen.findByTestId("shift-su-2");
      expect(card.textContent).toMatch(/check-in opens at/i);
      expect(card).toBeDisabled();
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(1);

      await tick(30 * 1000);

      await waitFor(() =>
        expect(screen.getByTestId("shift-su-2").textContent).toMatch(/tap to check in/i),
      );
      expect(screen.getByTestId("shift-su-2")).not.toBeDisabled();
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(2);
      expect(api.public.checkInLookup).toHaveBeenLastCalledWith(
        "evt-1",
        "hungkhuu@ucsb.edu",
        "4321",
      );

      // Nothing is upcoming any more, so the polling stops.
      await tick(90 * 1000);
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(2);
    });

    it("does not poll when no shift is upcoming", async () => {
      api.public.checkInLookup.mockResolvedValue(lookupWith("open"));

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-2");

      await tick(90 * 1000);
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(1);
    });

    it("does not poll while the page is hidden", async () => {
      api.public.checkInLookup.mockResolvedValue(lookupWith("upcoming"));

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-2");
      setVisibility("hidden");

      await tick(90 * 1000);
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(1);
    });

    it("looks up again as soon as the page comes back while a shift is upcoming", async () => {
      api.public.checkInLookup
        .mockResolvedValueOnce(lookupWith("upcoming"))
        .mockResolvedValue(lookupWith("open"));

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-2");
      setVisibility("hidden");
      await tick(10 * 1000);
      setVisibility("visible");

      await waitFor(() => expect(api.public.checkInLookup).toHaveBeenCalledTimes(2));
      await waitFor(() =>
        expect(screen.getByTestId("shift-su-2").textContent).toMatch(/tap to check in/i),
      );
    });

    it("does not look up on return when nothing is upcoming", async () => {
      api.public.checkInLookup.mockResolvedValue(lookupWith("open"));

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-2");
      setVisibility("hidden");
      setVisibility("visible");
      await tick(0);

      expect(api.public.checkInLookup).toHaveBeenCalledTimes(1);
    });

    it("keeps the cards when a background re-lookup fails", async () => {
      let rejectRefresh;
      const refresh = new Promise((_, reject) => {
        rejectRefresh = reject;
      });
      api.public.checkInLookup
        .mockResolvedValueOnce(lookupWith("upcoming"))
        .mockReturnValueOnce(refresh)
        .mockResolvedValue(lookupWith("upcoming"));

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-2");

      await tick(30 * 1000);
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(2);
      await act(async () => {
        rejectRefresh(new Error("network down"));
        await refresh.catch(() => {});
      });
      await tick(0);

      // The rejection has settled: the cards are still there, no error shows,
      // and the form has not come back.
      expect(screen.getByTestId("shift-su-2").textContent).toMatch(/check-in opens at/i);
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    });

    it("does not re-look up while a tap is in flight, then refreshes when it settles", async () => {
      api.public.checkInLookup.mockResolvedValue(
        lookupOf(
          shiftFixture({ unitId: "su-1", type: "orientation", state: "open" }),
          shiftFixture({ unitId: "su-2", type: "period", state: "upcoming" }),
        ),
      );
      let finishTap;
      api.public.checkInSelected.mockReturnValue(
        new Promise((resolve) => {
          finishTap = resolve;
        }),
      );

      renderPage();
      await submitEmail(user);
      await user.click(await screen.findByTestId("shift-su-1"));
      expect(api.public.checkInSelected).toHaveBeenCalledTimes(1);

      // A tick that would have fired mid-tap does not.
      await tick(60 * 1000);
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(1);

      await act(async () => {
        finishTap({ signups: [{ unit_id: "su-1", status: "checked_in", newly_checked_in: true }] });
      });
      await waitFor(() => expect(api.public.checkInLookup).toHaveBeenCalledTimes(2));
    });

    it("a re-lookup in flight during a tap does not undo the check-in", async () => {
      const both = (s1Status) =>
        lookupOf(
          shiftFixture({ unitId: "su-1", type: "orientation", state: "open", status: s1Status }),
          shiftFixture({ unitId: "su-2", type: "period", state: "upcoming" }),
        );
      let resolveStale;
      api.public.checkInLookup
        .mockResolvedValueOnce(both("confirmed"))
        .mockImplementationOnce(
          () => new Promise((resolve) => { resolveStale = resolve; }),
        )
        .mockResolvedValue(both("checked_in"));
      api.public.checkInSelected.mockResolvedValue({
        signups: [{ unit_id: "su-1", status: "checked_in" }],
      });

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-1");
      await tick(30 * 1000); // re-lookup starts and hangs
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(2);

      await user.click(screen.getByTestId("shift-su-1"));
      await waitFor(() =>
        expect(screen.getByTestId("shift-su-1").textContent).toMatch(/checked in ✓/i),
      );
      // The stale answer (fetched before the tap) lands afterwards.
      await act(async () => {
        resolveStale(both("confirmed"));
      });
      await tick(0);
      expect(screen.getByTestId("shift-su-1").textContent).toMatch(/checked in ✓/i);
    });

    it("stops polling after 'Check in someone else'", async () => {
      api.public.checkInLookup.mockResolvedValue(lookupWith("upcoming"));

      renderPage();
      await submitEmail(user);
      await screen.findByTestId("shift-su-2");
      await user.click(screen.getByRole("button", { name: /check in someone else/i }));
      await screen.findByLabelText("Email");

      await tick(90 * 1000);
      expect(api.public.checkInLookup).toHaveBeenCalledTimes(1);
    });
  });
});
