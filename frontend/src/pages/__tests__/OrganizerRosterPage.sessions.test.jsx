// src/pages/__tests__/OrganizerRosterPage.sessions.test.jsx
//
// 2026-08-05 shifts — the live check-in page against shift-booked rows.
//
// A roster row is one volunteer at one *session*, and a shift row carries
// `shift_signup_id` with `signup_id` null. The page tapped
// `checkInSignup(row.signup_id)`, so a shift volunteer's card fired a request
// to /signups/undefined/check-in — and because the optimistic update also
// matched on signup_id, every shift row on the page flipped to "checked in"
// while the server had recorded nothing. Check-in is keyed on
// (commitment, session): a Tue+Wed volunteer is checked in once per day and can
// be present Tuesday and absent Wednesday.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
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

vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import {
  fetchRoster,
  checkInSignup,
  undoCheckInSignup,
  checkInSession,
  undoCheckInSession,
} from "../../api/roster";
import OrganizerRosterPage from "../OrganizerRosterPage";

const TUE = "slot-tue";
const WED = "slot-wed";

// Ada holds a Tue+Wed shift, so she is on the roster twice.
const ROWS = [
  {
    shift_signup_id: "c-1",
    signup_id: null,
    slot_id: TUE,
    slot_type: "period",
    shift_name: "Tue morning",
    session_name: "Period 1",
    student_name: "Ada Lovelace",
    status: "confirmed",
    slot_time: "2026-07-26T17:00:00Z",
    slot_end: "2026-07-26T18:30:00Z",
  },
  {
    shift_signup_id: "c-1",
    signup_id: null,
    slot_id: WED,
    slot_type: "period",
    shift_name: "Tue morning",
    session_name: "Period 2",
    student_name: "Ada Lovelace",
    status: "confirmed",
    slot_time: "2026-07-27T17:00:00Z",
    slot_end: "2026-07-27T18:30:00Z",
  },
];

function roster(rows) {
  return {
    event_id: "ev-1",
    event_name: "Adams Elementary",
    total: rows.length,
    checked_in_count: 0,
    rows,
  };
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <OrganizerRosterPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("OrganizerRosterPage — shift sessions", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    checkInSession.mockResolvedValue({});
    undoCheckInSession.mockResolvedValue({});
  });

  it("checks in one session, not the whole commitment", async () => {
    fetchRoster.mockResolvedValue(roster(ROWS));
    const user = userEvent.setup();
    renderPage();

    const cards = await screen.findAllByText("Ada Lovelace");
    expect(cards).toHaveLength(2);

    await user.click(cards[0].closest("button"));

    await waitFor(() => expect(checkInSession).toHaveBeenCalledTimes(1));
    expect(checkInSession).toHaveBeenCalledWith("c-1", TUE);
    // No signup id exists on this row, so the signup endpoint must not be
    // reached — calling it was a request to /signups/undefined/check-in.
    expect(checkInSignup).not.toHaveBeenCalled();
  });

  it("only the tapped session shows as checked in", async () => {
    fetchRoster.mockResolvedValue(roster(ROWS));
    // Hold the request open so the assertion lands on the optimistic state
    // rather than on the refetch that follows it.
    checkInSession.mockReturnValue(new Promise(() => {}));
    const user = userEvent.setup();
    renderPage();

    const cards = await screen.findAllByText("Ada Lovelace");
    await user.click(cards[0].closest("button"));

    // The optimistic update matches on (commitment, session). Matching on the
    // commitment alone flipped Wednesday too, so the organizer saw a volunteer
    // checked in for a day they hadn't turned up to yet.
    await waitFor(() =>
      expect(screen.getAllByText("checked in")).toHaveLength(1),
    );
    expect(screen.getAllByText("confirmed")).toHaveLength(1);
  });

  it("undo reverts the session it was tapped on", async () => {
    fetchRoster.mockResolvedValue(
      roster([{ ...ROWS[0], status: "checked_in" }, ROWS[1]]),
    );
    const user = userEvent.setup();
    renderPage();

    const cards = await screen.findAllByText("Ada Lovelace");
    await user.click(cards[0].closest("button"));

    await waitFor(() => expect(undoCheckInSession).toHaveBeenCalledTimes(1));
    expect(undoCheckInSession).toHaveBeenCalledWith("c-1", TUE);
    expect(undoCheckInSignup).not.toHaveBeenCalled();
  });

  it("names the shift and session in the section header", async () => {
    fetchRoster.mockResolvedValue(roster(ROWS));
    renderPage();

    // Two sessions of the same shift run at the same hour on different days;
    // the header has to say which one this section is.
    expect(
      await screen.findByText(/Tue morning · Period 1/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Tue morning · Period 2/)).toBeInTheDocument();
  });
});
