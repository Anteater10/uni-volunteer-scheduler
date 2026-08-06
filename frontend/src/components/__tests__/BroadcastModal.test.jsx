// Phase 26 — BroadcastModal tests.
//
// Covers the three paths the UI owns end-to-end: recipient-count preview,
// successful send dispatches the API payload, and 429 renders a friendly
// rate-limit error.

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../lib/api", () => {
  const broadcastRecipientCount = vi.fn();
  const sendBroadcast = vi.fn();
  const api = {
    listSlots: vi.fn(),
    shifts: { list: vi.fn() },
    admin: {
      broadcastRecipientCount,
      sendBroadcast,
    },
    organizer: {
      broadcastRecipientCount,
      sendBroadcast,
    },
  };
  return { api, default: api };
});

vi.mock("../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { api } from "../../lib/api";
import { toast } from "../../state/toast";
import BroadcastModal from "../BroadcastModal";

// 2026-08-05 shifts: a period slot is a *session*, so it belongs to a shift
// and carries shift_id. It is not itself a broadcast target — the shift is.
const SESSION_A1 = {
  id: "sess-a1",
  shift_id: "shift-a",
  sort_order: 0,
  slot_type: "period",
  date: "2026-04-20",
  start_time: "2026-04-20T16:00:00",
  end_time: "2026-04-20T18:00:00",
  location: "Room 12",
  capacity: 10,
  current_count: 3,
};

const SESSION_A2 = {
  id: "sess-a2",
  shift_id: "shift-a",
  sort_order: 1,
  slot_type: "period",
  date: "2026-04-21",
  start_time: "2026-04-21T16:00:00",
  end_time: "2026-04-21T18:00:00",
  location: "Room 12",
  capacity: 10,
  current_count: 3,
};

const SHIFT_A = {
  id: "shift-a",
  event_id: "evt-1",
  name: "Tue morning",
  sort_order: 0,
  capacity: 10,
  current_count: 3,
  sessions: [SESSION_A1, SESSION_A2],
};

const SLOT_B = {
  id: "slot-b",
  slot_type: "orientation",
  date: "2026-04-20",
  start_time: "2026-04-20T19:00:00",
  end_time: "2026-04-20T20:00:00",
  location: null,
  capacity: 30,
  current_count: 12,
};

describe("BroadcastModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Default: nothing bookable → picker hidden, whole-event behaviour.
    api.listSlots.mockResolvedValue([]);
    api.shifts.list.mockResolvedValue([]);
  });

  it("renders the recipient count from the server", async () => {
    api.admin.broadcastRecipientCount.mockResolvedValueOnce({
      recipient_count: 7,
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="admin"
      />,
    );

    await waitFor(() =>
      expect(api.admin.broadcastRecipientCount).toHaveBeenCalledWith("evt-1"),
    );
    const pill = await screen.findByTestId("broadcast-recipient-count");
    expect(pill.textContent).toMatch(/7 volunteers/i);
  });

  it("sends the broadcast with the typed subject + body on confirm", async () => {
    api.admin.broadcastRecipientCount.mockResolvedValueOnce({
      recipient_count: 2,
    });
    api.admin.sendBroadcast.mockResolvedValueOnce({
      broadcast_id: "bcast1",
      recipient_count: 2,
      sent_at: "2026-04-17T00:00:00Z",
    });

    const onClose = vi.fn();
    render(
      <BroadcastModal
        open
        onClose={onClose}
        eventId="evt-2"
        scope="admin"
      />,
    );

    await screen.findByTestId("broadcast-recipient-count");

    const user = userEvent.setup();
    const subjectInput = screen.getByLabelText("Subject");
    const bodyInput = screen.getByLabelText(/Message \(Markdown\)/i);

    await user.type(subjectInput, "Parking moved");
    await user.type(bodyInput, "New lot is **Lot 22**.");

    // First click opens the confirm state; second click actually sends.
    await user.click(screen.getByTestId("broadcast-send"));
    await user.click(await screen.findByTestId("broadcast-confirm"));

    await waitFor(() =>
      expect(api.admin.sendBroadcast).toHaveBeenCalledWith("evt-2", {
        subject: "Parking moved",
        body_markdown: "New lot is **Lot 22**.",
      }),
    );
    expect(toast.success).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("shows a rate-limit error when the API returns 429", async () => {
    api.admin.broadcastRecipientCount.mockResolvedValueOnce({
      recipient_count: 3,
    });
    const err = new Error("Broadcast rate limit reached");
    err.status = 429;
    err.retryAfter = 120;
    api.admin.sendBroadcast.mockRejectedValueOnce(err);

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-3"
        scope="admin"
      />,
    );

    await screen.findByTestId("broadcast-recipient-count");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Subject"), "Over the limit");
    await user.type(screen.getByLabelText(/Message \(Markdown\)/i), "again");

    await user.click(screen.getByTestId("broadcast-send"));
    await user.click(await screen.findByTestId("broadcast-confirm"));

    const alert = await screen.findByText(/Rate limit reached/i);
    expect(alert).toBeTruthy();
  });

  // ------------------------------------------------------------------
  // Slot-scoped sending — organizer targets one slot's roster;
  // "All slots" (the default) preserves the whole-event behavior.
  // ------------------------------------------------------------------

  it("lists shifts and orientation slots, never bare sessions", async () => {
    api.listSlots.mockResolvedValue([SESSION_A1, SESSION_A2, SLOT_B]);
    api.shifts.list.mockResolvedValue([SHIFT_A]);
    api.organizer.broadcastRecipientCount.mockResolvedValueOnce({
      recipient_count: 7,
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    const select = await screen.findByTestId("broadcast-slot-select");
    expect(api.listSlots).toHaveBeenCalledWith({ event_id: "evt-1" });
    expect(api.shifts.list).toHaveBeenCalledWith("evt-1");
    expect(select.value).toBe("");

    // The shift plus the orientation slot — and nothing else. Listing the two
    // sessions as their own options is what shipped, and every one of them was
    // unsendable: a session has no roster of its own and the API 422s it.
    const labels = [...select.options].map((o) => o.textContent);
    expect(labels).toHaveLength(3);
    expect(labels[0]).toMatch(/everyone signed up/i);
    expect(labels[1]).toMatch(/Tue morning/);
    expect(labels[2]).toMatch(/orientation/i);
    const values = [...select.options].map((o) => o.value);
    expect(values).not.toContain("sess-a1");
    expect(values).not.toContain("sess-a2");

    // Both days are named, since "Tue morning" alone doesn't say what the
    // volunteer committed to.
    expect(labels[1]).toMatch(/Apr 20/);
    expect(labels[1]).toMatch(/Apr 21/);

    expect(api.organizer.broadcastRecipientCount).toHaveBeenCalledWith("evt-1");
  });

  it("previews the recipient count for a chosen shift", async () => {
    api.listSlots.mockResolvedValue([SESSION_A1, SESSION_A2, SLOT_B]);
    api.shifts.list.mockResolvedValue([SHIFT_A]);
    api.organizer.broadcastRecipientCount
      .mockResolvedValueOnce({ recipient_count: 7 })
      .mockResolvedValueOnce({ recipient_count: 3 });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    const select = await screen.findByTestId("broadcast-slot-select");
    const user = userEvent.setup();
    await user.selectOptions(select, "shift:shift-a");

    await waitFor(() =>
      expect(api.organizer.broadcastRecipientCount).toHaveBeenLastCalledWith(
        "evt-1",
        { shift_id: "shift-a" },
      ),
    );
    const pill = await screen.findByTestId("broadcast-recipient-count");
    await waitFor(() => expect(pill.textContent).toMatch(/3 volunteers/i));
  });

  it("sends shift_id in the payload when a shift is selected", async () => {
    api.listSlots.mockResolvedValue([SESSION_A1, SESSION_A2, SLOT_B]);
    api.shifts.list.mockResolvedValue([SHIFT_A]);
    api.organizer.broadcastRecipientCount.mockResolvedValue({
      recipient_count: 3,
    });
    api.organizer.sendBroadcast.mockResolvedValueOnce({
      broadcast_id: "bcast2",
      recipient_count: 3,
      sent_at: "2026-07-21T00:00:00Z",
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    const select = await screen.findByTestId("broadcast-slot-select");
    const user = userEvent.setup();
    await user.selectOptions(select, "shift:shift-a");
    await user.type(screen.getByLabelText("Subject"), "Room change");
    await user.type(
      screen.getByLabelText(/Message \(Markdown\)/i),
      "We moved to Room 12.",
    );

    await user.click(screen.getByTestId("broadcast-send"));
    await user.click(await screen.findByTestId("broadcast-confirm"));

    await waitFor(() =>
      expect(api.organizer.sendBroadcast).toHaveBeenCalledWith("evt-1", {
        subject: "Room change",
        body_markdown: "We moved to Room 12.",
        shift_id: "shift-a",
      }),
    );
  });

  it("still sends slot_id for an orientation slot", async () => {
    api.listSlots.mockResolvedValue([SESSION_A1, SESSION_A2, SLOT_B]);
    api.shifts.list.mockResolvedValue([SHIFT_A]);
    api.organizer.broadcastRecipientCount.mockResolvedValue({
      recipient_count: 2,
    });
    api.organizer.sendBroadcast.mockResolvedValueOnce({
      broadcast_id: "bcast5",
      recipient_count: 2,
      sent_at: "2026-07-21T00:00:00Z",
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    const select = await screen.findByTestId("broadcast-slot-select");
    const user = userEvent.setup();
    await user.selectOptions(select, "slot:slot-b");
    await user.type(screen.getByLabelText("Subject"), "Orientation note");
    await user.type(screen.getByLabelText(/Message \(Markdown\)/i), "See you.");

    await user.click(screen.getByTestId("broadcast-send"));
    await user.click(await screen.findByTestId("broadcast-confirm"));

    await waitFor(() =>
      expect(api.organizer.sendBroadcast).toHaveBeenCalledWith("evt-1", {
        subject: "Orientation note",
        body_markdown: "See you.",
        slot_id: "slot-b",
      }),
    );
  });

  it("omits any scope from the payload when the whole event is kept", async () => {
    api.listSlots.mockResolvedValue([SESSION_A1, SESSION_A2, SLOT_B]);
    api.shifts.list.mockResolvedValue([SHIFT_A]);
    api.organizer.broadcastRecipientCount.mockResolvedValue({
      recipient_count: 7,
    });
    api.organizer.sendBroadcast.mockResolvedValueOnce({
      broadcast_id: "bcast3",
      recipient_count: 7,
      sent_at: "2026-07-21T00:00:00Z",
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    await screen.findByTestId("broadcast-slot-select");
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Subject"), "Everyone");
    await user.type(
      screen.getByLabelText(/Message \(Markdown\)/i),
      "Whole-event note.",
    );

    await user.click(screen.getByTestId("broadcast-send"));
    await user.click(await screen.findByTestId("broadcast-confirm"));

    await waitFor(() =>
      expect(api.organizer.sendBroadcast).toHaveBeenCalledWith("evt-1", {
        subject: "Everyone",
        body_markdown: "Whole-event note.",
      }),
    );
  });

  it("hides the picker when the event has only one bookable unit", async () => {
    api.listSlots.mockResolvedValue([SESSION_A1, SESSION_A2]);
    api.shifts.list.mockResolvedValue([SHIFT_A]);
    api.organizer.broadcastRecipientCount.mockResolvedValueOnce({
      recipient_count: 4,
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    await screen.findByTestId("broadcast-recipient-count");
    expect(screen.queryByTestId("broadcast-slot-select")).toBeNull();
  });

  it("degrades to whole-event sending when the unit lists fail to load", async () => {
    api.listSlots.mockRejectedValue(new Error("boom"));
    api.shifts.list.mockRejectedValue(new Error("boom"));
    api.organizer.broadcastRecipientCount.mockResolvedValueOnce({
      recipient_count: 5,
    });
    api.organizer.sendBroadcast.mockResolvedValueOnce({
      broadcast_id: "bcast4",
      recipient_count: 5,
      sent_at: "2026-07-21T00:00:00Z",
    });

    render(
      <BroadcastModal
        open
        onClose={() => {}}
        eventId="evt-1"
        scope="organizer"
      />,
    );

    await screen.findByTestId("broadcast-recipient-count");
    expect(screen.queryByTestId("broadcast-slot-select")).toBeNull();

    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Subject"), "Still works");
    await user.type(screen.getByLabelText(/Message \(Markdown\)/i), "body");
    await user.click(screen.getByTestId("broadcast-send"));
    await user.click(await screen.findByTestId("broadcast-confirm"));

    await waitFor(() =>
      expect(api.organizer.sendBroadcast).toHaveBeenCalledWith("evt-1", {
        subject: "Still works",
        body_markdown: "body",
      }),
    );
  });
});
