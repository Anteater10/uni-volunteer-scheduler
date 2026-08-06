// Grant-on-slot-end (2026-07-24) — ResolveEventModal slot mode.
//
// The modal now works in two scopes:
//   - event mode (no `slot` prop): legacy "End event" — resolves via
//     resolveEvent(eventId, ...)
//   - slot mode (`slot` prop): "End orientation" / "End module slot" —
//     resolves via resolveSlot(slot.id, ...); the orientation variant warns
//     that attended volunteers will be granted orientation credit.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("../../api/roster", () => ({
  resolveEvent: vi.fn().mockResolvedValue({}),
  resolveSlot: vi.fn().mockResolvedValue({}),
}));

vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

import { resolveEvent, resolveSlot } from "../../api/roster";
import ResolveEventModal from "../ResolveEventModal";

beforeEach(() => {
  vi.clearAllMocks();
  resolveEvent.mockResolvedValue({});
  resolveSlot.mockResolvedValue({});
});

const SIGNUPS = [
  { signup_id: "s-1", student_name: "Ada Lovelace", status: "checked_in" },
  { signup_id: "s-2", student_name: "Grace Hopper", status: "confirmed" },
];

function renderModal(props = {}) {
  return render(
    <ResolveEventModal
      eventId="ev-1"
      signups={SIGNUPS}
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
  it("keeps the legacy End event flow via resolveEvent", async () => {
    const user = userEvent.setup();
    renderModal();

    expect(screen.getByText("End event")).toBeInTheDocument();
    await markAllAndSave(user);

    await waitFor(() =>
      expect(resolveEvent).toHaveBeenCalledWith("ev-1", {
        attended: ["s-1"],
        no_show: ["s-2"],
      }),
    );
    expect(resolveSlot).not.toHaveBeenCalled();
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
        eventId="ev-1"
        signups={SIGNUPS}
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
      expect(resolveEvent).toHaveBeenCalledWith("ev-1", {
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
        { signup_id: "s-3", student_name: "Katherine Johnson", status: "checked_in" },
      ],
    });

    expect(screen.getByText("Katherine Johnson")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save/i })).toBeDisabled();

    await user.click(screen.getByLabelText("Mark Katherine Johnson attended"));
    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(resolveEvent).toHaveBeenCalledWith("ev-1", {
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
      signups: [
        SIGNUPS[0],
        { ...SIGNUPS[1], status: "checked_in" },
      ],
    });

    await user.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() =>
      expect(resolveEvent).toHaveBeenCalledWith("ev-1", {
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
    expect(resolveEvent).not.toHaveBeenCalled();
  });

  it("period slot: End module slot title, no credit warning", () => {
    renderModal({ slot: { id: "slot-3", slot_type: "period" } });

    expect(screen.getByText("End module slot")).toBeInTheDocument();
    expect(
      screen.queryByText(/orientation credit/i),
    ).not.toBeInTheDocument();
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
    shift_name: "Tue morning",
    session_name: "Period 1",
    student_name: "Ada Lovelace",
    status: "checked_in",
  },
  {
    shift_signup_id: "c-1",
    signup_id: null,
    slot_id: WED,
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
    expect(resolveEvent).not.toHaveBeenCalled();
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
        },
      ],
    });

    // Prefill: checked_in -> attended, everyone else -> no_show. Save is
    // enabled only when every row has a decision, which is the check that used
    // to pass after one click.
    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => expect(resolveEvent).toHaveBeenCalledTimes(1));
    expect(resolveEvent).toHaveBeenCalledWith("ev-1", {
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
    const allIds = [
      ...resolveEvent.mock.calls,
      ...resolveSlot.mock.calls,
    ].flatMap(([, body]) => [...body.attended, ...body.no_show]);
    expect(allIds.every(Boolean)).toBe(true);
  });

});
