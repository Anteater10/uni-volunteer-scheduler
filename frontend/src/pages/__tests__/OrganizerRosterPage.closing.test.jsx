// src/pages/__tests__/OrganizerRosterPage.closing.test.jsx
//
// 2026-10-13 (Kim's report) — attendance lives on the slot.
//
// While a slot is open a seated volunteer is either "checked in" or "not
// checked in" (pending and confirmed look identical), and tapping toggles
// between the two. Closing a slot is the only thing that produces attended /
// no show, it only happens when a person presses End, and it can always be
// undone with Reopen. A tap that lands on a slot someone closed in the
// meantime gets a clear message and the roster refetches.
//
// This file also covers the page's supporting surfaces (loading state, the
// quick-add question modal, broadcast and QR modals) so the page is fully
// exercised.

import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
// Imported rather than taken from vitest's globals so this file lints clean.
import { beforeEach, describe, expect, it, vi } from "vitest";

const authState = vi.hoisted(() => ({ role: "organizer" }));

// The real SLOT_CLOSED check, so these tests exercise the actual error shape.
vi.mock("../../api/roster", async (importOriginal) => ({
  isSlotClosedError: (await importOriginal()).isSlotClosedError,
  isSlotNotStartedError: (await importOriginal()).isSlotNotStartedError,
  fetchRoster: vi.fn(),
  checkInSignup: vi.fn(),
  undoCheckInSignup: vi.fn(),
  checkInSession: vi.fn(),
  undoCheckInSession: vi.fn(),
  reopenEvent: vi.fn(),
  reopenSlot: vi.fn(),
  resolveSlot: vi.fn(),
}));

vi.mock("../../lib/api", () => ({
  default: { organizer: { appendEventField: vi.fn() } },
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({ role: authState.role }),
}));

vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

// The broadcast and QR modals have their own tests; here they only need to
// open and close.
vi.mock("../../components/BroadcastModal", () => ({
  default: ({ open, onClose }) =>
    open ? (
      <div data-testid="broadcast-modal">
        <button type="button" onClick={onClose}>
          close broadcast
        </button>
      </div>
    ) : null,
}));

vi.mock("../../components/admin/CheckInQRModal", () => ({
  default: ({ open, onClose, eventTitle }) =>
    open ? (
      <div data-testid="qr-modal">
        {eventTitle}
        <button type="button" onClick={onClose}>
          close qr
        </button>
      </div>
    ) : null,
}));

import {
  fetchRoster,
  checkInSignup,
  undoCheckInSignup,
  reopenEvent,
  reopenSlot,
  resolveSlot,
} from "../../api/roster";
import api from "../../lib/api";
import { toast } from "../../state/toast";
import OrganizerRosterPage from "../OrganizerRosterPage";

const SLOT_CLOSED_MESSAGE =
  "This slot is closed — reopen it to change attendance.";

const PAST = "2020-01-06T17:00:00Z";
const PAST_END = "2020-01-06T18:30:00Z";
const FUTURE = "2099-01-08T17:00:00Z";
const CLOSED_AT = "2020-01-06T19:00:00Z";

const OPEN_SLOT = {
  slot_id: "slot-open",
  slot_type: "period",
  slot_time: PAST,
  slot_end: PAST_END,
  slot_location: "Room 12",
  slot_closed_at: null,
};

const CLOSED_SLOT = {
  ...OPEN_SLOT,
  slot_id: "slot-closed",
  slot_type: "orientation",
  slot_closed_at: CLOSED_AT,
};

function row(slot, signup_id, student_name, status, extra = {}) {
  return { ...slot, signup_id, student_name, status, ...extra };
}

function roster(rows, extra = {}) {
  return {
    event_id: "ev-1",
    event_name: "Adams Elementary",
    venue_code: "4321",
    total: rows.length,
    checked_in_count: rows.filter((r) => r.status === "checked_in").length,
    rows,
    ...extra,
  };
}

function slotClosedError() {
  const err = new Error("This slot is closed. Reopen it to change attendance.");
  err.status = 409;
  // The real body: main.py's global handler flattens every HTTPException to
  // {error, code, detail: "<message>"}, so the code is top-level.
  err.response = {
    status: 409,
    data: {
      error: "http_409",
      code: "SLOT_CLOSED",
      detail: "This slot is closed. Reopen it to change attendance.",
    },
  };
  return err;
}

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

const card = (name) => screen.getByText(name).closest("button");
const chipOf = (name) => card(name).querySelector("span.rounded-full");

beforeEach(() => {
  vi.clearAllMocks();
  authState.role = "organizer";
  checkInSignup.mockResolvedValue({});
  undoCheckInSignup.mockResolvedValue({});
  resolveSlot.mockResolvedValue({});
});

describe("open slot: checked in / not checked in", () => {
  it("renders pending and confirmed identically as not checked in", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(OPEN_SLOT, "s1", "Parker Pending", "pending"),
        row(OPEN_SLOT, "s2", "Carla Confirmed", "confirmed"),
      ]),
    );
    renderPage();
    await screen.findByText("Parker Pending");

    expect(chipOf("Parker Pending")).toHaveTextContent("not checked in");
    expect(chipOf("Carla Confirmed")).toHaveTextContent("not checked in");
    expect(chipOf("Parker Pending").className).toBe(
      chipOf("Carla Confirmed").className,
    );
    expect(card("Parker Pending").className).toBe(card("Carla Confirmed").className);
    expect(card("Parker Pending")).toBeEnabled();
    expect(card("Carla Confirmed")).toBeEnabled();
    expect(screen.queryByText("pending")).not.toBeInTheDocument();
    expect(screen.queryByText("confirmed")).not.toBeInTheDocument();
    // Open slot header: live tally and End.
    expect(screen.getByText("0/2 checked in")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^End slot\b/ })).toBeEnabled();
  });

  it("keeps waitlisted and cancelled cards disabled", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(OPEN_SLOT, "s1", "Wanda Waitlist", "waitlisted"),
        row(OPEN_SLOT, "s2", "Cody Cancelled", "cancelled"),
      ]),
    );
    renderPage();
    await screen.findByText("Wanda Waitlist");

    expect(card("Wanda Waitlist")).toBeDisabled();
    expect(card("Cody Cancelled")).toBeDisabled();
    expect(chipOf("Wanda Waitlist")).toHaveTextContent("waitlisted");
    expect(chipOf("Cody Cancelled")).toHaveTextContent("cancelled");
    // They don't count toward the slot.
    expect(screen.getByText("0/0 checked in")).toBeInTheDocument();
  });

  it("taps a pending volunteer in, optimistically", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Parker Pending", "pending")]),
    );
    checkInSignup.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Parker Pending");

    await user.click(card("Parker Pending"));

    expect(checkInSignup).toHaveBeenCalledWith("s1");
    await waitFor(() =>
      expect(chipOf("Parker Pending")).toHaveTextContent(/^checked in$/),
    );
    // While a tap is in flight, cards don't take another.
    expect(card("Parker Pending")).toBeDisabled();
  });

  it("taps a checked-in volunteer back to not checked in", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Ivy In", "checked_in")]),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ivy In");

    expect(chipOf("Ivy In")).toHaveTextContent(/^checked in$/);
    expect(within(card("Ivy In")).getByText(/tap again to undo/)).toBeInTheDocument();
    expect(screen.getByText("1/1 checked in")).toBeInTheDocument();

    await user.click(card("Ivy In"));

    await waitFor(() => expect(undoCheckInSignup).toHaveBeenCalledWith("s1"));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith("Check-in undone."));
  });

  it("rolls a failed check-in back and says to retry", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Carla Confirmed", "confirmed")]),
    );
    checkInSignup.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Carla Confirmed");

    await user.click(card("Carla Confirmed"));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Check-in failed. Please retry."),
    );
    await waitFor(() =>
      expect(chipOf("Carla Confirmed")).toHaveTextContent("not checked in"),
    );
  });

  it("rolls a failed undo back and says to retry", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Ivy In", "checked_in")]),
    );
    undoCheckInSignup.mockRejectedValue(new Error("boom"));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ivy In");

    await user.click(card("Ivy In"));

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Undo failed. Please retry."),
    );
    await waitFor(() => expect(chipOf("Ivy In")).toHaveTextContent(/^checked in$/));
  });

  it("explains SLOT_CLOSED on a check-in tap and refetches", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Carla Confirmed", "confirmed")]),
    );
    checkInSignup.mockRejectedValue(slotClosedError());
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Carla Confirmed");
    const callsBefore = fetchRoster.mock.calls.length;

    // Someone closed the slot on another phone; the refetch shows it.
    fetchRoster.mockResolvedValue(
      roster([row({ ...OPEN_SLOT, slot_closed_at: CLOSED_AT }, "s1", "Carla Confirmed", "no_show")]),
    );
    await user.click(card("Carla Confirmed"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(SLOT_CLOSED_MESSAGE));
    await waitFor(() =>
      expect(fetchRoster.mock.calls.length).toBeGreaterThan(callsBefore),
    );
    expect(await screen.findByText("Closed")).toBeInTheDocument();
    expect(chipOf("Carla Confirmed")).toHaveTextContent("no show");
    expect(card("Carla Confirmed")).toBeDisabled();
  });

  it("explains SLOT_CLOSED on an undo tap too", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Ivy In", "checked_in")]),
    );
    undoCheckInSignup.mockRejectedValue(slotClosedError());
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ivy In");

    await user.click(card("Ivy In"));

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(SLOT_CLOSED_MESSAGE));
  });

  it("leaves an unknown status on an open slot readable but untappable", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s2", "Odd Status", "mystery_state")]),
    );
    renderPage();
    await screen.findByText("Odd Status");

    expect(chipOf("Odd Status")).toHaveTextContent("mystery state");
    expect(card("Odd Status")).toBeDisabled();
  });

  // Issue #189: attended / no show only mean something on a closed slot. A
  // stray one left on an open slot (old "End event" data) must not block
  // staff, because the QR page sends the volunteer to them to fix it.
  it("shows a stray no-show on an open slot as not checked in, and a tap checks it in", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Stray NoShow", "no_show")]),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Stray NoShow");

    expect(chipOf("Stray NoShow")).toHaveTextContent("not checked in");
    expect(screen.getByText("0/1 checked in")).toBeInTheDocument();
    expect(card("Stray NoShow")).toBeEnabled();

    await user.click(card("Stray NoShow"));
    expect(checkInSignup).toHaveBeenCalledWith("s1");
    expect(undoCheckInSignup).not.toHaveBeenCalled();
  });

  it("shows a stray attended on an open slot as checked in, and a tap undoes it", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Stray Attended", "attended")]),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Stray Attended");

    expect(chipOf("Stray Attended")).toHaveTextContent(/^checked in$/);
    expect(within(card("Stray Attended")).getByText(/tap again to undo/)).toBeInTheDocument();
    expect(screen.getByText("1/1 checked in")).toBeInTheDocument();

    await user.click(card("Stray Attended"));
    await waitFor(() => expect(undoCheckInSignup).toHaveBeenCalledWith("s1"));
    expect(checkInSignup).not.toHaveBeenCalled();
  });
});

describe("closed slot", () => {
  it("is read-only with attended / no show chips and a Reopen button", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(CLOSED_SLOT, "s1", "Ada Attended", "attended"),
        row(CLOSED_SLOT, "s2", "Ned NoShow", "no_show"),
        // A stray check-in on a closed slot can't be tapped either.
        row(CLOSED_SLOT, "s3", "Stray In", "checked_in"),
      ]),
    );
    renderPage();
    await screen.findByText("Ada Attended");

    expect(screen.getByText("Closed")).toBeInTheDocument();
    expect(screen.getByText("1 attended · 1 no show")).toBeInTheDocument();
    expect(chipOf("Ada Attended")).toHaveTextContent("attended");
    expect(chipOf("Ned NoShow")).toHaveTextContent("no show");
    for (const name of ["Ada Attended", "Ned NoShow", "Stray In"]) {
      expect(card(name)).toBeDisabled();
    }
    for (const name of ["Ada Attended", "Ned NoShow", "Stray In"]) {
      expect(within(card(name)).queryByText(/tap again to undo/)).not.toBeInTheDocument();
    }
    expect(
      screen.getByRole("button", { name: /^Reopen orientation\b/ }),
    ).toBeEnabled();
  });

  it("reopens a slot through the API and shows the fresh roster", async () => {
    fetchRoster.mockResolvedValue(
      roster([row({ ...CLOSED_SLOT, slot_type: "period" }, "s1", "Ada Attended", "attended")]),
    );
    const reopened = roster([
      row({ ...CLOSED_SLOT, slot_type: "period", slot_closed_at: null }, "s1", "Ada Attended", "checked_in"),
    ]);
    reopenSlot.mockResolvedValue(reopened);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ada Attended");

    fetchRoster.mockResolvedValue(reopened);
    await user.click(screen.getByRole("button", { name: /^Reopen slot\b/ }));

    expect(reopenSlot).toHaveBeenCalledWith("slot-closed");
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        expect.stringMatching(/^Slot reopened/),
      ),
    );
    expect(await screen.findByRole("button", { name: /^End slot\b/ })).toBeEnabled();
    expect(screen.queryByText("Closed")).not.toBeInTheDocument();
    expect(chipOf("Ada Attended")).toHaveTextContent(/^checked in$/);
    expect(card("Ada Attended")).toBeEnabled();
  });

  it("still refetches when reopen returns no body", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(CLOSED_SLOT, "s1", "Ada Attended", "attended")]),
    );
    reopenSlot.mockResolvedValue(null);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ada Attended");
    const callsBefore = fetchRoster.mock.calls.length;

    await user.click(screen.getByRole("button", { name: /^Reopen orientation\b/ }));

    await waitFor(() =>
      expect(fetchRoster.mock.calls.length).toBeGreaterThan(callsBefore),
    );
  });

  it("reports a failed reopen", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(CLOSED_SLOT, "s1", "Ada Attended", "attended")]),
    );
    reopenSlot.mockRejectedValueOnce(new Error("Quarter has ended"));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ada Attended");

    await user.click(screen.getByRole("button", { name: /^Reopen orientation\b/ }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Quarter has ended"));

    reopenSlot.mockRejectedValueOnce({});
    await user.click(screen.getByRole("button", { name: /^Reopen orientation\b/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Couldn't reopen the slot"),
    );
  });

  it("goes round close → reopen → close again", async () => {
    const open = roster([row(OPEN_SLOT, "s1", "Carla Confirmed", "confirmed")]);
    const closed = roster([
      row({ ...OPEN_SLOT, slot_closed_at: CLOSED_AT }, "s1", "Carla Confirmed", "no_show"),
    ]);
    fetchRoster.mockResolvedValue(open);
    reopenSlot.mockResolvedValue(open);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Carla Confirmed");

    for (let round = 1; round <= 2; round += 1) {
      await user.click(screen.getByRole("button", { name: /^End slot\b/ }));
      const dialog = await screen.findByRole("dialog");
      fetchRoster.mockResolvedValue(closed);
      await user.click(within(dialog).getByRole("button", { name: /save/i }));
      await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(round));
      expect(resolveSlot).toHaveBeenLastCalledWith("slot-open", {
        attended: [],
        no_show: ["s1"],
      });
      expect(await screen.findByText("Closed")).toBeInTheDocument();

      fetchRoster.mockResolvedValue(open);
      await user.click(screen.getByRole("button", { name: /^Reopen slot\b/ }));
      expect(await screen.findByRole("button", { name: /^End slot\b/ })).toBeEnabled();
    }
    expect(reopenSlot).toHaveBeenCalledTimes(2);
  });

  it("can cancel the per-slot End dialog", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(OPEN_SLOT, "s1", "Carla Confirmed", "confirmed")]),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Carla Confirmed");

    await user.click(screen.getByRole("button", { name: /^End slot\b/ }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: /cancel/i }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(resolveSlot).not.toHaveBeenCalled();
  });
});

describe("End event", () => {
  it("offers only open slots that have started, closing them one by one", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(OPEN_SLOT, "s1", "Tuesday Person", "confirmed"),
        row(CLOSED_SLOT, "s2", "Already Closed", "attended"),
        row({ ...OPEN_SLOT, slot_id: "slot-thu", slot_time: FUTURE, slot_end: null }, "s3", "Thursday Person", "confirmed"),
      ]),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Tuesday Person");

    await user.click(screen.getByRole("button", { name: /^End event$/ }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Tuesday Person")).toBeInTheDocument();
    expect(within(dialog).queryByText("Thursday Person")).not.toBeInTheDocument();
    expect(within(dialog).queryByText("Already Closed")).not.toBeInTheDocument();

    await user.click(within(dialog).getByRole("button", { name: /save/i }));
    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(1));
    expect(resolveSlot).toHaveBeenCalledWith("slot-open", {
      attended: [],
      no_show: ["s1"],
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("says nothing can be closed yet before any session starts", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row({ ...OPEN_SLOT, slot_time: FUTURE }, "s1", "Thursday Person", "confirmed"),
      ]),
    );
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Thursday Person");

    await user.click(screen.getByRole("button", { name: /^End event$/ }));
    expect(
      await screen.findByText(/Nothing to close yet/),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^Close$/ }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reopens the whole event from the banner, and reports a failure", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(CLOSED_SLOT, "s1", "Ada Attended", "attended")]),
    );
    reopenEvent.mockRejectedValueOnce(new Error("Quarter has ended"));
    const user = userEvent.setup();
    renderPage();

    const banner = await screen.findByTestId("event-complete-banner");
    expect(screen.getByRole("button", { name: /Event ended/ })).toBeDisabled();
    await user.click(within(banner).getByRole("button", { name: /reopen event/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Quarter has ended"));

    reopenEvent.mockRejectedValueOnce({});
    await user.click(within(banner).getByRole("button", { name: /reopen event/i }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Couldn't reopen the event"),
    );

    let finish;
    reopenEvent.mockReturnValueOnce(new Promise((r) => (finish = r)));
    await user.click(within(banner).getByRole("button", { name: /reopen event/i }));
    expect(await screen.findByRole("button", { name: /Reopening…/ })).toBeDisabled();
    const open = roster([row({ ...CLOSED_SLOT, slot_closed_at: null }, "s1", "Ada Attended", "checked_in")]);
    fetchRoster.mockResolvedValue(open);
    finish(open);
    await waitFor(() =>
      expect(screen.queryByTestId("event-complete-banner")).not.toBeInTheDocument(),
    );
    expect(toast.success).toHaveBeenCalledWith(
      expect.stringMatching(/^Event reopened/),
    );
  });
});

describe("review round 1", () => {
  it("names the session on every End / Reopen button for screen readers", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(OPEN_SLOT, null, "Shift Person", "confirmed", {
          shift_signup_id: "c-1",
          shift_name: "Tue morning",
          session_name: "Period 1",
        }),
        row(CLOSED_SLOT, "s2", "Ada Attended", "attended"),
      ]),
    );
    renderPage();
    await screen.findByText("Shift Person");

    // 17:00Z on Jan 6 2020 is 9:00 AM Pacific.
    expect(
      screen.getByRole("button", {
        name: "End slot Tue morning · Period 1, Mon, Jan 6 · 9:00 AM – 10:30 AM",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Reopen orientation Mon, Jan 6 · 9:00 AM – 10:30 AM",
      }),
    ).toBeInTheDocument();
  });

  it("won't let a session be ended before it starts", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(OPEN_SLOT, "s1", "Tuesday Person", "confirmed"),
        row({ ...OPEN_SLOT, slot_id: "slot-thu", slot_type: "orientation", slot_time: FUTURE, slot_end: null }, "s2", "Thursday Person", "confirmed"),
      ]),
    );
    renderPage();
    await screen.findByText("Thursday Person");

    const hint = "This session hasn't started yet — you can close it once it starts.";
    const future = screen.getByRole("button", { name: /^End orientation\b/ });
    expect(future).toBeDisabled();
    expect(future).toHaveAttribute("title", hint);
    expect(future).toHaveAccessibleName(expect.stringContaining(hint));
    // Its volunteers can still be tapped in.
    expect(card("Thursday Person")).toBeEnabled();

    const started = screen.getByRole("button", { name: /^End slot\b/ });
    expect(started).toBeEnabled();
    expect(started).not.toHaveAttribute("title");
  });

  it("shows Reopening… only on the slot being reopened", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(CLOSED_SLOT, "s1", "Ada Attended", "attended"),
        row({ ...CLOSED_SLOT, slot_id: "slot-closed-2", slot_type: "period" }, "s2", "Ned NoShow", "no_show"),
      ]),
    );
    reopenSlot.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ada Attended");

    await user.click(screen.getByRole("button", { name: /^Reopen orientation\b/ }));

    const pending = await screen.findByText("Reopening…");
    expect(pending.closest("button")).toBeDisabled();
    expect(screen.getAllByText("Reopening…")).toHaveLength(1);
    expect(screen.getByRole("button", { name: /^Reopen slot\b/ })).toBeEnabled();
  });

  it("toasts the server's own message when a reopen is refused", async () => {
    fetchRoster.mockResolvedValue(
      roster([row(CLOSED_SLOT, "s1", "Ada Attended", "attended")]),
    );
    // What _authedRequest throws for the flattened {error, code, detail} body.
    const err = new Error("This quarter has ended and is read-only.");
    err.response = {
      status: 422,
      data: { error: "http_422", code: "http_422", detail: err.message },
    };
    reopenSlot.mockRejectedValueOnce(err);
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Ada Attended");

    await user.click(screen.getByRole("button", { name: /^Reopen orientation\b/ }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith(
        "This quarter has ended and is read-only.",
      ),
    );
  });

  it("counts a closed session from the rows it has, even if late joiners are omitted", async () => {
    // The backend leaves out shift commitments that joined after the session
    // closed; the header and the event banner work from what's there.
    fetchRoster.mockResolvedValue(
      roster(
        [row(CLOSED_SLOT, "s1", "Ada Attended", "attended")],
        { total: 3 },
      ),
    );
    renderPage();
    await screen.findByText("Ada Attended");

    expect(screen.getByText("1 attended · 0 no show")).toBeInTheDocument();
    expect(screen.getByTestId("event-complete-banner")).toBeInTheDocument();
  });

  it("never lets legacy rows without a slot hold the event open", async () => {
    fetchRoster.mockResolvedValue(
      roster([
        row(CLOSED_SLOT, "s1", "Ada Attended", "attended"),
        { signup_id: "s2", student_name: "Legacy Person", status: "confirmed", slot_time: PAST },
      ]),
    );
    renderPage();
    await screen.findByText("Legacy Person");

    expect(screen.getByTestId("event-complete-banner")).toBeInTheDocument();
  });
});

describe("page surfaces", () => {
  it("shows skeletons while loading", () => {
    fetchRoster.mockReturnValue(new Promise(() => {}));
    renderPage();
    expect(screen.getByText("Roster")).toBeInTheDocument();
  });

  it("retries a network failure on demand", async () => {
    fetchRoster.mockRejectedValueOnce(new Error("Network request failed"));
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: /try again/i }));
    fetchRoster.mockResolvedValue(roster([]));
    await waitFor(() => expect(fetchRoster).toHaveBeenCalledTimes(2));
  });

  it("sends an admin back to the admin event page", async () => {
    authState.role = "admin";
    fetchRoster.mockResolvedValue(roster([]));
    renderPage();
    const back = await screen.findByRole("link", { name: /back to event/i });
    expect(back).toHaveAttribute("href", "/admin/events/ev-1");
  });

  it("sends an organizer back to the events list", async () => {
    fetchRoster.mockResolvedValue(roster([]));
    renderPage();
    const back = await screen.findByRole("link", { name: /back to event/i });
    expect(back).toHaveAttribute("href", "/admin/events");
  });

  it("handles a bare roster: no name, no totals, no venue code", async () => {
    fetchRoster.mockResolvedValue({ rows: undefined });
    renderPage();
    await screen.findByText(/Live check-in/);
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Roster");
    expect(screen.getByText("0 / 0 (0%)")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
    // No slots at all: nothing is closed, so End event stays available.
    expect(screen.getByRole("button", { name: /^End event$/ })).toBeEnabled();
  });

  it("puts legacy rows without slot metadata in one group with no End button", async () => {
    fetchRoster.mockResolvedValue(
      roster(
        [
          { signup_id: "s1", student_name: "Legacy Person", status: "confirmed", slot_time: PAST },
          row({ ...OPEN_SLOT, slot_id: "s-shift", slot_location: null }, null, "Shift Person", "confirmed", {
            shift_signup_id: "c-1",
            shift_name: "Tue morning",
          }),
        ],
        { checked_in_count: 0, waitlisted: 0 },
      ),
    );
    renderPage();
    await screen.findByText("Legacy Person");

    expect(screen.getAllByRole("button", { name: /^End slot\b/ })).toHaveLength(1);
    // A shift with no session name shows just the shift.
    expect(screen.getByRole("heading", { level: 2, name: /Tue morning/ })).not.toHaveTextContent(" · Period");
  });

  it("opens and closes the QR and broadcast modals", async () => {
    fetchRoster.mockResolvedValue(roster([]));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Adams Elementary");

    await user.click(screen.getByRole("button", { name: "Check-in QR" }));
    expect(screen.getByTestId("qr-modal")).toHaveTextContent("Adams Elementary");
    await user.click(screen.getByRole("button", { name: "close qr" }));
    expect(screen.queryByTestId("qr-modal")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Message volunteers" }));
    expect(screen.getByTestId("broadcast-modal")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "close broadcast" }));
    expect(screen.queryByTestId("broadcast-modal")).not.toBeInTheDocument();
  });

  it("passes an empty title to the QR modal for an unnamed event", async () => {
    fetchRoster.mockResolvedValue({ ...roster([]), event_name: null });
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "Check-in QR" }));
    expect(screen.getByTestId("qr-modal")).toHaveTextContent("close qr");
  });
});

describe("quick-add question", () => {
  async function openModal(user) {
    fetchRoster.mockResolvedValue(roster([]));
    renderPage();
    await screen.findByText("Adams Elementary");
    await user.click(screen.getByRole("button", { name: "Add a question" }));
    return screen.findByRole("dialog");
  }

  it("adds a short-text question", async () => {
    const user = userEvent.setup();
    api.organizer.appendEventField.mockResolvedValue({});
    const dialog = await openModal(user);

    await user.type(within(dialog).getByLabelText("Question"), "  Parking pass needed?  ");
    await user.click(within(dialog).getByLabelText("Required"));
    await user.click(within(dialog).getByRole("button", { name: "Add field" }));

    await waitFor(() =>
      expect(api.organizer.appendEventField).toHaveBeenCalledWith("ev-1", {
        id: "parking_pass_needed",
        label: "Parking pass needed?",
        type: "text",
        required: true,
      }),
    );
    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith(
        "Question added to this event's signup form.",
      ),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    // A saved question doesn't linger in the form for the next one.
    await user.click(screen.getByRole("button", { name: "Add a question" }));
    const again = await screen.findByRole("dialog");
    expect(within(again).getByLabelText("Question")).toHaveValue("");
    expect(within(again).getByLabelText("Required")).not.toBeChecked();
  });

  it("ignores a blank question", async () => {
    const user = userEvent.setup();
    const dialog = await openModal(user);
    await user.type(within(dialog).getByLabelText("Question"), "   ");
    await user.click(within(dialog).getByRole("button", { name: "Add field" }));
    expect(api.organizer.appendEventField).not.toHaveBeenCalled();
  });

  it("needs options for a choice question, then sends them", async () => {
    const user = userEvent.setup();
    api.organizer.appendEventField.mockResolvedValue({});
    const dialog = await openModal(user);

    await user.type(within(dialog).getByLabelText("Question"), "T-shirt size");
    await user.selectOptions(within(dialog).getByLabelText("Answer type"), "select");
    const opts = within(dialog).getByLabelText("Options (comma-separated)");
    await user.type(opts, " , ");
    await user.click(within(dialog).getByRole("button", { name: "Add field" }));
    expect(toast.error).toHaveBeenCalledWith("Options are required for this field type.");
    expect(api.organizer.appendEventField).not.toHaveBeenCalled();

    await user.clear(opts);
    await user.type(opts, "S, M ,L");
    await user.click(within(dialog).getByRole("button", { name: "Add field" }));
    await waitFor(() =>
      expect(api.organizer.appendEventField).toHaveBeenCalledWith("ev-1", {
        id: "t_shirt_size",
        label: "T-shirt size",
        type: "select",
        required: false,
        options: ["S", "M", "L"],
      }),
    );
  });

  it("shows Adding… while saving and reports a failure", async () => {
    const user = userEvent.setup();
    let fail;
    api.organizer.appendEventField.mockReturnValueOnce(
      new Promise((_, reject) => (fail = reject)),
    );
    const dialog = await openModal(user);
    await user.type(within(dialog).getByLabelText("Question"), "Diet");
    await user.click(within(dialog).getByRole("button", { name: "Add field" }));
    expect(await within(dialog).findByRole("button", { name: "Adding..." })).toBeDisabled();
    fail(new Error("Event is archived"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Event is archived"));

    api.organizer.appendEventField.mockRejectedValueOnce({});
    await user.click(within(dialog).getByRole("button", { name: "Add field" }));
    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith("Failed to add field"),
    );
  });

  it("cancel clears and closes", async () => {
    const user = userEvent.setup();
    const dialog = await openModal(user);
    await user.type(within(dialog).getByLabelText("Question"), "Diet");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Add a question" }));
    const again = await screen.findByRole("dialog");
    expect(within(again).getByLabelText("Question")).toHaveValue("");
  });
});
