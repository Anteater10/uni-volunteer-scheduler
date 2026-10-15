// src/pages/__tests__/OrganizerRosterPage.ended.test.jsx
//
// 2026-10-13 (Kim's report): a slot is closed when, and only when, the slot
// itself says so (`slot_closed_at`). It used to be inferred from every signup
// being attended/no_show, so a future session whose volunteers had been
// wrongly marked no-show read as "Ended" with nothing a person had pressed.
// A closed slot announces itself and offers "Reopen …"; an open slot beside
// it stays fully actionable.

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
    slot_closed_at: overrides.slot_closed_at ?? null,
  };
}

const CLOSED_AT = "2026-07-26T19:00:00Z";

const ENDED_SLOT = {
  slot_id: "slot-orientation",
  slot_type: "orientation",
  slot_time: "2026-07-26T17:00:00Z",
  slot_end: "2026-07-26T18:30:00Z",
  slot_closed_at: CLOSED_AT,
};

const LIVE_SLOT = {
  slot_id: "slot-module",
  slot_type: "period",
  slot_time: "2026-07-27T15:00:00Z",
  slot_end: "2026-07-27T18:00:00Z",
};

const CLOSED_MODULE = { ...LIVE_SLOT, slot_closed_at: CLOSED_AT };

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

describe("OrganizerRosterPage — closed slots", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("marks a closed slot Closed and offers Reopen instead of End", async () => {
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

    // Closed orientation: badge, attended/no-show tally, enabled Reopen.
    expect(await screen.findByText("Closed")).toBeInTheDocument();
    expect(screen.getByText("1 attended · 1 no show")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /^Reopen orientation\b/i }),
    ).toBeEnabled();
    expect(
      screen.queryByRole("button", { name: /^End orientation\b/i }),
    ).not.toBeInTheDocument();
    // Its cards are read-only.
    expect(screen.getByText("Alina Rahman").closest("button")).toBeDisabled();
    expect(screen.getByText("Marcus Delgado").closest("button")).toBeDisabled();

    // The live module slot beside it is untouched.
    const liveBtn = screen.getByRole("button", { name: /^End slot\b/i });
    expect(liveBtn).toBeEnabled();
    expect(screen.getByText("1/2 checked in")).toBeInTheDocument();

    // Not every slot is closed, so the event-level action stays available.
    expect(screen.getByRole("button", { name: /^End event$/i })).toBeEnabled();
  });

  it("locks the event-level End button once every slot is closed", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 1,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
        row({ ...CLOSED_MODULE, signup_id: "s2", student_name: "Jonah Whitfield", status: "no_show" }),
      ],
    });

    renderPage();

    const eventBtn = await screen.findByRole("button", { name: /Event ended/i });
    expect(eventBtn).toBeDisabled();
  });

  it("never infers Closed from statuses: an all-no-show open slot stays open", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 1,
      rows: [
        // The Thursday case: everyone marked no_show, but nobody closed the
        // slot. It must not read as Closed, and the event isn't done.
        row({ ...ENDED_SLOT, slot_closed_at: null, signup_id: "s1", student_name: "Alina Rahman", status: "no_show" }),
        row({ ...ENDED_SLOT, slot_closed_at: null, signup_id: "s2", student_name: "Marcus Delgado", status: "no_show" }),
      ],
    });

    renderPage();

    const btn = await screen.findByRole("button", { name: /^End orientation\b/i });
    expect(btn).toBeEnabled();
    expect(screen.queryByText("Closed")).not.toBeInTheDocument();
    expect(screen.queryByTestId("event-complete-banner")).not.toBeInTheDocument();
    expect(screen.getByText("0/2 checked in")).toBeInTheDocument();
  });

  it("shows Closed on a closed slot even when nobody in it is attended/no_show", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 0,
      rows: [
        row({ ...CLOSED_MODULE, signup_id: "s1", student_name: "Wait Listed", status: "waitlisted" }),
      ],
    });

    renderPage();

    expect(await screen.findByText("Closed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Reopen slot\b/i })).toBeEnabled();
  });

  // PR #51 — a fully-closed event gets an animated completion banner.

  it("celebrates a fully-closed event with the completion banner", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 3,
      checked_in_count: 0,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
        row({ ...ENDED_SLOT, signup_id: "s2", student_name: "Marcus Delgado", status: "no_show" }),
        row({ ...CLOSED_MODULE, signup_id: "s3", student_name: "Priya Venkatesan", status: "attended" }),
        // A slot nobody is seated in doesn't hold the event open.
        row({ slot_id: "empty", slot_type: "period", slot_time: "2026-07-28T15:00:00Z", signup_id: "s4", student_name: "Can Celled", status: "cancelled" }),
      ],
    });

    renderPage();

    const banner = await screen.findByTestId("event-complete-banner");
    expect(banner).toHaveTextContent(/event complete/i);
    expect(banner).toHaveTextContent(/2 attended/i);
    expect(banner).toHaveTextContent(/1 no-show on the books/i);
    expect(banner).toHaveTextContent(
      /Orientation credit was granted with each closed orientation\./,
    );
    expect(banner).toHaveTextContent(/Reopen a slot to fix a mistake/i);
  });

  it("pluralises no-shows and skips the credit line without orientation", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 0,
      rows: [
        row({ ...CLOSED_MODULE, signup_id: "s1", student_name: "Alina Rahman", status: "no_show" }),
        row({ ...CLOSED_MODULE, signup_id: "s2", student_name: "Marcus Delgado", status: "no_show" }),
      ],
    });

    renderPage();

    const banner = await screen.findByTestId("event-complete-banner");
    expect(banner).toHaveTextContent(/2 no-shows on the books/i);
    expect(banner).not.toHaveTextContent(/Orientation credit/i);
  });

  it("offers the reopen undo from the completion banner", async () => {
    const { fireEvent } = await import("@testing-library/react");
    const { reopenEvent } = await import("../../api/roster");
    reopenEvent.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 1,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "checked_in" }),
      ],
    });
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 0,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
      ],
    });

    renderPage();

    const banner = await screen.findByTestId("event-complete-banner");
    const reopenBtn = screen.getByRole("button", { name: /reopen event/i });
    expect(banner).toContainElement(reopenBtn);

    fireEvent.click(reopenBtn);
    await screen.findByText("CRISPR Module 1");
    expect(reopenEvent).toHaveBeenCalledTimes(1);
  });

  it("shows no completion banner while any slot is live", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 2,
      checked_in_count: 1,
      rows: [
        row({ ...ENDED_SLOT, signup_id: "s1", student_name: "Alina Rahman", status: "attended" }),
        row({ ...LIVE_SLOT, signup_id: "s2", student_name: "Jonah Whitfield", status: "confirmed" }),
      ],
    });

    renderPage();

    await screen.findByText("CRISPR Module 1");
    expect(screen.queryByTestId("event-complete-banner")).not.toBeInTheDocument();
  });

  it("does not treat a cancelled-only open slot as closed", async () => {
    fetchRoster.mockResolvedValue({
      event_name: "CRISPR Module 1",
      total: 1,
      checked_in_count: 0,
      rows: [
        // Cancelled rows are excluded from `expected`, so the slot has nothing
        // to close — it must not silently read as finished.
        row({ ...ENDED_SLOT, slot_closed_at: null, signup_id: "s1", student_name: "Alina Rahman", status: "cancelled" }),
      ],
    });

    renderPage();

    const btn = await screen.findByRole("button", { name: /^End orientation\b/i });
    expect(btn).toBeEnabled();
  });
});
