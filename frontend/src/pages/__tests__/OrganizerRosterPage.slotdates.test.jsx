// src/pages/__tests__/OrganizerRosterPage.slotdates.test.jsx
//
// Slot section headers must carry the slot's date, not just its time range —
// a multi-day event otherwise renders two identical-looking "9:00 AM" sections
// and the organizer can't tell which day they're checking in.

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

// Same formatting call the page makes, so the assertion is timezone-agnostic
// regardless of the TZ the test runner happens to use.
function expectedDateLabel(iso) {
  return new Date(iso).toLocaleDateString([], {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
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

describe("OrganizerRosterPage — slot header dates", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows each slot's date in its section header", async () => {
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

    const dayOne = expectedDateLabel(DAY_ONE_SLOT.slot_time);
    const dayTwo = expectedDateLabel(DAY_TWO_SLOT.slot_time);
    expect(
      screen.getByRole("heading", { level: 2, name: new RegExp(escapeRegExp(dayOne)) }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 2, name: new RegExp(escapeRegExp(dayTwo)) }),
    ).toBeInTheDocument();
  });

  it("still shows the time range alongside the date", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 0,
      rows: [
        row({ ...DAY_ONE_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "confirmed" }),
      ],
    });

    renderPage();
    await screen.findByText("CRISPR Module 1");

    const start = new Date(DAY_ONE_SLOT.slot_time).toLocaleTimeString([], {
      hour: "numeric",
      minute: "2-digit",
    });
    const heading = screen.getByRole("heading", {
      level: 2,
      name: new RegExp(escapeRegExp(start)),
    });
    expect(heading).toHaveTextContent(expectedDateLabel(DAY_ONE_SLOT.slot_time));
  });
});
