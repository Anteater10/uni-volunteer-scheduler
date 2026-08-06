import React, { useEffect, useMemo, useRef, useState } from "react";
import { resolveEvent, resolveSlot } from "../api/roster";
import { Button, Modal } from "./ui";
import { toast } from "../state/toast";

/**
 * Resolve modal: shows remaining confirmed/checked_in signups.
 * Each row gets a toggle: attended (check) or no-show (x).
 * Save is disabled until every row is marked.
 *
 * Two scopes (grant-on-slot-end, 2026-07-24):
 *  - event mode (no `slot` prop): legacy "End event" across all slots
 *  - slot mode (`slot` = {id, slot_type}): "End orientation" / "End module
 *    slot" for one slot. Ending an orientation slot grants orientation
 *    credit to every volunteer marked attended — the modal says so, since
 *    that is the moment the credit commitment happens.
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
  eventId,
  signups,
  isOpen,
  onClose,
  onResolved,
  slot = null,
}) {
  const unmarked = useMemo(
    () =>
      (signups || [])
        .filter((s) => s.status === "confirmed" || s.status === "checked_in")
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
  const wasOpenRef = useRef(false);
  useEffect(() => {
    if (isOpen && !wasOpenRef.current) {
      const prefill = {};
      for (const s of unmarked) {
        prefill[s.key] = s.status === "checked_in" ? "attended" : "no_show";
      }
      setDecisions(prefill);
    }
    wasOpenRef.current = isOpen;
  }, [isOpen, unmarked]);

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

  /** Split one set of rows into the two id lists the resolve endpoints take. */
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
    try {
      if (slot) {
        // Every row here belongs to this one slot or session already.
        await resolveSlot(slot.id, split(unmarked));
      } else {
        // Event mode. `POST /events/{id}/resolve` applies one decision to a
        // commitment's whole shift, which cannot express "attended Tuesday,
        // no-show Wednesday" — so where shift rows are involved we close out
        // one session at a time and leave the event call for the orientation
        // and legacy rows. The per-session calls skip sessions that already
        // hold a terminal record, so a failure part-way through is safe to
        // retry rather than something the organizer has to unpick.
        const bySession = new Map();
        const plain = [];
        for (const s of unmarked) {
          if (s.isShift && s.slot_id) {
            if (!bySession.has(s.slot_id)) bySession.set(s.slot_id, []);
            bySession.get(s.slot_id).push(s);
          } else {
            plain.push(s);
          }
        }
        for (const [slotId, rows] of bySession) {
          await resolveSlot(slotId, split(rows));
        }
        if (plain.length > 0 || bySession.size === 0) {
          await resolveEvent(eventId, split(plain));
        }
      }
      toast.success(
        slot ? "Slot resolved successfully." : "Event resolved successfully.",
      );
      if (onResolved) onResolved();
      if (onClose) onClose();
      setDecisions({});
    } catch (e) {
      toast.error(e?.message || "Resolve failed");
    } finally {
      setSaving(false);
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
            All attendees marked.
          </p>
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      ) : (
        <div>
          <p className="text-sm text-[var(--color-fg-muted)] mb-3">
            Checked-in volunteers are pre-marked attended; everyone else is
            pre-marked no-show. Adjust anyone if needed, then save.
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
