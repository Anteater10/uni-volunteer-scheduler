import React, { useEffect, useMemo, useState } from "react";
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
      (signups || []).filter(
        (s) => s.status === "confirmed" || s.status === "checked_in",
      ),
    [signups],
  );

  const [decisions, setDecisions] = useState({});
  const [saving, setSaving] = useState(false);

  // Prefill from live check-in state (2026-07-24 fix): checked-in volunteers
  // are pre-marked attended, everyone else no-show — ending a slot is one
  // confirmation press, not a per-person marking chore. The organizer can
  // still flip any row before saving.
  useEffect(() => {
    if (!isOpen) return;
    const prefill = {};
    for (const s of unmarked) {
      prefill[s.signup_id] =
        s.status === "checked_in" ? "attended" : "no_show";
    }
    setDecisions(prefill);
  }, [isOpen, unmarked]);

  function mark(signupId, decision) {
    setDecisions((prev) => ({ ...prev, [signupId]: decision }));
  }

  const allMarked =
    unmarked.length > 0 && unmarked.every((s) => decisions[s.signup_id]);

  const isOrientation = slot?.slot_type === "orientation";
  const title = slot
    ? isOrientation
      ? "End orientation"
      : "End module slot"
    : "End event";

  async function handleSave() {
    setSaving(true);
    try {
      const attended = [];
      const no_show = [];
      for (const s of unmarked) {
        if (decisions[s.signup_id] === "attended") {
          attended.push(s.signup_id);
        } else if (decisions[s.signup_id] === "no_show") {
          no_show.push(s.signup_id);
        }
      }
      if (slot) {
        await resolveSlot(slot.id, { attended, no_show });
      } else {
        await resolveEvent(eventId, { attended, no_show });
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
            {unmarked.map((s) => (
              <li
                key={s.signup_id}
                className="flex items-center justify-between py-2 px-2 rounded-lg hover:bg-[var(--color-bg-muted)]"
              >
                <span className="text-sm">{s.student_name}</span>
                <div className="flex gap-1">
                  <button
                    type="button"
                    aria-label={`Mark ${s.student_name} attended`}
                    className={`w-9 h-9 rounded-full flex items-center justify-center text-lg ${
                      decisions[s.signup_id] === "attended"
                        ? "bg-green-500 text-white"
                        : "bg-gray-100"
                    }`}
                    onClick={() => mark(s.signup_id, "attended")}
                  >
                    &#10003;
                  </button>
                  <button
                    type="button"
                    aria-label={`Mark ${s.student_name} no-show`}
                    className={`w-9 h-9 rounded-full flex items-center justify-center text-lg ${
                      decisions[s.signup_id] === "no_show"
                        ? "bg-red-500 text-white"
                        : "bg-gray-100"
                    }`}
                    onClick={() => mark(s.signup_id, "no_show")}
                  >
                    &#10005;
                  </button>
                </div>
              </li>
            ))}
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
