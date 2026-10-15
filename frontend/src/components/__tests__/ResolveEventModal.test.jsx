// Grant-on-slot-end (2026-07-24) + attendance lock per slot (2026-10-13).
//
// The modal works in two scopes:
//   - event mode (no `slot` prop): "End event" — closes every OPEN slot that
//     has already started, one POST /slots/{id}/resolve per slot. Future
//     sessions are left alone: "End event" on a Tuesday used to mark
//     Thursday's volunteers no-show.
//   - slot mode (`slot` prop): "End orientation" / "End module slot" —
//     resolves via resolveSlot(slot.id, ...); the orientation variant warns
//     that attended volunteers will be granted orientation credit.
//
// Pending and confirmed are the same "not checked in" here: both are listed
// and both are pre-marked no-show.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// The real SLOT_CLOSED check, so these tests exercise the actual error shape.
vi.mock("../../api/roster", async (importOriginal) => ({
  isSlotClosedError: (await importOriginal()).isSlotClosedError,
  isSlotNotStartedError: (await importOriginal()).isSlotNotStartedError,
  resolveSlot: vi.fn().mockResolvedValue({}),
}));

vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { resolveSlot } from "../../api/roster";
import { toast } from "../../state/toast";
import ResolveEventModal from "../ResolveEventModal";

beforeEach(() => {
  vi.clearAllMocks();
  resolveSlot.mockResolvedValue({});
});

// Far enough either side of "now" that the test never depends on the clock.
const PAST = "2020-01-06T17:00:00Z";
const PAST_2 = "2020-01-07T17:00:00Z";
const FUTURE = "2099-01-06T17:00:00Z";

const ORIENT = "slot-orient";

const SIGNUPS = [
  { signup_id: "s-1", student_name: "Ada Lovelace", status: "checked_in", slot_id: ORIENT, slot_time: PAST },
  { signup_id: "s-2", student_name: "Grace Hopper", status: "confirmed", slot_id: ORIENT, slot_time: PAST },
];

function slotClosed(code = "SLOT_CLOSED") {
  const err = new Error("This slot is closed. Reopen it to change attendance.");
  err.status = 409;
  // The real body: main.py's global handler flattens every HTTPException to
  // {error, code, detail: "<message>"}, so the code is top-level.
  err.response = {
    status: 409,
    data: { error: "http_409", code, detail: err.message },
  };
  return err;
}

// What the roster page stamps when End event is pressed.
const NOW = Date.now();

function renderModal(props = {}) {
  return render(
    <ResolveEventModal
      signups={SIGNUPS}
      openedAt={NOW}
      isOpen
      onClose={() => {}}
      onResolved={() => {}}
      {...props}
    />,
  );
}

async function markAllAndSave(user) {
  await user.click(screen.getByLabelText("Mark Ada Lovelace attended"));
  await user.click(screen.getByLabelText("Mark Grace Hopper no-show"));
  await user.click(screen.getByRole("button", { name: /save/i }));
}

describe("event mode (no slot prop)", () => {
  it("closes each started slot with its own resolveSlot call", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onResolved = vi.fn();
    renderModal({ onClose, onResolved });

    expect(screen.getByText("End event")).toBeInTheDocument();
    // The copy says the close can be undone.
    expect(screen.getByText(/reopen the slot later/i)).toBeInTheDocument();
    await markAllAndSave(user);

    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith(ORIENT, {
        attended: ["s-1"],
        no_show: ["s-2"],
      }),
    );
    expect(resolveSlot).toHaveBeenCalledTimes(1);
    expect(toast.success).toHaveBeenCalledWith("Event closed.");
    expect(onClose).toHaveBeenCalled();
    expect(onResolved).toHaveBeenCalled();
  });

  it("never offers a session that hasn't started yet", async () => {
    const user = userEvent.setup();
    renderModal({
      signups: [
        ...SIGNUPS,
        { signup_id: "s-thu", student_name: "Thursday Person", status: "confirmed", slot_id: "slot-thu", slot_time: FUTURE },
      ],
    });

    expect(screen.queryByText("Thursday Person")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(1));
    expect(resolveSlot).not.toHaveBeenCalledWith("slot-thu", expect.anything());
  });

  it("skips slots that are already closed, and rows with no slot or time", async () => {
    const user = userEvent.setup();
    renderModal({
      signups: [
        ...SIGNUPS,
        { signup_id: "s-c", student_name: "Closed Person", status: "attended", slot_id: "slot-closed", slot_time: PAST, slot_closed_at: PAST_2 },
        { signup_id: "s-n", student_name: "No Slot", status: "confirmed", slot_id: null, slot_time: PAST },
        { signup_id: "s-t", student_name: "No Time", status: "confirmed", slot_id: "slot-x", slot_time: null },
      ],
    });

    expect(screen.queryByText("Closed Person")).not.toBeInTheDocument();
    expect(screen.queryByText("No Slot")).not.toBeInTheDocument();
    expect(screen.queryByText("No Time")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(1));
    expect(resolveSlot).toHaveBeenCalledWith(ORIENT, expect.anything());
  });

  it("mixes future, closed and started slots: only the started open ones close", async () => {
    const user = userEvent.setup();
    renderModal({
      signups: [
        { signup_id: "a", student_name: "Tue One", status: "pending", slot_id: "tue-1", slot_time: PAST },
        { signup_id: "b", student_name: "Tue Two", status: "checked_in", slot_id: "tue-2", slot_time: PAST_2 },
        { signup_id: "c", student_name: "Tue Closed", status: "no_show", slot_id: "tue-3", slot_time: PAST, slot_closed_at: PAST_2 },
        { signup_id: "d", student_name: "Thu", status: "confirmed", slot_id: "thu-1", slot_time: FUTURE },
      ],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(2));
    expect(resolveSlot).toHaveBeenCalledWith("tue-1", { attended: [], no_show: ["a"] });
    expect(resolveSlot).toHaveBeenCalledWith("tue-2", { attended: ["b"], no_show: [] });
  });

  it("says there is nothing to close yet when no session has started", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderModal({
      onClose,
      signups: [
        { signup_id: "d", student_name: "Thu", status: "confirmed", slot_id: "thu-1", slot_time: FUTURE },
      ],
    });

    expect(
      screen.getByText(
        "Nothing to close yet — only sessions that have started can be closed.",
      ),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
    expect(resolveSlot).not.toHaveBeenCalled();
  });

  it("offers nothing when the caller gave no open time", () => {
    renderModal({ openedAt: undefined });
    expect(screen.getByText(/Nothing to close yet/)).toBeInTheDocument();
  });

  it("judges 'started' against the open time, not the clock", () => {
    // A session at 10:00 opened at 09:59 isn't offered, at 10:00 it is.
    const at = new Date(PAST).getTime();
    const { rerender } = renderModal({ openedAt: at - 60_000 });
    expect(screen.queryByText("Ada Lovelace")).not.toBeInTheDocument();
    rerender(
      <ResolveEventModal signups={SIGNUPS} openedAt={at} isOpen onClose={() => {}} />,
    );
    expect(screen.getByText("Ada Lovelace")).toBeInTheDocument();
  });

  it("is prefilled on the very first render, with Save already enabled", () => {
    renderModal();
    expect(screen.getByRole("button", { name: /save/i })).toBeEnabled();
    expect(screen.getByLabelText("Mark Ada Lovelace attended").className).toMatch(/bg-green-500/);
  });

  it("treats an empty or missing roster as nothing to close", () => {
    renderModal({ signups: undefined });
    expect(screen.getByText(/Nothing to close yet/)).toBeInTheDocument();
  });

  it("carries on past a slot someone else already closed", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    resolveSlot
      .mockRejectedValueOnce(slotClosed())
      .mockResolvedValueOnce({});
    renderModal({
      onClose,
      signups: [
        { signup_id: "a", student_name: "Tue One", status: "confirmed", slot_id: "tue-1", slot_time: PAST },
        { signup_id: "b", student_name: "Tue Two", status: "confirmed", slot_id: "tue-2", slot_time: PAST },
      ],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(2));
    expect(toast.info).toHaveBeenCalledWith(
      expect.stringMatching(/already closed by someone else/),
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("counts several slots that were already closed", async () => {
    const user = userEvent.setup();
    resolveSlot.mockRejectedValue(slotClosed());
    renderModal({
      signups: [
        { signup_id: "a", student_name: "Tue One", status: "confirmed", slot_id: "tue-1", slot_time: PAST },
        { signup_id: "b", student_name: "Tue Two", status: "confirmed", slot_id: "tue-2", slot_time: PAST },
      ],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        "2 slots were already closed by someone else — reopen them on the roster to change them.",
      ),
    );
  });

  it("leaves sessions the server says haven't started open, and says so", async () => {
    // This device's clock ran ahead of the server's.
    const user = userEvent.setup();
    const onClose = vi.fn();
    resolveSlot
      .mockRejectedValueOnce(slotClosed("SLOT_NOT_STARTED"))
      .mockRejectedValueOnce(slotClosed("SLOT_NOT_STARTED"))
      .mockRejectedValueOnce(slotClosed("SLOT_CLOSED"));
    renderModal({
      onClose,
      signups: [
        { signup_id: "a", student_name: "One", status: "confirmed", slot_id: "s-1", slot_time: PAST },
        { signup_id: "b", student_name: "Two", status: "confirmed", slot_id: "s-2", slot_time: PAST },
        { signup_id: "c", student_name: "Three", status: "confirmed", slot_id: "s-3", slot_time: PAST },
      ],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(3));
    expect(toast.info).toHaveBeenCalledWith(
      "2 sessions haven't started yet — you can close them once they start.",
    );
    expect(toast.info).toHaveBeenCalledWith(
      "That slot was already closed by someone else — reopen it on the roster to change it.",
    );
    expect(toast.success).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it("says a single slot hasn't started yet", async () => {
    const user = userEvent.setup();
    resolveSlot.mockRejectedValueOnce(slotClosed("SLOT_NOT_STARTED"));
    renderModal({ slot: { id: "slot-9", slot_type: "orientation" } });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        "That session hasn't started yet — you can close it once it starts.",
      ),
    );
    expect(toast.success).not.toHaveBeenCalled();
  });

  it("stops on any other failure, keeps the modal open, and still refreshes", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const onResolved = vi.fn();
    resolveSlot.mockRejectedValueOnce(slotClosed("SOMETHING_ELSE"));
    renderModal({
      onClose,
      onResolved,
      signups: [
        { signup_id: "a", student_name: "Tue One", status: "confirmed", slot_id: "tue-1", slot_time: PAST },
        { signup_id: "b", student_name: "Tue Two", status: "confirmed", slot_id: "tue-2", slot_time: PAST },
      ],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalled());
    expect(resolveSlot).toHaveBeenCalledTimes(1);
    expect(onClose).not.toHaveBeenCalled();
    // The slots before the failure may have closed; the roster must show it.
    expect(onResolved).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: /save/i })).toBeEnabled();
  });

  it("falls back to a generic message for an error without one", async () => {
    const user = userEvent.setup();
    resolveSlot.mockRejectedValueOnce({});
    renderModal({ onClose: undefined, onResolved: undefined });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("Close failed"));
  });
});

describe("who is listed", () => {
  it("lists pending exactly like confirmed and leaves out waitlisted/cancelled", async () => {
    const user = userEvent.setup();
    renderModal({
      slot: { id: ORIENT, slot_type: "orientation" },
      signups: [
        ...SIGNUPS,
        { signup_id: "s-3", student_name: "Parker Unconfirmed", status: "pending", slot_id: ORIENT },
        { signup_id: "s-4", student_name: "Wait Listed", status: "waitlisted", slot_id: ORIENT },
        { signup_id: "s-5", student_name: "Can Celled", status: "cancelled", slot_id: ORIENT },
      ],
    });

    expect(screen.getByText("Parker Unconfirmed")).toBeInTheDocument();
    expect(screen.queryByText("Wait Listed")).not.toBeInTheDocument();
    expect(screen.queryByText("Can Celled")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith(ORIENT, {
        attended: ["s-1"],
        no_show: ["s-2", "s-3"],
      }),
    );
  });
});

describe("prefill from check-in state (2026-07-24 fix)", () => {
  it("pre-marks checked_in as attended, others as no-show — save works with zero clicks", async () => {
    const user = userEvent.setup();
    renderModal({ slot: { id: "slot-9", slot_type: "orientation" } });

    // No manual marking: the organizer only presses Save.
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith("slot-9", {
        attended: ["s-1"],
        no_show: ["s-2"],
      }),
    );
    expect(toast.success).toHaveBeenCalledWith("Slot closed.");
  });

  it("organizer can override a prefilled decision before saving", async () => {
    const user = userEvent.setup();
    renderModal({ slot: { id: "slot-9", slot_type: "orientation" } });

    await user.click(screen.getByLabelText("Mark Ada Lovelace no-show"));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith("slot-9", {
        attended: [],
        no_show: ["s-1", "s-2"],
      }),
    );
  });
});

describe("live roster updates while open (poll/optimistic refresh)", () => {
  function rerenderModal(rerender, props = {}) {
    rerender(
      <ResolveEventModal
        signups={SIGNUPS}
        openedAt={NOW}
        isOpen
        onClose={() => {}}
        onResolved={() => {}}
        {...props}
      />,
    );
  }

  it("preserves manual overrides when the signups prop refreshes", async () => {
    const user = userEvent.setup();
    const { rerender } = renderModal();

    await user.click(screen.getByLabelText("Mark Ada Lovelace no-show"));

    // Roster poll / optimistic check-in elsewhere: same rows, new references.
    rerenderModal(rerender, { signups: SIGNUPS.map((s) => ({ ...s })) });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith(ORIENT, {
        attended: [],
        no_show: ["s-1", "s-2"],
      }),
    );
  });

  it("leaves a mid-session walk-in unmarked and disables Save until decided", async () => {
    const user = userEvent.setup();
    const { rerender } = renderModal();

    rerenderModal(rerender, {
      signups: [
        ...SIGNUPS,
        { signup_id: "s-3", student_name: "Katherine Johnson", status: "checked_in", slot_id: ORIENT, slot_time: PAST },
      ],
    });

    expect(screen.getByText("Katherine Johnson")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();

    await user.click(screen.getByLabelText("Mark Katherine Johnson attended"));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith(ORIENT, {
        attended: ["s-1", "s-3"],
        no_show: ["s-2"],
      }),
    );
  });

  it("re-prefills from current check-in state when reopened after closing", async () => {
    const user = userEvent.setup();
    const { rerender } = renderModal();

    await user.click(screen.getByLabelText("Mark Ada Lovelace no-show"));
    rerenderModal(rerender, { isOpen: false });

    // Grace checked in while the modal was closed.
    rerenderModal(rerender, {
      signups: [SIGNUPS[0], { ...SIGNUPS[1], status: "checked_in" }],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith(ORIENT, {
        attended: ["s-1", "s-2"],
        no_show: [],
      }),
    );
  });
});

describe("slot mode", () => {
  it("orientation slot: End orientation title, credit warning, resolveSlot", async () => {
    const user = userEvent.setup();
    renderModal({ slot: { id: "slot-9", slot_type: "orientation" } });

    expect(screen.getByText("End orientation")).toBeInTheDocument();
    expect(
      screen.getByText(/will be granted orientation credit/i),
    ).toBeInTheDocument();

    await markAllAndSave(user);

    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith("slot-9", {
        attended: ["s-1"],
        no_show: ["s-2"],
      }),
    );
    expect(resolveSlot).toHaveBeenCalledTimes(1);
  });

  it("period slot: End module slot title, no credit warning", () => {
    renderModal({ slot: { id: "slot-3", slot_type: "period" } });

    expect(screen.getByText("End module slot")).toBeInTheDocument();
    expect(
      screen.queryByText(/orientation credit/i),
    ).not.toBeInTheDocument();
  });

  it("offers a slot regardless of its start time — the organizer chose it", () => {
    renderModal({
      slot: { id: "thu-1", slot_type: "period" },
      signups: [
        { signup_id: "d", student_name: "Thu", status: "confirmed", slot_id: "thu-1", slot_time: FUTURE },
      ],
    });
    expect(screen.getByText("Thu")).toBeInTheDocument();
  });

  it("says a slot with nobody booked has nothing to close", () => {
    renderModal({
      slot: { id: "slot-3", slot_type: "period" },
      signups: [
        { signup_id: "w", student_name: "Wait", status: "waitlisted", slot_id: "slot-3" },
      ],
    });
    expect(
      screen.getByText("Nobody is booked into this slot, so there is nothing to close."),
    ).toBeInTheDocument();
  });

  it("works without onClose/onResolved and with no signups at all", async () => {
    const user = userEvent.setup();
    const { unmount } = renderModal({
      slot: { id: "slot-3", slot_type: "period" },
      signups: undefined,
    });
    expect(screen.getByText(/Nobody is booked/)).toBeInTheDocument();
    unmount();

    renderModal({
      slot: { id: "slot-9", slot_type: "orientation" },
      onClose: undefined,
      onResolved: undefined,
    });
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith("Slot closed."));
  });

  it("reports a slot that was closed elsewhere first", async () => {
    const user = userEvent.setup();
    resolveSlot.mockRejectedValueOnce(slotClosed());
    renderModal({ slot: { id: "slot-9", slot_type: "orientation" } });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(toast.info).toHaveBeenCalledWith(
        "That slot was already closed by someone else — reopen it on the roster to change it.",
      ),
    );
  });
});

// ---------------------------------------------------------------------------
// 2026-08-05 shifts — close-out is per (commitment, session).
//
// A roster row is one volunteer at one session, and a shift row carries
// `shift_signup_id` with `signup_id` null. The modal read `signup_id`, so every
// shift volunteer collapsed onto one undefined key: marking one name enabled
// Save for the whole list, and the request went out with nulls in it. Nothing
// caught it because every fixture here was signup-shaped.
// ---------------------------------------------------------------------------

const TUE = "slot-tue";
const WED = "slot-wed";

// Ada holds a Tue+Wed shift, so she appears twice. Grace is orientation.
const SHIFT_ROWS = [
  {
    shift_signup_id: "c-1",
    signup_id: null,
    slot_id: TUE,
    slot_time: PAST,
    shift_name: "Tue morning",
    session_name: "Period 1",
    student_name: "Ada Lovelace",
    status: "checked_in",
  },
  {
    shift_signup_id: "c-1",
    signup_id: null,
    slot_id: WED,
    slot_time: PAST_2,
    shift_name: "Tue morning",
    session_name: "Period 2",
    student_name: "Ada Lovelace",
    status: "confirmed",
  },
];

describe("shift close-out", () => {
  it("session mode sends commitment ids for that session only", async () => {
    const user = userEvent.setup();
    renderModal({
      signups: [SHIFT_ROWS[0]],
      slot: { id: TUE, slot_type: "period" },
    });

    // Not "End module slot": the rest of the shift stays open.
    expect(screen.getByText("End session")).toBeInTheDocument();
    await user.click(screen.getByLabelText("Mark Ada Lovelace attended"));
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() =>
      expect(resolveSlot).toHaveBeenCalledWith(TUE, {
        attended: ["c-1"],
        no_show: [],
      }),
    );
    expect(resolveSlot).toHaveBeenCalledTimes(1);
  });

  it("gives one volunteer independent decisions per session", async () => {
    const user = userEvent.setup();
    renderModal({ signups: SHIFT_ROWS });

    // Both of Ada's sessions are listed, distinguishable by name.
    expect(screen.getByText("Tue morning · Period 1")).toBeInTheDocument();
    expect(screen.getByText("Tue morning · Period 2")).toBeInTheDocument();

    await user.click(
      screen.getByLabelText("Mark Ada Lovelace (Tue morning · Period 1) attended"),
    );
    await user.click(
      screen.getByLabelText("Mark Ada Lovelace (Tue morning · Period 2) no-show"),
    );
    await user.click(screen.getByRole("button", { name: /save/i }));

    // Attended Tuesday, no-show Wednesday — the reason close-out is per
    // session at all. One event-wide call could only say one of the two.
    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(2));
    expect(resolveSlot).toHaveBeenCalledWith(TUE, {
      attended: ["c-1"],
      no_show: [],
    });
    expect(resolveSlot).toHaveBeenCalledWith(WED, {
      attended: [],
      no_show: ["c-1"],
    });
  });

  it("End event handles a mixed roster without sending nulls", async () => {
    const user = userEvent.setup();
    renderModal({
      signups: [
        ...SHIFT_ROWS,
        {
          signup_id: "s-9",
          student_name: "Grace Hopper",
          status: "confirmed",
          slot_id: "slot-orient",
          slot_time: PAST,
        },
      ],
    });

    // Prefill: checked_in -> attended, everyone else -> no_show. Save is
    // enabled only when every row has a decision, which is the check that used
    // to pass after one click.
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(resolveSlot).toHaveBeenCalledTimes(3));
    expect(resolveSlot).toHaveBeenCalledWith("slot-orient", {
      attended: [],
      no_show: ["s-9"],
    });
    expect(resolveSlot).toHaveBeenCalledWith(TUE, {
      attended: ["c-1"],
      no_show: [],
    });
    expect(resolveSlot).toHaveBeenCalledWith(WED, {
      attended: [],
      no_show: ["c-1"],
    });
    const allIds = resolveSlot.mock.calls.flatMap(([, body]) => [
      ...body.attended,
      ...body.no_show,
    ]);
    expect(allIds.every(Boolean)).toBe(true);
  });

  it("labels a shift row with only one of shift/session names", () => {
    renderModal({
      signups: [{ ...SHIFT_ROWS[0], session_name: null }],
    });
    expect(screen.getByText("Tue morning")).toBeInTheDocument();
  });
});
