import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";
import { formatApiDateTimeLocal, toEpochMs } from "../lib/datetime";
import {
  PageHeader,
  Card,
  Button,
  Modal,
  EmptyState,
  Skeleton,
  FieldError,
} from "../components/ui";
import { toast } from "../state/toast";
import StatusIcon from "../components/StatusIcon";
import ModuleTimeline from "../components/ModuleTimeline";

export default function MySignupsPage() {
  const qc = useQueryClient();
  const [pendingCancel, setPendingCancel] = useState(null);
  const [cancelError, setCancelError] = useState("");
  const [busy, setBusy] = useState(false);

  const signupsQ = useQuery({
    queryKey: ["mySignups"],
    queryFn: api.signups.my,
  });

  // Phase 4: module timeline
  const timelineQ = useQuery({
    queryKey: ["module-timeline"],
    queryFn: () => api.moduleTimeline(),
  });

  const signups = signupsQ.data || [];

  const sorted = useMemo(() => {
    return [...signups].sort(
      (a, b) => toEpochMs(b.timestamp) - toEpochMs(a.timestamp),
    );
  }, [signups]);

  const { upcoming, past } = useMemo(() => {
    const now = Date.now();
    const groups = { upcoming: [], past: [] };
    sorted.forEach((signup) => {
      const slotEnd = signup.slot_end_time
        ? toEpochMs(signup.slot_end_time)
        : null;
      if (slotEnd !== null && slotEnd < now) {
        groups.past.push(signup);
      } else {
        groups.upcoming.push(signup);
      }
    });
    return groups;
  }, [sorted]);

  async function confirmCancel() {
    if (!pendingCancel) return;
    setBusy(true);
    setCancelError("");
    try {
      await api.signups.cancel(pendingCancel.id);
      await qc.invalidateQueries({ queryKey: ["mySignups"] });
      setPendingCancel(null);
      // TODO(copy): cancel confirmation
      toast.success("Signup canceled.");
    } catch (e) {
      setCancelError(e?.message || "Cancel failed");
    } finally {
      setBusy(false);
    }
  }

  async function downloadIcs(signupId) {
    try {
      await downloadBlob(`/signups/${signupId}/ics`, `signup_${signupId}.ics`, {
        auth: true,
      });
    } catch (e) {
      toast.error(e?.message || "Download failed");
    }
  }

  function renderSignupCard(s, canCancel) {
    const timeLabel =
      s.slot_start_time && s.slot_end_time
        ? `${formatApiDateTimeLocal(s.slot_start_time)} - ${formatApiDateTimeLocal(
            s.slot_end_time,
          )}`
        : "Time unavailable";
    return (
      <Card key={s.id}>
        <h3 className="text-base font-semibold">
          {s.event_id ? (
            <Link to={`/events/${s.event_id}`}>
              {s.event_title || "Volunteer event"}
            </Link>
          ) : (
            s.event_title || "Volunteer event"
          )}
        </h3>
        <p className="text-sm text-[var(--color-fg-muted)]">
          {timeLabel}
          {s.event_location ? ` • ${s.event_location}` : ""}
        </p>
        <p className="text-xs text-[var(--color-fg-muted)] mt-1 flex items-center gap-1">
          <StatusIcon status={s.status} className="h-4 w-4 inline-block" />
          {/* TODO(copy): status label */}
          Status: {s.status}
          {s.status === "waitlisted" && s.waitlist_position
            ? ` (#${s.waitlist_position})`
            : ""}
        </p>
        <div className="flex gap-2 mt-3">
          <Button
            variant="secondary"
            onClick={() => downloadIcs(s.id)}
          >
            {/* TODO(copy) */}
            Download .ics
          </Button>
          {canCancel && s.status !== "cancelled" && (
            <Button
              variant="ghost"
              onClick={() => setPendingCancel(s)}
            >
              {/* TODO(copy) */}
              Cancel
            </Button>
          )}
        </div>
      </Card>
    );
  }

  return (
    <div>
      {/* TODO(copy) */}
      <PageHeader title="My Signups" />

      {signupsQ.isPending ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-32 w-full rounded-xl" />
          ))}
        </div>
      ) : signupsQ.error ? (
        <EmptyState
          /* TODO(copy) */
          title="Couldn't load signups"
          /* TODO(copy) */
          body={signupsQ.error.message}
          action={
            <Button onClick={() => signupsQ.refetch()}>
              {/* TODO(copy) */}
              Retry
            </Button>
          }
        />
      ) : sorted.length === 0 ? (
        <EmptyState
          /* TODO(copy) */
          title="You haven't signed up for anything"
          /* TODO(copy) */
          body="Find an event and grab a slot."
          action={
            <Button as={Link} to="/events">
              {/* TODO(copy) */}
              Browse events
            </Button>
          }
        />
      ) : (
        <>
          <section>
            {/* TODO(copy) */}
            <h2 className="text-sm font-medium text-[var(--color-fg-muted)] mt-6 mb-2 uppercase tracking-wide">
              Upcoming
            </h2>
            {upcoming.length === 0 ? (
              <p className="text-sm text-[var(--color-fg-muted)]">
                {/* TODO(copy) */}
                No upcoming signups.
              </p>
            ) : (
              <div className="space-y-3">
                {upcoming.map((s) => renderSignupCard(s, true))}
              </div>
            )}
          </section>

          <section>
            {/* TODO(copy) */}
            <h2 className="text-sm font-medium text-[var(--color-fg-muted)] mt-6 mb-2 uppercase tracking-wide">
              Past
            </h2>
            {past.length === 0 ? (
              <p className="text-sm text-[var(--color-fg-muted)]">
                {/* TODO(copy) */}
                No past signups.
              </p>
            ) : (
              <div className="space-y-3">
                {past.map((s) => renderSignupCard(s, false))}
              </div>
            )}
          </section>

          {/* Phase 4: Module Progress Timeline */}
          {timelineQ.data && timelineQ.data.length > 0 && (
            <section>
              {/* TODO(copy) */}
              <h2 className="text-sm font-medium text-[var(--color-fg-muted)] mt-6 mb-2 uppercase tracking-wide">
                Module Progress
              </h2>
              <ModuleTimeline modules={timelineQ.data} />
            </section>
          )}
        </>
      )}

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
          Cancel your signup for {pendingCancel?.event_title}? This can't be
          undone.
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
          <Button
            variant="danger"
            onClick={confirmCancel}
            disabled={busy}
          >
            {/* TODO(copy) */}
            Cancel signup
          </Button>
        </div>
      </Modal>
    </div>
  );
}
