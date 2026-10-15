import React, { useMemo, useState } from "react";
import {
  isSlotClosedError,
  isSlotNotStartedError,
  resolveSlot,
} from "../api/roster";
import { Button, Modal } from "./ui";
import { toast } from "../state/toast";

// Rows that never hold a seat are never closed out.
const UNSEATED = ["cancelled", "waitlisted"];

/**
 * Close-out modal: lists every seated booking (pending and confirmed are the
 * same "not checked in" here). Each row gets a toggle: attended (check) or
 * no-show (x). Save is disabled until every row is marked.
 *
 * Two scopes (grant-on-slot-end, 2026-07-24):
 *  - event mode (no `slot` prop): "End event" across the event's slots
 *  - slot mode (`slot` = {id, slot_type}): "End orientation" / "End module
 *    slot" for one slot. Ending an orientation slot grants orientation
 *    credit to every volunteer marked attended — the modal says so, since
 *    that is the moment the credit commitment happens.
 *
 * 2026-10-13 (Kim's report): closing is per slot and can be undone. Event
 * mode only offers slots that are still open and have already started —
 * "End event" on a Tuesday used to mark Thursday's volunteers no-show — and
 * saves with one POST /slots/{id}/resolve per slot, so what the organizer
 * sees listed is exactly what gets closed. "Started" is judged against
 * `openedAt` (ms), which the caller stamps when the End event button is
 * pressed — a render can't read the clock, and judging it once keeps the
 * list from shifting under the organizer's thumb while they mark it.
 *
 * 2026-08-05 shifts: a roster row is one volunteer at one *session*, so a
 * volunteer holding a Tue+Wed shift appears twice and gets two independent
 * decisions — the whole point of per-session close-out is that they can attend
 * Tuesday and no-show Wednesday. Rows are therefore keyed on
 * (booking, session), and the id sent to the server is the shift commitment
 * id when there is one. Before this the modal read `signup_id`, which is null
 * for a shift row, so every shift volunteer collapsed onto one undefined key:
 * marking one name enabled Save, and the request went out with nulls in it.
 */
export default function ResolveEventModal({
  signups,
  isOpen,
  onClose,
  onResolved,
  slot = null,
  openedAt = null,
}) {
  const seated = useMemo(
    () =>
      (signups || [])
        .filter((s) => !UNSEATED.includes(s.status))
        .map((s) => ({
          ...s,
          // Exactly one of the two ids is set on a roster row.
          bookingId: s.shift_signup_id || s.signup_id,
          isShift: Boolean(s.shift_signup_id),
          // One decision per session, so the key has to carry the session too.
          key: `${s.shift_signup_id || s.signup_id}|${s.slot_id || ""}`,
        })),
    [signups],
  );

  const unmarked = useMemo(
    () =>
      slot
        ? seated
        : // Event mode: open slots that have started. A row with no slot
          // can't be closed per slot, so it isn't offered.
          seated.filter(
            (s) =>
              s.slot_id &&
              !s.slot_closed_at &&
              s.slot_time &&
              openedAt !== null &&
              new Date(s.slot_time).getTime() <= openedAt,
          ),
    [seated, slot, openedAt],
  );

  const [decisions, setDecisions] = useState({});
  const [saving, setSaving] = useState(false);

  // Prefill from live check-in state (2026-07-24 fix): checked-in volunteers
  // are pre-marked attended, everyone else no-show — ending a slot is one
  // confirmation press, not a per-person marking chore. The organizer can
  // still flip any row before saving.
  //
  // Prefill runs only on the closed→open transition. In event mode `signups`
  // is live roster data (5s poll + optimistic check-ins), so re-prefilling on
  // every change would silently discard the organizer's manual overrides.
  // A signup that appears while the modal is open stays unmarked, keeping
  // Save disabled until the organizer decides that row.
  //
  // Done during render (React's "adjust state when a prop changes" pattern)
  // rather than in an effect, so the first frame of the open modal already
  // has its decisions and Save is never briefly disabled.
  const [wasOpen, setWasOpen] = useState(false);
  if (isOpen !== wasOpen) {
    setWasOpen(isOpen);
    if (isOpen) {
      // Prefill every seated row; rows event mode doesn't offer are never
      // sent, so the extra keys are harmless.
      const prefill = {};
      for (const s of seated) {
        prefill[s.key] = s.status === "checked_in" ? "attended" : "no_show";
      }
      setDecisions(prefill);
    }
  }

  function mark(key, decision) {
    setDecisions((prev) => ({ ...prev, [key]: decision }));
  }

  const allMarked =
    unmarked.length > 0 && unmarked.every((s) => decisions[s.key]);

  const isOrientation = slot?.slot_type === "orientation";
  // A session belongs to a shift, and closing one out leaves the rest of the
  // shift open — calling it "End module slot" would suggest the whole
  // commitment is done.
  const isSession =
    Boolean(slot) && (signups || []).some((r) => r.shift_signup_id);
  const title = slot
    ? isOrientation
      ? "End orientation"
      : isSession
        ? "End session"
        : "End module slot"
    : "End event";

  /** Split one set of rows into the two id lists the resolve endpoint takes. */
  function split(rows) {
    const attended = [];
    const no_show = [];
    for (const s of rows) {
      if (decisions[s.key] === "attended") {
        attended.push(s.bookingId);
      } else if (decisions[s.key] === "no_show") {
        no_show.push(s.bookingId);
      }
    }
    return { attended, no_show };
  }

  async function handleSave() {
    setSaving(true);
    // Slot mode: every row here belongs to this one slot or session already.
    // Event mode: one close per slot (per session for shifts), which is also
    // what lets a volunteer attend Tuesday and no-show Wednesday.
    const bySlot = new Map();
    for (const s of unmarked) {
      const id = slot ? slot.id : s.slot_id;
      if (!bySlot.has(id)) bySlot.set(id, []);
      bySlot.get(id).push(s);
    }
    let alreadyClosed = 0;
    let notStarted = 0;
    try {
      for (const [slotId, rows] of bySlot) {
        try {
          await resolveSlot(slotId, split(rows));
        } catch (e) {
          // Someone else closed it first (another phone, or a stale list):
          // their close stands. Or the server's clock says it hasn't started
          // (this device's clock ran fast): it stays open. Either way, carry
          // on with the rest.
          if (isSlotClosedError(e)) alreadyClosed += 1;
          else if (isSlotNotStartedError(e)) notStarted += 1;
          else throw e;
        }
      }
      if (alreadyClosed > 0) {
        toast.info(
          alreadyClosed === 1
            ? "That slot was already closed by someone else — reopen it on the roster to change it."
            : `${alreadyClosed} slots were already closed by someone else — reopen them on the roster to change them.`,
        );
      }
      if (notStarted > 0) {
        toast.info(
          notStarted === 1
            ? "That session hasn't started yet — you can close it once it starts."
            : `${notStarted} sessions haven't started yet — you can close them once they start.`,
        );
      }
      if (alreadyClosed === 0 && notStarted === 0) {
        toast.success(slot ? "Slot closed." : "Event closed.");
      }
      if (onClose) onClose();
      setDecisions({});
    } catch (e) {
      toast.error(e?.message || "Close failed");
    } finally {
      setSaving(false);
      // Refresh either way: a failure part-way through event mode may still
      // have closed the slots before it.
      if (onResolved) onResolved();
    }
  }

  return (
    <Modal
      open={isOpen}
      onClose={onClose}
      title={title}
      role="dialog"
      aria-modal="true"
    >
      {unmarked.length === 0 ? (
        <div>
          <p className="text-sm text-[var(--color-fg-muted)] mb-4">
            {slot
              ? "Nobody is booked into this slot, so there is nothing to close."
              : "Nothing to close yet — only sessions that have started can be closed."}
          </p>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      ) : (
        <div>
          <p className="text-sm text-[var(--color-fg-muted)] mb-3">
            Checked-in volunteers are pre-marked attended; everyone else is
            pre-marked no-show. Adjust anyone if needed, then save. Closing
            locks attendance — you can reopen the slot later from the roster
            to fix a mistake.
          </p>
          {isOrientation && (
            <p className="text-sm font-medium text-[var(--color-fg)] mb-3 rounded-lg bg-amber-50 border border-amber-200 px-3 py-2">
              Volunteers marked attended will be granted orientation credit
              for this module. Credits can be revoked individually from the
              admin Orientation credits page.
            </p>
          )}
          <ul className="space-y-2 max-h-[50vh] overflow-y-auto">
            {unmarked.map((s) => {
              // In event mode the same name appears once per session, so the
              // session has to be on the row or the organizer is marking
              // identical-looking lines. Slot mode already has one row each.
              const sessionLabel =
                !slot && s.isShift
                  ? [s.shift_name, s.session_name].filter(Boolean).join(" · ")
                  : null;
              const who = sessionLabel
                ? `${s.student_name} (${sessionLabel})`
                : s.student_name;
              return (
                <li
                  key={s.key}
                  className="flex items-center justify-between py-2 px-2 rounded-lg hover:bg-[var(--color-bg-muted)]"
                >
                  <span className="text-sm">
                    {s.student_name}
                    {sessionLabel ? (
                      <span className="block text-xs text-[var(--color-fg-muted)]">
                        {sessionLabel}
                      </span>
                    ) : null}
                  </span>
                  <div className="flex gap-1">
                    <button
                      type="button"
                      aria-label={`Mark ${who} attended`}
                      className={`w-9 h-9 rounded-full flex items-center justify-center text-lg ${
                        decisions[s.key] === "attended"
                          ? "bg-green-500 text-white"
                          : "bg-gray-100"
                      }`}
                      onClick={() => mark(s.key, "attended")}
                    >
                      &#10003;
                    </button>
                    <button
                      type="button"
                      aria-label={`Mark ${who} no-show`}
                      className={`w-9 h-9 rounded-full flex items-center justify-center text-lg ${
                        decisions[s.key] === "no_show"
                          ? "bg-red-500 text-white"
                          : "bg-gray-100"
                      }`}
                      onClick={() => mark(s.key, "no_show")}
                    >
                      &#10005;
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button onClick={handleSave} disabled={!allMarked || saving}>
              Save
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
}
