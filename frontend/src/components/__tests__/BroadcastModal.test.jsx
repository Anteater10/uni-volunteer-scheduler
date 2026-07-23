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

const SLOT_A = {
  id: "slot-a",
  slot_type: "period",
  date: "2026-04-20",
  start_time: "2026-04-20T16:00:00",
  end_time: "2026-04-20T18:00:00",
  location: "Room 12",
  capacity: 10,
  current_count: 3,
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
    // Default: no slots → picker hidden, legacy all-event behavior.
    api.listSlots.mockResolvedValue([]);
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

  it("shows a slot picker defaulting to All slots when the event has multiple slots", async () => {
    api.listSlots.mockResolvedValue([SLOT_A, SLOT_B]);
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
    expect(select.value).toBe("");
    expect(select.options[0].textContent).toMatch(/all slots/i);
    // Slots are labeled by type + date/time since they carry no name.
    expect(select.options[1].textContent).toMatch(/period/i);
    expect(select.options[2].textContent).toMatch(/orientation/i);
    // Default fetch is the whole-event count — same call shape as before.
    expect(api.organizer.broadcastRecipientCount).toHaveBeenCalledWith("evt-1");
  });

  it("refetches the recipient count when a slot is chosen", async () => {
    api.listSlots.mockResolvedValue([SLOT_A, SLOT_B]);
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
    await user.selectOptions(select, "slot-a");

    await waitFor(() =>
      expect(api.organizer.broadcastRecipientCount).toHaveBeenLastCalledWith(
        "evt-1",
        { slot_id: "slot-a" },
      ),
    );
    const pill = await screen.findByTestId("broadcast-recipient-count");
    await waitFor(() => expect(pill.textContent).toMatch(/3 volunteers/i));
  });

  it("sends slot_id in the payload when a slot is selected", async () => {
    api.listSlots.mockResolvedValue([SLOT_A, SLOT_B]);
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
    await user.selectOptions(select, "slot-a");
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
        slot_id: "slot-a",
      }),
    );
  });

  it("omits slot_id from the payload when All slots is kept", async () => {
    api.listSlots.mockResolvedValue([SLOT_A, SLOT_B]);
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

  it("hides the slot picker for single-slot events", async () => {
    api.listSlots.mockResolvedValue([SLOT_A]);
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

  it("degrades to all-slots sending when the slot list fails to load", async () => {
    api.listSlots.mockRejectedValue(new Error("boom"));
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
