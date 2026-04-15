import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { getSignupEvent, selfCheckIn } from "../api/checkIn";
import { PageHeader, Button, Skeleton } from "../components/ui";

export default function SelfCheckInPage() {
  const { signupId } = useParams();
  const [venueCode, setVenueCode] = useState("");
  const [errorMsg, setErrorMsg] = useState("");

  const signupQ = useQuery({
    queryKey: ["signup", signupId],
    queryFn: () => getSignupEvent(signupId),
  });

  const checkInMut = useMutation({
    mutationFn: ({ eventId, signupId: sid, code }) =>
      selfCheckIn(eventId, sid, code),
    onError: (err) => {
      const code = err?.response?.data?.code || err?.response?.data?.detail?.code;
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
      <div>
        <PageHeader title="Check In" />
        <Skeleton className="h-40 w-full rounded-xl" />
      </div>
    );
  }

  if (signupQ.error) {
    return (
      <div>
        <PageHeader title="Check In" />
        <p className="text-sm text-red-600 mt-4">
          Could not load signup details.
        </p>
      </div>
    );
  }

  const signup = signupQ.data;

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
        {/* TODO(copy) */}
        <PageHeader title="Checked in!" />
        <p className="text-lg mt-4">Checked in at {time}</p>
        <p className="text-sm text-[var(--color-fg-muted)] mt-2">
          {/* TODO(copy) */}
          Thanks for volunteering!
        </p>
      </div>
    );
  }

  // We need to discover event_id from the signup data
  // The GET /signups/{id} returns slot_id, so we need to look up event via the signup's slot
  // For now, the backend returns event-related fields if available
  const eventId = signup.event_id || signup.slot?.event_id;

  function handleSubmit(e) {
    e.preventDefault();
    setErrorMsg("");
    if (!eventId) {
      setErrorMsg("Could not determine event. Please contact an organizer.");
      return;
    }
    checkInMut.mutate({ eventId, signupId, code: venueCode });
  }

  return (
    <div>
      {/* TODO(copy) */}
      <PageHeader title="Check In" />

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

      <form onSubmit={handleSubmit} className="mt-8 max-w-xs mx-auto space-y-4">
        <div>
          <label
            htmlFor="venue-code"
            className="block text-sm font-medium mb-1"
          >
            {/* TODO(copy) */}
            4-digit venue code
          </label>
          <input
            id="venue-code"
            type="text"
            inputMode="numeric"
            pattern="[0-9]{4}"
            maxLength={4}
            value={venueCode}
            onChange={(e) => setVenueCode(e.target.value.replace(/\D/g, ""))}
            className="w-full text-center text-2xl tracking-[0.5em] font-mono border rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]"
            placeholder="0000"
            autoComplete="off"
          />
        </div>

        {errorMsg && (
          <p className="text-sm text-red-600 text-center" role="alert">
            {errorMsg}
          </p>
        )}

        <Button
          type="submit"
          className="w-full h-14 text-lg"
          disabled={venueCode.length !== 4 || checkInMut.isPending}
        >
          {/* TODO(copy) */}
          {checkInMut.isPending ? "Checking in..." : "Check in"}
        </Button>
      </form>
    </div>
  );
}
