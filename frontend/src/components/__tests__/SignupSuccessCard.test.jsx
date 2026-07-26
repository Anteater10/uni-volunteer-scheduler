/**
 * SignupSuccessCard.test.jsx
 *
 * The calendar buttons on this card were unreachable in practice: they were
 * gated on an `event && slot` pair, and the signup flow — the only caller —
 * confirms a *list* of slots and passes no `slot`. These tests pin the relaxed
 * gate and the multi-session export so that regression can't come back.
 */

import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import SignupSuccessCard from "../SignupSuccessCard";

vi.mock("../../lib/calendar", () => ({
  downloadIcs: vi.fn(),
  buildGoogleCalendarUrl: vi.fn(() => "https://calendar.google.com/stub"),
}));
vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import { downloadIcs, buildGoogleCalendarUrl } from "../../lib/calendar";
import { toast } from "../../state/toast";

const EVENT = { id: "evt-1", title: "CRISPR at Carpinteria HS", slug: "crispr" };
const SLOT_A = {
  id: "slot-a",
  date: "2026-04-22",
  start_time: "2026-04-22T16:00:00Z",
  end_time: "2026-04-22T18:00:00Z",
  location: "Room 12",
};
const SLOT_B = {
  id: "slot-b",
  date: "2026-04-23",
  start_time: "2026-04-23T16:00:00Z",
  end_time: "2026-04-23T18:00:00Z",
  location: "Room 12",
};

function setup(props = {}) {
  return render(
    <SignupSuccessCard
      open
      volunteerName="Ada"
      slots={[SLOT_A]}
      event={EVENT}
      onDismiss={() => {}}
      {...props}
    />,
  );
}

const icsButton = () => screen.getByRole("button", { name: /download \.ics/i });

describe("SignupSuccessCard", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists the confirmed slots", () => {
    setup({ slots: [SLOT_A, SLOT_B] });
    expect(screen.getByText(/you signed up for/i)).toBeInTheDocument();
    expect(screen.getAllByText(/Room 12/)).toHaveLength(2);
  });

  it("offers the calendar buttons from a slots list alone, with no `slot` prop", () => {
    setup();
    expect(icsButton()).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /add to google calendar/i }),
    ).toBeInTheDocument();
  });

  it("hides the calendar buttons when there is no event to describe", () => {
    setup({ event: undefined });
    expect(
      screen.queryByRole("button", { name: /download \.ics/i }),
    ).not.toBeInTheDocument();
  });

  it("hides the calendar buttons when no slots were confirmed", () => {
    setup({ slots: [] });
    expect(
      screen.queryByRole("button", { name: /download \.ics/i }),
    ).not.toBeInTheDocument();
  });

  it("exports every confirmed slot in one file", () => {
    setup({ slots: [SLOT_A, SLOT_B] });
    fireEvent.click(icsButton());

    expect(downloadIcs).toHaveBeenCalledTimes(1);
    const arg = downloadIcs.mock.calls[0][0];
    expect(arg.event).toBe(EVENT);
    expect(arg.slots.map((s) => s.id)).toEqual(["slot-a", "slot-b"]);
    // No filename: calendar.js derives and sanitises it.
    expect(arg).not.toHaveProperty("filename");
    expect(toast.success).toHaveBeenCalledWith(
      "Calendar file saved with 2 sessions. Open it to add them.",
    );
  });

  it("still accepts a single `slot` for callers that confirm one at a time", () => {
    setup({ slots: [], slot: SLOT_A });
    fireEvent.click(icsButton());
    expect(downloadIcs.mock.calls[0][0].slots.map((s) => s.id)).toEqual([
      "slot-a",
    ]);
    expect(toast.success).toHaveBeenCalledWith(
      "Calendar file saved. Open it to add to your calendar.",
    );
  });

  it("sends the first session to Google, and says so when there are several", () => {
    setup({ slots: [SLOT_A, SLOT_B] });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);

    fireEvent.click(
      screen.getByRole("button", { name: /add first session to google/i }),
    );
    expect(buildGoogleCalendarUrl.mock.calls[0][0].slot.id).toBe("slot-a");
    expect(open).toHaveBeenCalledWith(
      "https://calendar.google.com/stub",
      "_blank",
      "noopener,noreferrer",
    );
    open.mockRestore();
  });

  it("calls onDismiss from Done", () => {
    const onDismiss = vi.fn();
    setup({ onDismiss });
    fireEvent.click(screen.getByRole("button", { name: /^done$/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
