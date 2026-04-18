import React, { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getSignupEvent, selfCheckIn } from "../api/checkIn";
import {
  PageHeader,
  Button,
  Skeleton,
  ErrorState,
  Input,
  Label,
  FieldError,
} from "../components/ui";

export default function SelfCheckInPage() {
  const { signupId } = useParams();
  const navigate = useNavigate();
  const [venueCode, setVenueCode] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [errorKind, setErrorKind] = useState("");

  const signupQ = useQuery({
    queryKey: ["signup", signupId],
    queryFn: () => getSignupEvent(signupId),
  });

  const checkInMut = useMutation({
    mutationFn: ({ eventId, signupId: sid, code }) =>
      selfCheckIn(eventId, sid, code),
    onError: (err) => {
      const code =
        err?.response?.data?.code || err?.response?.data?.detail?.code;
      setErrorKind(code || "UNKNOWN");
      if (code === "WRONG_VENUE_CODE") {
        setErrorMsg("That's not the right code. Ask an organizer.");
      } else if (code === "OUTSIDE_WINDOW") {
        setErrorMsg(
          "Check-in is only open 15 minutes before your slot through 30 minutes after.",
        );
      } else if (code === "INVALID_TRANSITION") {
        setErrorMsg("This signup can't be checked in right now.");
      } else {
        setErrorMsg(err?.message || "Check-in failed");
      }
    },
  });

  if (signupQ.isPending) {
    return (
      <div
        aria-busy="true"
        aria-live="polite"
        className="max-w-md mx-auto mt-12 space-y-3 px-4"
      >
        <Skeleton className="h-8 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-12 rounded-xl" />
      </div>
    );
  }

  if (signupQ.error) {
    return (
      <ErrorState
        title="We couldn't load this check-in"
        body="Check your connection and try again."
        action={
          <Button variant="secondary" onClick={() => signupQ.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const signup = signupQ.data;
  const eventId = signup.event_id || signup.slot?.event_id;

  // Already checked in or attended — show confirmation
  if (
    signup.status === "checked_in" ||
    signup.status === "attended" ||
    checkInMut.isSuccess
  ) {
    const time = signup.checked_in_at
      ? new Date(signup.checked_in_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })
      : new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        });
    return (
      <div className="text-center mt-12">
        <PageHeader title="You're checked in" />
        <p className="text-lg mt-4">Checked in at {time}</p>
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">
          Thanks for volunteering!
        </p>
      </div>
    );
  }

  // PART-09: Page-level error branches that block the form.
  // INVALID_TRANSITION: server says signup cannot transition (already attended, etc.).
  if (errorKind === "INVALID_TRANSITION") {
    return (
      <ErrorState
        title="Already checked in"
        body="Our records show you're already marked as attended. No action needed."
        action={
          <Button
            variant="secondary"
            onClick={() => navigate(`/events/${eventId}`)}
          >
            View event details
          </Button>
        }
      />
    );
  }

  // OUTSIDE_WINDOW: distinguish "not open yet" vs "closed" by comparing slot start_time to now.
  // Backend currently does not expose a before/after discriminator on the error payload, so
  // we fall back to a client-side heuristic: if the slot has not started yet, show
  // "isn't open yet"; otherwise show "has closed". (Documented in SUMMARY as a backend gap.)
  if (errorKind === "OUTSIDE_WINDOW") {
    const slotStart =
      signup.slot_start_time ||
      signup.slot?.start_time ||
      signup.start_time;
    const isBeforeWindow = slotStart
      ? new Date() < new Date(slotStart)
      : true;
    if (isBeforeWindow) {
      return (
        <ErrorState
          title="Check-in isn't open yet"
          body="Check-in opens 15 minutes before the event starts"
          action={
            <Button
              variant="secondary"
              onClick={() => navigate(`/events/${eventId}`)}
            >
              View event details
            </Button>
          }
        />
      );
    }
    return (
      <ErrorState
        title="Check-in has closed"
        body="Check-in closed when the event ended. Talk to the organizer on-site."
        action={
          <Button
            variant="secondary"
            onClick={() => navigate(`/events/${eventId}`)}
          >
            View event details
          </Button>
        }
      />
    );
  }

  function handleSubmit(e) {
    e.preventDefault();
    setErrorMsg("");
    setErrorKind("");
    if (!eventId) {
      setErrorMsg("Could not determine event. Please contact an organizer.");
      return;
    }
    checkInMut.mutate({ eventId, signupId, code: venueCode });
  }

  return (
    <div>
      <PageHeader title="Check in" />

      <div className="mt-6 text-center">
        {signup.event_title && (
          <h2 className="text-lg font-semibold">{signup.event_title}</h2>
        )}
        {signup.slot_start_time && (
          <p className="text-sm text-[var(--color-fg-muted)] mt-1">
            {new Date(signup.slot_start_time).toLocaleString()}
          </p>
        )}
      </div>

      <form
        onSubmit={handleSubmit}
        className="mt-8 max-w-xs mx-auto space-y-4"
      >
        <div>
          <Label htmlFor="venue-code">4-digit venue code</Label>
          <Input
            id="venue-code"
            name="venue-code"
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={4}
            autoComplete="one-time-code"
            value={venueCode}
            onChange={(e) =>
              setVenueCode(e.target.value.replace(/\D/g, ""))
            }
            aria-describedby={
              errorMsg && errorKind === "WRONG_VENUE_CODE"
                ? "venue-code-error"
                : undefined
            }
            aria-invalid={
              errorMsg && errorKind === "WRONG_VENUE_CODE" ? "true" : undefined
            }
            placeholder="0000"
            className="text-center text-2xl tracking-[0.5em] font-mono"
          />
          {errorMsg && errorKind === "WRONG_VENUE_CODE" ? (
            <FieldError id="venue-code-error">{errorMsg}</FieldError>
          ) : null}
        </div>

        {errorMsg &&
        errorKind !== "WRONG_VENUE_CODE" &&
        errorKind !== "OUTSIDE_WINDOW" &&
        errorKind !== "INVALID_TRANSITION" ? (
          <p className="text-sm text-red-600 text-center" role="alert">
            {errorMsg}
          </p>
        ) : null}

        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="w-full"
          disabled={venueCode.length !== 4 || checkInMut.isPending}
        >
          {checkInMut.isPending ? "Checking in..." : "Check me in"}
        </Button>
      </form>
    </div>
  );
}
