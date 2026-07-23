// src/components/OrientationWarningModal.jsx
//
// Orientation modal, two variants:
//
// required (default when the event offers orientation sessions):
//   The server enforces that un-oriented volunteers include an orientation
//   session in their signup (422 ORIENTATION_REQUIRED). No bypass — the
//   only CTA steers back to the schedule to add an orientation session.
//
// advisory (event has NO orientation slots — requirement unfulfillable here,
// server exempts it; organizers can vouch at the door):
//   Soft warning; primary CTA proceeds with signup regardless.
//
// Modal primitive (./ui/Modal.jsx) provides:
//   - role="dialog" + aria-modal="true"
//   - Focus trap via useFocusTrap
//   - ESC key close
//   - Restore focus to trigger on close

import React from "react";
import { Modal, Button } from "./ui";

/**
 * Props:
 *   open              {boolean}  — controls modal visibility
 *   required          {boolean}  — hard-requirement variant (no bypass)
 *   onPickOrientation {function} — required variant: back to schedule to add
 *                                  an orientation session
 *   onYes             {function} — advisory variant: proceed with signup
 *   onNo              {function} — advisory variant / close: see orientation
 *                                  events instead
 */
export default function OrientationWarningModal({
  open,
  required = false,
  onPickOrientation,
  onYes,
  onNo,
}) {
  if (required) {
    return (
      <Modal
        open={open}
        onClose={onNo}
        title="Orientation is part of your first signup"
      >
        <p className="text-sm text-[var(--color-fg)]">
          Looks like you haven't completed a Sci Trek orientation for this
          module yet. Your signup needs to include an orientation session —
          pick one from the schedule and it'll be added alongside the shifts
          you already selected.
        </p>
        <div className="flex flex-col gap-2 mt-4">
          <Button
            type="button"
            variant="primary"
            className="w-full min-h-11"
            onClick={onPickOrientation}
          >
            Pick an orientation session
          </Button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal
      open={open}
      onClose={onNo}
      title="Have you done a Sci Trek orientation?"
    >
      <p className="text-sm text-[var(--color-fg)]">
        This event has period slots but no orientation slot. New volunteers
        need to complete an orientation with Sci Trek before working a period
        slot.
      </p>
      <div className="flex flex-col gap-2 mt-4">
        <Button
          type="button"
          variant="primary"
          className="w-full min-h-11"
          onClick={onYes}
        >
          {"I've done orientation — continue"}
        </Button>
        <Button
          type="button"
          variant="secondary"
          className="w-full min-h-11"
          onClick={onNo}
        >
          {"I haven't — show me orientation events"}
        </Button>
      </div>
    </Modal>
  );
}
