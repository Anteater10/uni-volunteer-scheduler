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

  it("offers a Google Calendar button for every session, not just the first", () => {
    setup({ slots: [SLOT_A, SLOT_B] });
    const open = vi.spyOn(window, "open").mockImplementation(() => null);

    const googleButtons = screen.getAllByRole("button", {
      name: /to google calendar/i,
    });
    expect(googleButtons).toHaveLength(2);

    fireEvent.click(googleButtons[0]);
    fireEvent.click(googleButtons[1]);
    expect(
      buildGoogleCalendarUrl.mock.calls.map((c) => c[0].slot.id),
    ).toEqual(["slot-a", "slot-b"]);
    expect(open).toHaveBeenCalledTimes(2);
    expect(open).toHaveBeenCalledWith(
      "https://calendar.google.com/stub",
      "_blank",
      "noopener,noreferrer",
    );
    open.mockRestore();
  });

  it("pushes the volunteer to confirm — spots aren't held forever", () => {
    setup();
    // The copy must convey urgency: the signup isn't final until confirmed,
    // and unconfirmed spots get released.
    expect(screen.getByText(/isn'?t secured yet/i)).toBeInTheDocument();
    expect(screen.getByText(/expire/i)).toBeInTheDocument();
  });

  it("badges waitlisted sessions and warns about the 3-day promotion window", () => {
    setup({
      slots: [SLOT_A, SLOT_B],
      signups: [
        { signup_id: "su-1", slot_id: "slot-a", status: "pending" },
        { signup_id: "su-2", slot_id: "slot-b", status: "waitlisted", position: 2 },
      ],
    });

    expect(screen.getByText(/waitlist #2/i)).toBeInTheDocument();
    // The inbox warning: promotion emails are actionable for only 3 days.
    const notice = screen.getByText(/check your inbox/i);
    expect(notice).toBeInTheDocument();
    expect(screen.getByText(/3 days/i)).toBeInTheDocument();

    // Only the non-waitlisted session gets a Google button…
    const googleButtons = screen.getAllByRole("button", {
      name: /to google calendar/i,
    });
    expect(googleButtons).toHaveLength(1);
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    fireEvent.click(googleButtons[0]);
    expect(buildGoogleCalendarUrl.mock.calls[0][0].slot.id).toBe("slot-a");
    open.mockRestore();

    // …and the .ics export skips the waitlisted one too.
    fireEvent.click(icsButton());
    expect(downloadIcs.mock.calls[0][0].slots.map((s) => s.id)).toEqual([
      "slot-a",
    ]);
  });

  it("hides the calendar buttons when every session is waitlisted", () => {
    setup({
      slots: [SLOT_A],
      signups: [
        { signup_id: "su-1", slot_id: "slot-a", status: "waitlisted", position: 1 },
      ],
    });
    expect(
      screen.queryByRole("button", { name: /google calendar/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /download \.ics/i }),
    ).not.toBeInTheDocument();
  });

  it("calls onDismiss from Done", () => {
    const onDismiss = vi.fn();
    setup({ onDismiss });
    fireEvent.click(screen.getByRole("button", { name: /^done$/i }));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });
});
