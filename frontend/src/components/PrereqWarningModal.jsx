import React from "react";
import { useNavigate } from "react-router-dom";
import { Modal, Button } from "./ui";

// TODO(copy): finalize wording with Sci Trek
export default function PrereqWarningModal({
  open,
  onClose,
  missing,
  nextSlot,
  onSignUpAnyway,
  isSubmitting,
}) {
  const navigate = useNavigate();

  if (!open) return null;

  return (
    <Modal open={open} onClose={onClose} title="Prerequisites not met">
      {/* TODO(copy): finalize prerequisite warning copy */}
      <p className="text-sm">
        You haven't completed:{" "}
        <strong>{(missing || []).join(", ")}</strong>.
      </p>
      <p className="text-sm text-[var(--color-fg-muted)] mt-1">
        We recommend finishing orientation first.
      </p>
      <div className="flex justify-end gap-2 mt-4">
        {nextSlot && (
          <Button
            type="button"
            onClick={() =>
              navigate(
                `/events/${nextSlot.event_id}?slot=${nextSlot.slot_id}`,
              )
            }
          >
            Attend orientation first
          </Button>
        )}
        <Button
          type="button"
          variant={nextSlot ? "secondary" : "primary"}
          onClick={onSignUpAnyway}
          disabled={isSubmitting}
        >
          Sign up anyway
        </Button>
      </div>
    </Modal>
  );
}
