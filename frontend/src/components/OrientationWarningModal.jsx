// src/components/OrientationWarningModal.jsx
//
// Orientation soft-warning modal. Fires when a volunteer selects a period slot
// but no orientation slot, and the backend reports they haven't attended orientation.
//
// NOT a hard block — primary CTA proceeds with signup regardless.
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
 *   open     {boolean}    — controls modal visibility
 *   onYes    {function}   — called when user asserts they have done orientation; signup proceeds
 *   onNo     {function}   — called when user wants to see orientation events instead
 */
export default function OrientationWarningModal({ open, onYes, onNo }) {
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
