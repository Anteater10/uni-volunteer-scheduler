import React, { useMemo, useState } from "react";
import { resolveEvent } from "../api/roster";
import { Button, Modal } from "./ui";
import { toast } from "../state/toast";

/**
 * Resolve modal: shows remaining confirmed/checked_in signups.
 * Each row gets a toggle: attended (check) or no-show (x).
 * Save is disabled until every row is marked.
 */
export default function ResolveEventModal({
  eventId,
  signups,
  isOpen,
  onClose,
  onResolved,
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

  function mark(signupId, decision) {
    setDecisions((prev) => ({ ...prev, [signupId]: decision }));
  }

  const allMarked =
    unmarked.length > 0 && unmarked.every((s) => decisions[s.signup_id]);

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
      await resolveEvent(eventId, { attended, no_show });
      toast.success("Event resolved successfully.");
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
      title="End event"
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
            {/* TODO(copy) */}
            Mark each remaining signup as attended or no-show.
          </p>
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
