// src/components/SignupSuccessCard.jsx
//
// Post-signup success popup card shown as a modal overlay.
// Pushes the volunteer to confirm via the emailed link (unconfirmed signups
// expire), lists every slot they took — with a waitlist badge and a 3-day
// promotion warning where that applies — and offers calendar exports.
// Dismissing resets the parent form.
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

function openGoogleCalendar(event, slot) {
  const url = buildGoogleCalendarUrl({
    event,
    slot,
    origin: window.location.origin,
  });
  window.open(url, "_blank", "noopener,noreferrer");
}

/**
 * Props:
 *   open          {boolean}    — controls modal visibility
 *   volunteerName {string}     — first name of the volunteer
 *   slots         {object[]}   — array of slot objects (date, start_time, end_time, location)
 *   onDismiss     {function}   — called when user clicks "Done"
 *   event         {object?}    — OPTIONAL. When provided alongside slots, enables
 *                                the calendar export buttons (PART-13 surface B).
 *   slot          {object?}    — OPTIONAL. A single slot to encode instead of `slots`,
 *                                for callers that confirm one session at a time.
 *   signups       {object[]?}  — OPTIONAL. Per-signup result items from the signup
 *                                response ({slot_id, status, position}); drives the
 *                                waitlist badges and the promotion warning.
 */
export default function SignupSuccessCard({
  open,
  volunteerName,
  slots,
  onDismiss,
  event,
  slot,
  signups,
}) {
  // What the calendar buttons export. `slot` used to be required, which meant
  // the buttons never appeared for the signup flow — it confirms a list of
  // slots, not one — so the most useful moment to add to a calendar had no way
  // to do it. Either shape works now.
  const calendarSlots = slots?.length ? slots : slot ? [slot] : [];

  // Per-slot signup result, keyed by slot_id (Phase 25 result items). Callers
  // that don't pass `signups` get the old everything-is-booked behavior.
  const resultBySlot = {};
  (signups || []).forEach((item) => {
    if (item?.slot_id) resultBySlot[item.slot_id] = item;
  });
  const isWaitlisted = (s) => resultBySlot[s.id]?.status === "waitlisted";
  const waitlistedSlots = calendarSlots.filter(isWaitlisted);

  // A waitlisted session isn't on the volunteer's schedule yet — keep it out
  // of both calendar exports until a promotion lands them a real spot.
  const bookedSlots = calendarSlots.filter((s) => !isWaitlisted(s));
  const canAddToCalendar = Boolean(event) && bookedSlots.length > 0;

  return (
    <Modal open={open} onClose={onDismiss} title="Almost done — check your email!">
      <p className="text-sm text-[var(--color-fg)]">
        Thanks,{" "}
        <span className="font-semibold">{volunteerName || "volunteer"}</span>!{" "}
        <span className="font-semibold">Your spot isn&apos;t secured yet.</span>{" "}
        We sent a confirmation link to your email — open it and confirm now.
        Unconfirmed signups expire, and your spot can be released to another
        volunteer.
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
                className="flex items-center justify-between gap-2 text-sm text-[var(--color-fg)] bg-[var(--color-surface)] rounded-lg px-3 py-2"
              >
                <span>{formatSlotLine(s)}</span>
                {isWaitlisted(s) ? (
                  <span className="shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-xs font-semibold text-amber-800">
                    {resultBySlot[s.id]?.position != null
                      ? `Waitlist #${resultBySlot[s.id].position}`
                      : "Waitlist"}
                  </span>
                ) : canAddToCalendar && bookedSlots.length > 1 && Boolean(event) ? (
                  <button
                    type="button"
                    aria-label={`Add ${formatSlotLine(s)} to Google Calendar`}
                    className="shrink-0 rounded-md border border-[var(--color-border)] px-2 py-1 text-xs font-medium text-[var(--color-brand)] hover:bg-gray-50"
                    onClick={() => openGoogleCalendar(event, s)}
                  >
                    Google Calendar
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      )}

      {waitlistedSlots.length > 0 ? (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-sm text-amber-900">
          <p className="font-semibold">
            You&apos;re on the waitlist for{" "}
            {waitlistedSlots.length === 1
              ? "one session"
              : `${waitlistedSlots.length} sessions`}
            .
          </p>
          <p className="mt-1">
            Check your inbox regularly — if a spot opens, we&apos;ll email you a
            promotion link, and you&apos;ll have{" "}
            <span className="font-semibold">3 days</span> from that email to
            confirm before the spot is offered to the next volunteer.
          </p>
        </div>
      ) : null}

      {canAddToCalendar ? (
        <>
          {bookedSlots.length === 1 ? (
            <Button
              type="button"
              variant="primary"
              className="w-full min-h-11 mt-5"
              onClick={() => openGoogleCalendar(event, bookedSlots[0])}
            >
              Add to Google Calendar
            </Button>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            className="w-full min-h-11 mt-3"
            onClick={() => {
              // Every booked slot the volunteer just took, not only the first
              // — one file that fills in their whole commitment. The filename
              // is derived in the lib so it can't pick up an ISO timestamp's
              // colons, which Windows rejects.
              downloadIcs({ event, slots: bookedSlots });
              toast.success(
                bookedSlots.length > 1
                  ? `Calendar file saved with ${bookedSlots.length} sessions. Open it to add them.`
                  : "Calendar file saved. Open it to add to your calendar.",
              );
            }}
          >
            Download .ics (Apple / Outlook)
          </Button>
        </>
      ) : null}

      <Button
        type="button"
        variant={canAddToCalendar ? "secondary" : "primary"}
        className="w-full min-h-11 mt-3"
        onClick={onDismiss}
      >
        Done
      </Button>
    </Modal>
  );
}
