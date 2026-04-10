// src/components/SignupSuccessCard.jsx
//
// Post-signup success popup card shown as a modal overlay.
// Displays "Check your email!" with the volunteer's name and the list of
// slots they signed up for. Dismissing resets the parent form.

import React from "react";
import { Modal, Button } from "./ui";

/**
 * Format a slot for display in the success list.
 */
function formatSlotLine(slot) {
  if (!slot) return "";
  const date = slot.date
    ? new Date(slot.date.includes("T") ? slot.date : `${slot.date}T00:00:00`).toLocaleDateString(
        "en-US",
        { weekday: "short", month: "short", day: "numeric" }
      )
    : "";
  const start = slot.start_time
    ? new Date(
        slot.start_time.includes("Z") || slot.start_time.includes("+")
          ? slot.start_time
          : `${slot.start_time}Z`
      ).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : "";
  const end = slot.end_time
    ? new Date(
        slot.end_time.includes("Z") || slot.end_time.includes("+")
          ? slot.end_time
          : `${slot.end_time}Z`
      ).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
    : "";

  const timeRange = start && end ? `${start}–${end}` : start;
  return [date, timeRange, slot.location].filter(Boolean).join(", ");
}

/**
 * Props:
 *   open          {boolean}    — controls modal visibility
 *   volunteerName {string}     — first name of the volunteer
 *   slots         {object[]}   — array of slot objects (date, start_time, end_time, location)
 *   onDismiss     {function}   — called when user clicks "Done"
 */
export default function SignupSuccessCard({ open, volunteerName, slots, onDismiss }) {
  return (
    <Modal open={open} onClose={onDismiss} title="Check your email!">
      <p className="text-sm text-[var(--color-fg)]">
        Thanks,{" "}
        <span className="font-semibold">{volunteerName || "volunteer"}</span>! We
        sent a confirmation link to your email.
      </p>

      {slots && slots.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-[var(--color-fg-muted)] mb-2">
            You signed up for:
          </p>
          <ul className="flex flex-col gap-1">
            {slots.map((slot) => (
              <li
                key={slot.id || slot.start_time}
                className="text-sm text-[var(--color-fg)] bg-[var(--color-surface)] rounded-lg px-3 py-2"
              >
                {formatSlotLine(slot)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <Button
        type="button"
        variant="primary"
        className="w-full min-h-11 mt-5"
        onClick={onDismiss}
      >
        Done
      </Button>
    </Modal>
  );
}
