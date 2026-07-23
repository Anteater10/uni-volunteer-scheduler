import React, { useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, Button, Input, Label, FieldError } from "../components/ui";

// Mirror of the backend check-in window (check_in_service.py): a slot opens
// 30 minutes before its start and closes 30 minutes after. Only drives the
// pre-email schedule banner — per-shift verdicts come from the server.
const WINDOW_BEFORE_MS = 30 * 60 * 1000;
const WINDOW_AFTER_MS = 30 * 60 * 1000;

function fmtTime(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
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
  const open = shift.window_state === "open";
  const tappable = open && !done && !busy;

  const stateLine = done
    ? "Checked in ✓"
    : open
      ? "Tap to check in"
      : shift.window_state === "upcoming"
        ? `Check-in opens at ${fmtTime(shift.window_opens_at)}`
        : "Check-in closed";

  return (
    <li>
      <button
        type="button"
        data-testid={`shift-${shift.signup_id}`}
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
  const [email, setEmail] = useState("");
  const [lookup, setLookup] = useState(null);
  const [error, setError] = useState(null);

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

  const lookupMut = useMutation({
    mutationFn: () => api.public.checkInLookup(eventId, email.trim(), venueCode),
    onSuccess: (data) => {
      setLookup(data);
      setError(null);
    },
    onError: (err) => {
      setError(err);
      setLookup(null);
    },
  });

  const checkInMut = useMutation({
    mutationFn: (signupId) =>
      api.public.checkInSelected(eventId, email.trim(), [signupId], venueCode),
    onSuccess: (data) => {
      // Flip the tapped shift(s) to their new status in place.
      const updated = new Map(data.signups.map((s) => [s.signup_id, s.status]));
      setLookup((prev) =>
        prev
          ? {
              ...prev,
              shifts: prev.shifts.map((sh) =>
                updated.has(sh.signup_id)
                  ? { ...sh, status: updated.get(sh.signup_id) }
                  : sh,
              ),
            }
          : prev,
      );
      setError(null);
    },
    onError: (err) => setError(err),
  });

  const onSubmit = (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    lookupMut.mutate();
  };

  const eventTitle = eventQ.data?.title || "Event check-in";

  const now = Date.now();
  const slots = Array.isArray(slotsQ.data)
    ? [...slotsQ.data].sort(
        (a, b) => new Date(a.start_time) - new Date(b.start_time),
      )
    : [];
  const slotStates = slots.map((s) => {
    const start = new Date(s.start_time).getTime();
    const opensAt = start - WINDOW_BEFORE_MS;
    const closesAt = start + WINDOW_AFTER_MS;
    const state = now < opensAt ? "upcoming" : now > closesAt ? "closed" : "open";
    return { slot: s, state, opensAt };
  });
  const anyOpen = slotStates.some((e) => e.state === "open");

  const checkedCount = (lookup?.shifts || []).filter(
    (s) => s.status === "checked_in" || s.status === "attended",
  ).length;

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

        {!lookup && slotStates.length > 0 ? (
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
              {slotStates.map(({ slot, state, opensAt }) => (
                <li
                  key={slot.id}
                  className={`flex flex-wrap items-center justify-between gap-1.5 ${
                    state === "closed" ? "opacity-60" : ""
                  }`}
                >
                  <span className="flex items-center gap-1.5">
                    <TypeBadge slotType={slot.slot_type} />
                    {fmtTime(slot.start_time)} – {fmtTime(slot.end_time)}
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
                        : "Check-in closed"}
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
            {error ? (
              <FieldError>
                {error?.code === "NO_SIGNUP_FOR_EMAIL"
                  ? "We couldn't find a signup for that email on this event. Double-check the spelling."
                  : error?.code === "WRONG_VENUE_CODE"
                    ? "This check-in link is out of date — ask the organizer to re-show the QR code and scan it again."
                    : error?.message || "Something went wrong. Please try again."}
              </FieldError>
            ) : null}
            <Button type="submit" disabled={lookupMut.isPending}>
              {lookupMut.isPending ? "Looking up…" : "Find my shifts"}
            </Button>
          </form>
        ) : (
          <div className="space-y-3">
            <p className="text-sm">
              Hi <strong>{lookup.volunteer_name}</strong>
              {checkedCount > 0
                ? ` — checked in for ${checkedCount} shift${checkedCount === 1 ? "" : "s"}.`
                : " — here are your shifts:"}
            </p>
            <ul className="space-y-2">
              {lookup.shifts.map((shift) => (
                <ShiftCard
                  key={shift.signup_id}
                  shift={shift}
                  busy={checkInMut.isPending}
                  onCheckIn={(sh) => checkInMut.mutate(sh.signup_id)}
                />
              ))}
            </ul>
            {error ? (
              <FieldError>
                {error?.code === "OUTSIDE_WINDOW"
                  ? "That shift isn't open for check-in right now — check-in opens 30 minutes before start."
                  : error?.code === "WRONG_VENUE_CODE"
                    ? "This check-in link is out of date — ask the organizer to re-show the QR code and scan it again."
                    : error?.message || "Check-in failed. Please try again."}
              </FieldError>
            ) : null}
            <Button
              variant="secondary"
              onClick={() => {
                setLookup(null);
                setEmail("");
                setError(null);
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
