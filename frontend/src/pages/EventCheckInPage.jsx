import React, { useRef, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, Button, Input, Label, FieldError } from "../components/ui";
import {
  VENUE_TZ,
  fmtVenueDate,
  fmtVenueTime,
  fmtVenueWeekday,
} from "../lib/venueTime";

// Mirror of the backend check-in window (check_in_service.py): a slot opens
// 30 minutes before its start and closes 30 minutes after. Only drives the
// pre-email schedule banner — per-shift verdicts come from the server.
const WINDOW_BEFORE_MS = 30 * 60 * 1000;
const WINDOW_AFTER_MS = 30 * 60 * 1000;

// Issue #189: while any of the volunteer's shifts is still "upcoming", look
// them up again this often, so "Check-in opens at 9:24" turns tappable on its
// own. react-query pauses the interval while the page is hidden.
const RELOOKUP_MS = 30 * 1000;

const anyUpcoming = (data) =>
  (data?.shifts || []).some((s) => s.window_state === "upcoming");

// Venue (Pacific) time, like every other page: a volunteer's phone may be
// set to another timezone, and the schedule is the venue's wall clock.
const fmtTime = (iso) => fmtVenueTime(iso);

// The venue calendar day of an instant, e.g. "2026-10-15". Issue #189: the
// page is about today; a two-day shift's Tuesday is not what a student
// scanning on Thursday is here for.
const venueDay = (t) =>
  new Date(t).toLocaleDateString("en-CA", { timeZone: VENUE_TZ });

// Issue #189: "closed" has two causes and two different next steps. Shared by
// the schedule and the cards so both say the same thing.
const closedLabel = (staffClosed) =>
  staffClosed ? "Closed by staff" : "Self check-in has ended — ask a staff member";

// "Shift 2 · Thursday" for a unit this visit checked in.
function visitLabel(row) {
  const name =
    row.shift_name ||
    (row.slot_type === "orientation" ? "Orientation" : row.session_name);
  return [name, fmtVenueWeekday(row.slot_start)].filter(Boolean).join(" · ");
}

function slotTypeLabel(slotType) {
  return slotType === "orientation" ? "Orientation" : "Module";
}

function TypeBadge({ slotType }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
        slotType === "orientation"
          ? "bg-purple-100 text-purple-700"
          : "bg-blue-100 text-blue-700"
      }`}
    >
      {slotTypeLabel(slotType)}
    </span>
  );
}

// Issue #31 UX rework — one tappable card per shift the volunteer holds.
function ShiftCard({ shift, onCheckIn, busy }) {
  const done = shift.status === "checked_in" || shift.status === "attended";
  const waitlisted = shift.status === "waitlisted";
  const open = shift.window_state === "open" && !waitlisted;
  const tappable = open && !done && !busy;

  // A waitlisted booking holds no seat: say so up front rather than let the
  // tap be refused.
  const stateLine = done
    ? "Checked in ✓"
    : waitlisted
      ? "Waitlisted — nothing to check in to yet"
      : open
        ? "Tap to check in"
        : shift.window_state === "upcoming"
          ? `Check-in opens at ${fmtTime(shift.window_opens_at)}`
          : closedLabel(shift.staff_closed);

  return (
    <li>
      <button
        type="button"
        data-testid={`shift-${shift.unit_id}`}
        className={`w-full rounded-xl border-2 px-4 py-3 text-left transition-all ${
          done
            ? "border-green-300 bg-green-50"
            : tappable
              ? "cursor-pointer border-blue-300 bg-white shadow-sm hover:border-blue-500 hover:shadow-md"
              : "cursor-not-allowed border-gray-200 bg-gray-50 opacity-70"
        }`}
        disabled={!tappable}
        onClick={() => tappable && onCheckIn(shift)}
      >
        <div className="flex items-center justify-between gap-2">
          <span className="flex flex-wrap items-center gap-2 text-sm">
            <TypeBadge slotType={shift.slot_type} />
            {/* 2026-08-02 shifts: a session row leads with its shift name, so
                a Tue+Wed bundle's two rows read as one commitment. */}
            {shift.shift_name ? (
              <span className="font-semibold">{shift.shift_name}</span>
            ) : null}
            {shift.session_name ? (
              <span className="text-[var(--color-fg-muted)]">
                {shift.session_name}
              </span>
            ) : null}
            <span className="font-medium">
              {fmtTime(shift.slot_start)} – {fmtTime(shift.slot_end)}
            </span>
            {shift.slot_location ? (
              <span className="text-[var(--color-fg-muted)]">
                · {shift.slot_location}
              </span>
            ) : null}
          </span>
        </div>
        <p
          className={`mt-1 text-sm font-medium ${
            done
              ? "text-green-700"
              : open
                ? "text-blue-700"
                : "text-[var(--color-fg-muted)]"
          }`}
        >
          {stateLine}
        </p>
      </button>
    </li>
  );
}

export default function EventCheckInPage() {
  const { eventId } = useParams();
  // Issue #31 hardening: the organizer-displayed QR carries the venue code
  // (?v=CODE); the backend rejects lookup/check-in without it.
  const [searchParams] = useSearchParams();
  const venueCode = searchParams.get("v") || "";
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  // The submitted lookup: the email as sent, plus a counter that never
  // repeats, so every submit (the same email again after an error, or after
  // "Check in someone else") is a fresh fetch rather than a cache hit.
  const [submitted, setSubmitted] = useState(null);
  const attemptRef = useRef(0);
  // What this visit checked in, for the greeting: "Shift 2 · Thursday".
  const [visitCheckIns, setVisitCheckIns] = useState([]);

  const eventQ = useQuery({
    queryKey: ["publicEvent", eventId],
    queryFn: () => api.public.getEvent(eventId),
    retry: false,
  });

  // Pre-email schedule banner: every shift on the event with its verdict, so
  // nobody wonders where a passed shift went.
  const slotsQ = useQuery({
    queryKey: ["publicEventSlots", eventId],
    queryFn: () => api.listSlots({ event_id: eventId }),
    retry: false,
    refetchInterval: 60 * 1000,
  });
  // Shift names for the schedule, so a session reads "Shift 2 · Thu" the way
  // the roster names it, not as a bare time.
  const shiftsQ = useQuery({
    queryKey: ["publicEventShifts", eventId],
    queryFn: () => api.shifts.list(eventId),
    retry: false,
  });

  const lookupKey = ["checkInLookup", eventId, venueCode, submitted];
  const checkInMut = useMutation({
    mutationFn: (unitId) =>
      api.public.checkInSelected(eventId, submitted.email, [unitId], venueCode),
    // A re-lookup still in flight was answered before this tap; drop it so it
    // cannot land afterwards and flip the card back to "Tap to check in".
    onMutate: () => queryClient.cancelQueries({ queryKey: lookupKey }),
    // Then ask the server again, whatever happened: after a SLOT_CLOSED or
    // OUTSIDE_WINDOW refusal the card has to show why.
    onSettled: () => queryClient.invalidateQueries({ queryKey: lookupKey }),
    onSuccess: (data) => {
      // Flip the tapped row(s) to their new status in place. Keyed on unit_id
      // because a row is now either an orientation signup or one session of a
      // shift, and only unit_id is present for both.
      const updated = new Map(data.signups.map((s) => [s.unit_id, s.status]));
      queryClient.setQueryData(lookupKey, (prev) =>
        prev
          ? {
              ...prev,
              shifts: prev.shifts.map((sh) =>
                updated.has(sh.unit_id)
                  ? { ...sh, status: updated.get(sh.unit_id) }
                  : sh,
              ),
            }
          : prev,
      );
      const fresh = data.signups.filter((row) => row.newly_checked_in);
      setVisitCheckIns((prev) => {
        const seen = new Set(prev.map((v) => v.unitId));
        const next = [...prev];
        for (const row of fresh) {
          if (seen.has(row.unit_id)) continue;
          seen.add(row.unit_id);
          next.push({ unitId: row.unit_id, label: visitLabel(row) });
        }
        return next;
      });
    },
  });
  const checkInError = checkInMut.error;
  const tapping = checkInMut.isPending;

  const lookupQ = useQuery({
    queryKey: lookupKey,
    queryFn: () =>
      api.public.checkInLookup(eventId, submitted.email, venueCode),
    enabled: submitted !== null,
    retry: false,
    staleTime: Infinity,
    // Back on the page with a shift still upcoming: look again right away.
    refetchOnWindowFocus: (query) =>
      anyUpcoming(query.state.data) ? "always" : false,
    // Paused while a tap is in flight, so no refresh lands mid-tap; the tap
    // refreshes the cards itself when it settles.
    refetchInterval: (query) =>
      !tapping && anyUpcoming(query.state.data) ? RELOOKUP_MS : false,
  });
  // A failed background re-lookup keeps the cards it already has.
  const lookup = submitted ? (lookupQ.data ?? null) : null;
  const lookupError = submitted && !lookup ? lookupQ.error : null;


  const onSubmit = (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    checkInMut.reset();
    attemptRef.current += 1;
    setSubmitted({ email: email.trim(), attempt: attemptRef.current });
  };

  const eventTitle = eventQ.data?.title || "Event check-in";

  // The schedule's clock is the time of its last fetch (refetched every
  // minute), since a render can't read the clock itself.
  const now = slotsQ.dataUpdatedAt;
  const slots = Array.isArray(slotsQ.data)
    ? [...slotsQ.data].sort(
        (a, b) => new Date(a.start_time) - new Date(b.start_time),
      )
    : [];
  const shiftNames = new Map(
    (Array.isArray(shiftsQ.data) ? shiftsQ.data : []).map((sh) => [sh.id, sh.name]),
  );
  // Past days are over; the schedule is today and what is still ahead.
  const todayKey = venueDay(now);
  const slotStates = slots
    .filter((s) => venueDay(s.start_time) >= todayKey)
    .map((s) => {
    const start = new Date(s.start_time).getTime();
    const opensAt = start - WINDOW_BEFORE_MS;
    const closesAt = start + WINDOW_AFTER_MS;
    // A slot staff have closed is closed whatever the clock says — the same
    // rule the server's window_state applies after lookup.
    const state = s.closed_at
      ? "closed"
      : now < opensAt
        ? "upcoming"
        : now > closesAt
          ? "closed"
          : "open";
    const name = s.shift_id
      ? [shiftNames.get(s.shift_id), s.name].filter(Boolean).join(" · ")
      : null;
    return { slot: s, state, opensAt, name };
  });
  const anyOpen = slotStates.some((e) => e.state === "open");

  // After lookup: only today's units, by the clock of the last answer.
  const lookupToday = venueDay(lookupQ.dataUpdatedAt);
  const todaysShifts = (lookup?.shifts || []).filter(
    (s) => venueDay(s.slot_start) === lookupToday,
  );
  const showSchedule =
    !lookup &&
    slotStates.length > 0 &&
    lookupError?.code !== "WRONG_VENUE_CODE";

  if (!venueCode) {
    return (
      <div className="mx-auto max-w-md px-4 py-6">
        <Card className="space-y-2">
          <h1 className="text-xl font-semibold">{eventTitle}</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            This link is missing its check-in code. Please scan the QR code
            shown at the check-in table — if you already did, ask the
            organizer to re-show it from the roster screen.
          </p>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-md px-4 py-6">
      <Card className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold">{eventTitle}</h1>
          <p className="mt-1 text-sm text-[var(--color-fg-muted)]">
            {lookup
              ? "Tap the shift you're here for."
              : "Enter the email you used when you signed up, then pick the shift you're here for."}
          </p>
        </div>

        {showSchedule ? (
          <div
            className={`rounded-lg p-3 text-sm ${
              anyOpen ? "bg-blue-50 text-blue-900" : "bg-amber-50 text-amber-900"
            }`}
            data-testid="checkin-window-status"
          >
            <p className="mb-1.5 font-semibold">
              {anyOpen
                ? "Checking in now:"
                : "No shifts are open for check-in right now."}
            </p>
            <ul className="space-y-1.5">
              {slotStates.map(({ slot, state, opensAt, name }) => (
                <li
                  key={slot.id}
                  className={`flex flex-wrap items-center justify-between gap-1.5 ${
                    state === "closed" ? "opacity-60" : ""
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <TypeBadge slotType={slot.slot_type} />
                    {name ? <span className="font-semibold">{name}</span> : null}
                    <span>
                      {fmtVenueDate(slot.start_time)} · {fmtTime(slot.start_time)} –{" "}
                      {fmtTime(slot.end_time)}
                    </span>
                    {slot.location ? (
                      <span className="text-[var(--color-fg-muted)]">
                        · {slot.location}
                      </span>
                    ) : null}
                  </span>
                  <span
                    className={`text-xs font-medium ${
                      state === "open" ? "text-green-700" : ""
                    }`}
                  >
                    {state === "open"
                      ? "Open now"
                      : state === "upcoming"
                        ? `Opens at ${fmtTime(new Date(opensAt).toISOString())}`
                        : closedLabel(Boolean(slot.closed_at))}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {!lookup ? (
          <form onSubmit={onSubmit} className="space-y-3">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                inputMode="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
            </div>
            {lookupError ? (
              <FieldError>
                {lookupError.code === "NO_SIGNUP_FOR_EMAIL"
                  ? "We couldn't find a signup for that email on this event. Double-check the spelling."
                  : lookupError.code === "WRONG_VENUE_CODE"
                    ? "This check-in link is out of date — ask the organizer to re-show the QR code and scan it again."
                    : lookupError.message || "Something went wrong. Please try again."}
              </FieldError>
            ) : null}
            <Button type="submit" disabled={lookupQ.isFetching}>
              {lookupQ.isFetching ? "Looking up…" : "Find my shifts"}
            </Button>
          </form>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">
              Hi <strong>{lookup.volunteer_name}</strong>
              {todaysShifts.length > 0 ? " — here are today's shifts:" : ""}
            </p>
            {visitCheckIns.length > 0 ? (
              <p className="text-sm font-medium text-green-700" role="status">
                You&apos;re checked in for{" "}
                {visitCheckIns.map((v) => v.label).join(", ")}.
              </p>
            ) : null}
            {todaysShifts.length === 0 ? (
              <p className="text-sm text-[var(--color-fg-muted)]">
                You have no shifts today.
              </p>
            ) : null}
            <ul className="space-y-2" aria-live="polite">
              {todaysShifts.map((shift) => (
                <ShiftCard
                  key={shift.unit_id}
                  shift={shift}
                  busy={checkInMut.isPending}
                  onCheckIn={(sh) => checkInMut.mutate(sh.unit_id)}
                />
              ))}
            </ul>
            {checkInError ? (
              <FieldError>
                {/* SLOT_CLOSED / OUTSIDE_WINDOW / INVALID_TRANSITION carry a
                    message written for the volunteer; show it as sent. */}
                {checkInError.code === "WRONG_VENUE_CODE"
                  ? "This check-in link is out of date — ask the organizer to re-show the QR code and scan it again."
                  : checkInError.message || "Check-in failed. Please try again."}
              </FieldError>
            ) : null}
            <Button
              variant="secondary"
              onClick={() => {
                setSubmitted(null);
                setEmail("");
                setVisitCheckIns([]);
                checkInMut.reset();
              }}
            >
              Check in someone else
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
