// src/pages/__tests__/OrganizerRosterPage.ended.test.jsx
//
// Ending a slot is irreversible from the live-roster screen, and the only
// signal that it happened is that every expected signup has been resolved to
// attended/no_show. These cover that derivation: an ended slot must announce
// itself and lock its "End …" button, while a live slot beside it stays fully
// actionable.

import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../api/roster", () => ({
  fetchRoster: vi.fn(),
  checkInSignup: vi.fn(),
  undoCheckInSignup: vi.fn(),
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({ role: "organizer" }),
}));

import { fetchRoster } from "../../api/roster";
import OrganizerRosterPage from "../OrganizerRosterPage";

function row(overrides) {
  return {
    signup_id: overrides.signup_id,
    student_name: overrides.student_name,
    status: overrides.status,
    slot_id: overrides.slot_id,
    slot_type: overrides.slot_type,
    slot_time: overrides.slot_time,
    slot_end: overrides.slot_end,
    slot_location: "Room 12",
  };
}

const ENDED_SLOT = {
  slot_id: "slot-orientation",
  slot_type: "orientation",
  slot_time: "2026-07-26T17:00:00Z",
  slot_end: "2026-07-26T18:30:00Z",
};

const LIVE_SLOT = {
  slot_id: "slot-module",
  slot_type: "period",
  slot_time: "2026-07-27T15:00:00Z",
  slot_end: "2026-07-27T18:00:00Z",
};

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

describe("OrganizerRosterPage — ended slots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("marks a fully-resolved slot as ended and locks its End button", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 4,
      checked_in_count: 1,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
        row({ ...ENDED_SLOT, signup_id: "s2", student_name: "Marcus Delgado", status: "no_show" }),
        row({ ...LIVE_SLOT, signup_id: "s3", student_name: "Priya Venkatesan", status: "confirmed" }),
        row({ ...LIVE_SLOT, signup_id: "s4", student_name: "Jonah Whitfield", status: "checked_in" }),
      ],
    });

    renderPage();

    // Ended orientation: badge, attended/no-show tally, disabled button.
    expect(await screen.findByText(/Ended/)).toBeInTheDocument();
    expect(screen.getByText("1 attended · 1 no show")).toBeInTheDocument();
    const endedBtn = screen.getByRole("button", { name: /Orientation ended/i });
    expect(endedBtn).toBeDisabled();

    // The live module slot beside it is untouched.
    const liveBtn = screen.getByRole("button", { name: /^End slot$/i });
    expect(liveBtn).toBeEnabled();
    expect(screen.getByText("1/2 checked in")).toBeInTheDocument();

    // Not every slot is resolved, so the event-level action stays available.
    expect(screen.getByRole("button", { name: /^End event$/i })).toBeEnabled();
  });

  it("locks the event-level End button once every slot is resolved", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 1,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
        row({ ...LIVE_SLOT, signup_id: "s2", student_name: "Jonah Whitfield", status: "no_show" }),
      ],
    });

    renderPage();

    const eventBtn = await screen.findByRole("button", { name: /Event ended/i });
    expect(eventBtn).toBeDisabled();
  });

  it("leaves a slot live while anyone is still unresolved", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 1,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
        // Still checked in, not yet resolved — the slot is not over.
        row({ ...ENDED_SLOT, signup_id: "s2", student_name: "Marcus Delgado", status: "checked_in" }),
      ],
    });

    renderPage();

    const btn = await screen.findByRole("button", { name: /^End orientation$/i });
    expect(btn).toBeEnabled();
    expect(screen.queryByText(/Ended/)).not.toBeInTheDocument();
  });

  it("does not treat a cancelled-only slot as ended", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 0,
      rows: [
        // Cancelled rows are excluded from `expected`, so the slot has nothing
        // to resolve — it must not silently read as finished.
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "cancelled" }),
      ],
    });

    renderPage();

    const btn = await screen.findByRole("button", { name: /^End orientation$/i });
    expect(btn).toBeEnabled();
  });
});
