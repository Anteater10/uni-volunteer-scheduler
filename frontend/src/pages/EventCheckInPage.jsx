import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import { Card, Button, Input, Label, FieldError } from "../components/ui";

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

  return (
    <div className="mx-auto max-w-md px-4 py-6">
      <Card className="space-y-4">
        <div>
          <h1 className="text-xl font-semibold">{eventTitle}</h1>
          <p className="mt-1 text-sm text-[var(--color-fg-muted)]">
            Enter the email you used when you signed up. We'll check you
            in for every shift you have in the next half hour.
          </p>
        </div>

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
                  ? "You're not inside the check-in window for any of your shifts yet. Come back closer to start time."
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
                <li key={s.signup_id} className="flex items-center justify-between px-3 py-2 text-sm">
                  <span>
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
