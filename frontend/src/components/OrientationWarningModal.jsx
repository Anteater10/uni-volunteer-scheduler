// src/components/OrientationWarningModal.jsx
//
// Orientation soft-warning modal. Fires when a volunteer selects a period slot
// but no orientation slot, and the backend reports they haven't attended orientation.
//
// NOT a hard block — "Yes" proceeds with signup regardless.

import React from "react";
import { Modal, Button } from "./ui";

/**
 * Props:
 *   open     {boolean}    — controls modal visibility
 *   onYes    {function}   — called when user confirms they have completed orientation
 *   onNo     {function}   — called when user wants to see orientation slots instead
 */
export default function OrientationWarningModal({ open, onYes, onNo }) {
  return (
    <Modal
      open={open}
      onClose={onNo}
      title="Have you completed orientation?"
    >
      <p className="text-sm text-[var(--color-fg)]">
        You selected a period slot but no orientation slot. Have you already
        attended orientation for this module?
      </p>
      <div className="flex flex-col gap-2 mt-4">
        <Button
          type="button"
          variant="primary"
          className="w-full min-h-11"
          onClick={onYes}
        >
          Yes, I have completed orientation
        </Button>
        <Button
          type="button"
          variant="secondary"
          className="w-full min-h-11"
          onClick={onNo}
        >
          No — show me orientation slots
        </Button>
      </div>
    </Modal>
  );
}
