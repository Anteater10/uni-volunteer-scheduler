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

describe("BroadcastModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
});
