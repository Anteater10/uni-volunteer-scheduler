// src/components/SignupSuccessCard.jsx
//
// Post-signup success popup card shown as a modal overlay.
// Displays "Check your email!" with the volunteer's name and the list of
// slots they signed up for. Dismissing resets the parent form.
//
// PART-13 surface B (Phase 15-05): when both `event` and `slot` props are
// supplied (typically from ConfirmSignupPage after the magic-link confirm
// resolves with the relevant slot), an "Add to calendar" PRIMARY button
// appears that downloads a .ics file via the shared calendar util.

import React from "react";
import { Modal, Button } from "./ui";
import { downloadIcs, buildGoogleCalendarUrl } from "../lib/calendar";
import { toast } from "../state/toast";

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
 *   event         {object?}    — OPTIONAL. When provided alongside `slot`, enables
 *                                the Add-to-Calendar PRIMARY button (PART-13 surface B).
 *   slot          {object?}    — OPTIONAL. The single slot to encode into .ics.
 *                                Distinct from `slots` (the display list) so callers
 *                                can show multiple confirmed slots but only download
 *                                a calendar entry for the one most-recently confirmed.
 */
export default function SignupSuccessCard({
  open,
  volunteerName,
  slots,
  onDismiss,
  event,
  slot,
}) {
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
            {slots.map((s) => (
              <li
                key={s.id || s.start_time}
                className="text-sm text-[var(--color-fg)] bg-[var(--color-surface)] rounded-lg px-3 py-2"
              >
                {formatSlotLine(s)}
              </li>
            ))}
          </ul>
        </div>
      )}

      {event && slot ? (
        <>
          <Button
            type="button"
            variant="primary"
            className="w-full min-h-11 mt-5"
            onClick={() => {
              const url = buildGoogleCalendarUrl({
                event,
                slot,
                origin: window.location.origin,
              });
              window.open(url, "_blank", "noopener,noreferrer");
            }}
          >
            Add to Google Calendar
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full min-h-11 mt-3"
            onClick={() => {
              const dateStr =
                event.start_date ||
                (slot.start_time
                  ? new Date(slot.start_time).toISOString().slice(0, 10)
                  : "event");
              const slugPart = event.slug || event.id;
              const filename = `scitrek-${slugPart}-${dateStr}.ics`;
              downloadIcs({ event, slot, filename });
              toast.success("Calendar file saved. Open it to add to your calendar.");
            }}
          >
            Download .ics (Apple / Outlook)
          </Button>
        </>
      ) : null}

      <Button
        type="button"
        variant={event && slot ? "secondary" : "primary"}
        className="w-full min-h-11 mt-3"
        onClick={onDismiss}
      >
        Done
      </Button>
    </Modal>
  );
}
