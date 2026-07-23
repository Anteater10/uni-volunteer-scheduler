import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, Button, Input, Label, FieldError } from "../components/ui";

// Mirror of the backend check-in window (check_in_service.py):
// a slot opens 15 minutes before its start and closes 30 minutes after.
// The server stays authoritative — this only drives the informational copy.
const WINDOW_BEFORE_MS = 15 * 60 * 1000;
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

function SlotChip({ slot }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-white px-3 py-1 text-sm">
      <span
        className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
          slot.slot_type === "orientation"
            ? "bg-purple-100 text-purple-700"
            : "bg-blue-100 text-blue-700"
        }`}
      >
        {slotTypeLabel(slot.slot_type)}
      </span>
      {fmtTime(slot.start_time)} – {fmtTime(slot.end_time)}
      {slot.location ? (
        <span className="text-[var(--color-fg-muted)]">· {slot.location}</span>
      ) : null}
    </span>
  );
}

export default function EventCheckInPage() {
  const { eventId } = useParams();
  const [email, setEmail] = useState("");
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const eventQ = useQuery({
    queryKey: ["publicEvent", eventId],
    queryFn: () => api.public.getEvent(eventId),
    retry: false,
  });

  // Issue #31 — check-in is per-slot: name exactly which shift is open right
  // now instead of the old blanket "next half hour" copy.
  const slotsQ = useQuery({
    queryKey: ["publicEventSlots", eventId],
    queryFn: () => api.listSlots({ event_id: eventId }),
    retry: false,
    refetchInterval: 60 * 1000,
  });

  const mut = useMutation({
    mutationFn: () => api.public.checkInByEmail(eventId, email.trim()),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
    },
    onError: (err) => {
      setError(err);
      setResult(null);
    },
  });

  const onSubmit = (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    mut.mutate();
  };

  const eventTitle = eventQ.data?.title || "Event check-in";

  const now = Date.now();
  const slots = Array.isArray(slotsQ.data)
    ? [...slotsQ.data].sort(
        (a, b) => new Date(a.start_time) - new Date(b.start_time),
      )
    : [];
  // Every shift gets a window verdict — shifts whose windows already passed
  // stay visible as "closed" so nobody wonders where the orientation went.
  const slotStates = slots.map((s) => {
    const start = new Date(s.start_time).getTime();
    const opensAt = start - WINDOW_BEFORE_MS;
    const closesAt = start + WINDOW_AFTER_MS;
    const state = now < opensAt ? "upcoming" : now > closesAt ? "closed" : "open";
    return { slot: s, state, opensAt };
  });
  const anyOpen = slotStates.some((e) => e.state === "open");

  return (
    <div className="mx-auto max-w-md px-4 py-6">
      <Card className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold">{eventTitle}</h1>
          <p className="mt-1 text-sm text-[var(--color-fg-muted)]">
            Enter the email you used when you signed up. We'll check you in
            for the shift that's open right now.
          </p>
        </div>

        {slotStates.length > 0 ? (
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
                  <SlotChip slot={slot} />
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

        {!result ? (
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
                  : error?.code === "OUTSIDE_WINDOW"
                  ? "None of your shifts are open for check-in right now. Check-in opens 15 minutes before each shift starts."
                  : error?.message || "Check-in failed. Please try again."}
              </FieldError>
            ) : null}
            <Button type="submit" disabled={mut.isPending}>
              {mut.isPending ? "Checking in…" : "Check in"}
            </Button>
          </form>
        ) : (
          <div className="space-y-3">
            <div className="rounded-lg bg-green-50 p-3 text-green-900">
              <p className="font-semibold">
                Checked in, {result.volunteer_name}!
              </p>
              <p className="text-sm">
                {result.count_checked_in > 0
                  ? `Just checked you in for ${result.count_checked_in} shift${result.count_checked_in === 1 ? "" : "s"}.`
                  : "You were already checked in."}
                {result.count_already_checked_in > 0 && result.count_checked_in > 0
                  ? ` (${result.count_already_checked_in} already done.)`
                  : ""}
              </p>
            </div>
            <ul className="divide-y divide-[var(--color-border)] rounded-md border border-[var(--color-border)]">
              {(result.signups || []).map((s) => (
                <li
                  key={s.signup_id}
                  className="flex items-center justify-between gap-2 px-3 py-2 text-sm"
                >
                  <span className="flex items-center gap-2">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
                        s.slot_type === "orientation"
                          ? "bg-purple-100 text-purple-700"
                          : "bg-blue-100 text-blue-700"
                      }`}
                    >
                      {slotTypeLabel(s.slot_type)}
                    </span>
                    {fmtTime(s.slot_start)} – {fmtTime(s.slot_end)}
                  </span>
                  <span className="text-[var(--color-fg-muted)]">{s.status}</span>
                </li>
              ))}
            </ul>
            <Button
              variant="secondary"
              onClick={() => {
                setResult(null);
                setEmail("");
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
