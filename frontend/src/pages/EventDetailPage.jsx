import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { formatApiDateTimeLocal, toEpochMs } from "../lib/datetime";
import { useAuth } from "../state/authContext";
import {
  PageHeader,
  Card,
  Button,
  Modal,
  FieldError,
  Skeleton,
  EmptyState,
} from "../components/ui";
import { toast } from "../state/toast";
import { useDocumentMeta } from "../lib/useDocumentMeta";

// 3-tap rule: slot button (1) → confirm in modal (2) → done. No navigations between taps.

function isPast(endTime) {
  return toEpochMs(endTime) <= Date.now();
}

export default function EventDetailPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
  const { isAuthed, role } = useAuth();

  const [pendingSignup, setPendingSignup] = useState(null);
  const [pendingCancel, setPendingCancel] = useState(null);
  const [signupError, setSignupError] = useState("");
  const [cancelError, setCancelError] = useState("");
  const [busy, setBusy] = useState(false);

  const eventQ = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.events.get(eventId),
  });

  const event = eventQ.data;

  useDocumentMeta({
    title: event
      ? `${event.title} — Volunteer Scheduler` // TODO(copy)
      : "Event — Volunteer Scheduler", // TODO(copy)
    description: event?.description ?? "Volunteer shift details and signup.", // TODO(copy)
    ogType: "article",
  });

  const sortedSlots = useMemo(() => {
    const slots = event?.slots || [];
    return [...slots].sort(
      (a, b) => toEpochMs(a.start_time) - toEpochMs(b.start_time),
    );
  }, [event]);

  async function confirmSignup() {
    if (!pendingSignup) return;
    setSignupError("");
    setBusy(true);
    try {
      await api.signups.create({ slot_id: pendingSignup.id });
      await qc.invalidateQueries({ queryKey: ["mySignups"] });
      await qc.invalidateQueries({ queryKey: ["event", eventId] });
      setPendingSignup(null);
      // TODO(copy): signup success toast
      toast.success("You're in. See you there.");
    } catch (e) {
      setSignupError(e?.message || "Signup failed");
    } finally {
      setBusy(false);
    }
  }

  async function confirmCancel() {
    if (!pendingCancel) return;
    setCancelError("");
    setBusy(true);
    try {
      await api.signups.cancel(pendingCancel.signupId);
      await qc.invalidateQueries({ queryKey: ["mySignups"] });
      await qc.invalidateQueries({ queryKey: ["event", eventId] });
      setPendingCancel(null);
      // TODO(copy): cancel success toast
      toast.success("Signup canceled.");
    } catch (e) {
      setCancelError(e?.message || "Cancel failed");
    } finally {
      setBusy(false);
    }
  }

  if (eventQ.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (eventQ.error) {
    return (
      <EmptyState
        /* TODO(copy) */
        title="Couldn't load event"
        /* TODO(copy) */
        body={eventQ.error.message}
        action={
          <Button onClick={() => eventQ.refetch()}>
            {/* TODO(copy) */}
            Retry
          </Button>
        }
      />
    );
  }

  if (!event) {
    return (
      <EmptyState
        /* TODO(copy) */
        title="Event not found"
      />
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={event.title}
        subtitle={`${event.location || "TBD"} • ${formatApiDateTimeLocal(
          event.start_date,
        )}`}
      />

      {event.description && (
        <Card>
          <p className="whitespace-pre-wrap text-sm">{event.description}</p>
        </Card>
      )}

      <div>
        {/* TODO(copy): slots heading */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Slots
        </h2>
        {sortedSlots.length === 0 ? (
          /* TODO(copy) */
          <EmptyState title="No slots yet" />
        ) : (
          <ul className="space-y-2">
            {sortedSlots.map((s) => {
              const full = s.current_count >= s.capacity;
              const past = isPast(s.end_time);
              const canSignup =
                isAuthed && role === "participant" && !past;
              return (
                <li
                  key={s.id}
                  className="min-h-14 rounded-xl border border-[var(--color-border)] p-3 flex items-center justify-between gap-3"
                >
                  <div className="text-sm">
                    <div className="font-medium">
                      {formatApiDateTimeLocal(s.start_time)} →{" "}
                      {formatApiDateTimeLocal(s.end_time)}
                    </div>
                    <div className="text-[var(--color-fg-muted)] text-xs">
                      {s.current_count}/{s.capacity}
                      {full ? " • full (waitlist)" : ""}
                      {past ? " • past" : ""}
                    </div>
                  </div>
                  {canSignup && (
                    <Button
                      data-testid="slot-signup-button"
                      onClick={() =>
                        setPendingSignup({
                          id: s.id,
                          timeLabel: formatApiDateTimeLocal(s.start_time),
                        })
                      }
                    >
                      {/* TODO(copy) */}
                      Sign up
                    </Button>
                  )}
                  {!isAuthed && (
                    <span className="text-xs text-[var(--color-fg-muted)]">
                      {/* TODO(copy) */}
                      Login to sign up
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <Modal
        open={!!pendingSignup}
        onClose={() => {
          setPendingSignup(null);
          setSignupError("");
        }}
        /* TODO(copy) */
        title="Confirm signup"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Confirm signup for {pendingSignup?.timeLabel}?
        </p>
        <FieldError>{signupError}</FieldError>
        <div className="flex justify-end gap-2 mt-4">
          <Button
            variant="ghost"
            onClick={() => {
              setPendingSignup(null);
              setSignupError("");
            }}
            disabled={busy}
          >
            {/* TODO(copy) */}
            Not now
          </Button>
          <Button data-testid="confirm-signup-button" onClick={confirmSignup} disabled={busy}>
            {/* TODO(copy) */}
            Confirm signup
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!pendingCancel}
        onClose={() => {
          setPendingCancel(null);
          setCancelError("");
        }}
        /* TODO(copy) */
        title="Cancel signup"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Cancel your signup? This can't be undone.
        </p>
        <FieldError>{cancelError}</FieldError>
        <div className="flex justify-end gap-2 mt-4">
          <Button
            variant="ghost"
            onClick={() => setPendingCancel(null)}
            disabled={busy}
          >
            {/* TODO(copy) */}
            Keep it
          </Button>
          <Button variant="danger" onClick={confirmCancel} disabled={busy}>
            {/* TODO(copy) */}
            Cancel signup
          </Button>
        </div>
      </Modal>
    </div>
  );
}
