/* global process -- tests switch the machine's timezone via process.env.TZ */
// src/pages/__tests__/OrganizerRosterPage.slotdates.test.jsx
//
// Slot section headers must carry the slot's date, not just its time range —
// a multi-day event otherwise renders two identical-looking "9:00 AM" sections
// and the organizer can't tell which day they're checking in.
//
// 2026-10-13: and in venue (Pacific) time, like the public page. These run
// with the machine's clock in New York so a browser-timezone formatter would
// print the wrong hour (and, late in the evening, the wrong day).

import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../api/roster", () => ({
  fetchRoster: vi.fn(),
  checkInSignup: vi.fn(),
  undoCheckInSignup: vi.fn(),
  reopenEvent: vi.fn(),
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({ role: "organizer" }),
}));

import { afterAll, beforeAll } from "vitest";
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

const DAY_ONE_SLOT = {
  slot_id: "slot-day-one",
  slot_type: "period",
  slot_time: "2026-07-26T17:00:00Z",
  slot_end: "2026-07-26T18:30:00Z",
};

const DAY_TWO_SLOT = {
  slot_id: "slot-day-two",
  slot_type: "period",
  slot_time: "2026-07-27T17:00:00Z",
  slot_end: "2026-07-27T18:30:00Z",
};

const LATE_SLOT = {
  slot_id: "slot-late",
  slot_type: "period",
  // 9pm Pacific on Sun Jul 26 — already Monday in New York.
  slot_time: "2026-07-27T04:00:00Z",
  slot_end: "2026-07-27T05:00:00Z",
};

const originalTz = process.env.TZ;
beforeAll(() => {
  process.env.TZ = "America/New_York";
});
afterAll(() => {
  process.env.TZ = originalTz;
});

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

describe("OrganizerRosterPage — slot header dates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows each slot's Pacific date and time range in its section header", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 0,
      rows: [
        row({ ...DAY_ONE_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "confirmed" }),
        row({ ...DAY_TWO_SLOT, signup_id: "s2", student_name: "Marcus Delgado", status: "confirmed" }),
      ],
    });

    renderPage();
    await screen.findByText("CRISPR Module 1");

    // 17:00Z is 10:00 AM Pacific (1:00 PM in New York, where this runs).
    expect(
      screen.getByRole("heading", { level: 2, name: /Sun, Jul 26 · 10:00 AM – 11:30 AM/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: /Mon, Jul 27 · 10:00 AM – 11:30 AM/ }),
    ).toBeInTheDocument();
    // Card times are Pacific too.
    expect(screen.getAllByText("10:00 AM")).toHaveLength(2);
    expect(screen.queryByText(/1:00 PM/)).not.toBeInTheDocument();
  });

  it("keeps a late-evening session on its Pacific day", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 0,
      rows: [
        row({ ...LATE_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "confirmed" }),
      ],
    });

    renderPage();
    await screen.findByText("CRISPR Module 1");

    expect(
      screen.getByRole("heading", { level: 2, name: /Sun, Jul 26 · 9:00 PM – 10:00 PM/ }),
    ).toBeInTheDocument();
  });

  it("copes with a slot that has only an end time, or no times at all", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 0,
      rows: [
        row({ slot_id: "end-only", slot_type: "period", slot_time: null, slot_end: DAY_ONE_SLOT.slot_end, signup_id: "s1", student_name: "Alina Rahman", status: "confirmed" }),
        row({ slot_id: "no-times", slot_type: "period", slot_time: null, slot_end: null, signup_id: "s2", student_name: "Marcus Delgado", status: "confirmed" }),
      ],
    });

    renderPage();
    await screen.findByText("CRISPR Module 1");

    // Date from the end time, with " – 11:30 AM" as the range.
    expect(
      screen.getByRole("heading", { level: 2, name: /Sun, Jul 26 · – 11:30 AM/ }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(2);
  });
});
