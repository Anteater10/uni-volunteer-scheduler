// AdminEventPage.jsx
import React, { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  Modal,
  Label,
  Input,
  FieldError,
  EmptyState,
  Skeleton,
} from "../components/ui";
import { toast } from "../state/toast";
import { useAdminPageTitle } from "./admin/AdminLayout";

function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function StatCard({ label, value }) {
  return (
    <Card>
      <p className="text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold">{value ?? "—"}</p>
    </Card>
  );
}

function DetailRow({ label, value }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">
        {label}
      </dt>
      <dd className="mt-0.5">{value}</dd>
    </div>
  );
}

export default function AdminEventPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
  const [privacy, setPrivacy] = useState("full");
  const [confirmExport, setConfirmExport] = useState(false);
  const [err, setErr] = useState("");

  const analyticsQ = useQuery({
    queryKey: ["adminEventAnalytics", eventId],
    queryFn: () => api.admin.eventAnalytics(eventId),
  });

  const eventQ = useQuery({
    queryKey: ["adminEventDetail", eventId],
    queryFn: () => api.events.get(eventId),
  });

  const rosterQ = useQuery({
    queryKey: ["adminEventRoster", eventId, privacy],
    queryFn: () => api.admin.eventRoster(eventId, privacy),
  });

  const eventTitle =
    eventQ.data?.title ||
    analyticsQ.data?.title ||
    "Event";
  useAdminPageTitle(eventTitle);

  const roster = rosterQ.data || [];

  // Phase 21 — one-tap orientation credit grant from roster.
  const grantOrientationMut = useMutation({
    mutationFn: (signupId) =>
      api.organizer.grantOrientation(eventId, signupId),
    onSuccess: () => {
      toast.success("Orientation credit granted.");
      qc.invalidateQueries({
        queryKey: ["adminEventRoster", eventId],
      });
    },
    onError: (err) => {
      toast.error(err?.message || "Grant failed");
    },
  });

  const grouped = useMemo(() => {
    const map = new Map();
    for (const r of roster) {
      const key = r.slot_id;
      if (!map.has(key)) map.set(key, { slot: { id: key, start: r.slot_start, end: r.slot_end }, rows: [] });
      map.get(key).rows.push(r);
    }
    return Array.from(map.values());
  }, [roster]);

  async function doExport() {
    setErr("");
    try {
      await downloadBlob(
        `/admin/events/${eventId}/export?privacy=${privacy}`,
        `event_${eventId}_roster.csv`,
        { auth: true },
      );
      setConfirmExport(false);
      toast.success("Roster CSV download started.");
    } catch (e) {
      setErr(e?.message || "Export failed");
    }
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title={eventTitle}
        action={
          <div className="flex gap-2">
            <Button as={Link} to={`/organizer/events/${eventId}/roster`}>
              Live roster (check-in)
            </Button>
            <Button variant="secondary" onClick={() => setConfirmExport(true)}>
              Download roster CSV
            </Button>
          </div>
        }
      />

      <Card>
        <div>
          <Label htmlFor="privacy">Who can see volunteer names on this roster?</Label>
          <select
            id="privacy"
            value={privacy}
            onChange={(e) => setPrivacy(e.target.value)}
            className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
          >
            <option value="full">Show full names</option>
            <option value="minimal">Show initials only</option>
          </select>
        </div>
        <FieldError>{err}</FieldError>
      </Card>

      <section>
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Attendance summary
        </h2>
        {analyticsQ.isPending ? (
          <Skeleton className="h-24" />
        ) : analyticsQ.error ? (
          <EmptyState
            title="Couldn't load attendance summary"
            body={analyticsQ.error.message}
            action={
              <Button onClick={() => analyticsQ.refetch()}>Try again</Button>
            }
          />
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <StatCard label="Total slots" value={analyticsQ.data.total_slots} />
            <StatCard label="Total capacity" value={analyticsQ.data.total_capacity} />
            <StatCard label="Confirmed" value={analyticsQ.data.confirmed_signups} />
            <StatCard label="Waitlisted" value={analyticsQ.data.waitlisted_signups} />
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Event details
        </h2>
        {eventQ.isPending ? (
          <Skeleton className="h-32" />
        ) : eventQ.error ? (
          <EmptyState
            title="Couldn't load event"
            body={eventQ.error.message}
            action={<Button onClick={() => eventQ.refetch()}>Try again</Button>}
          />
        ) : (
          <Card>
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3 text-sm">
              <DetailRow label="Location" value={eventQ.data.location || "—"} />
              <DetailRow label="Visibility" value={eventQ.data.visibility || "—"} />
              <DetailRow label="Starts" value={fmtDateTime(eventQ.data.start_at)} />
              <DetailRow label="Ends" value={fmtDateTime(eventQ.data.end_at)} />
              <DetailRow
                label="Max signups per user"
                value={eventQ.data.max_signups_per_user ?? "—"}
              />
              <DetailRow
                label="Created"
                value={fmtDateTime(eventQ.data.created_at)}
              />
            </dl>
            {eventQ.data.description ? (
              <div className="mt-4">
                <p className="text-xs uppercase tracking-wide text-[var(--color-fg-muted)] mb-1">
                  Description
                </p>
                <p className="text-sm whitespace-pre-wrap">{eventQ.data.description}</p>
              </div>
            ) : null}
          </Card>
        )}
      </section>

      <section>
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Signed-up volunteers
        </h2>
        {rosterQ.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-20" />
            ))}
          </div>
        ) : rosterQ.error ? (
          <EmptyState
            title="Couldn't load roster"
            body={rosterQ.error.message}
            action={
              <Button onClick={() => qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] })}>
                Try again
              </Button>
            }
          />
        ) : grouped.length === 0 ? (
          <EmptyState
            title="No one has signed up yet"
            body="As soon as volunteers start signing up, they will appear here."
          />
        ) : (
          <div className="space-y-3">
            {grouped.map(({ slot, rows }) => (
              <Card key={slot.id}>
                <p className="text-sm font-medium">
                  Slot: {fmtDateTime(slot.start)} → {fmtDateTime(slot.end)}
                </p>
                <ul className="mt-2 space-y-1">
                  {rows.map((r) => (
                    <li
                      key={r.signup_id || r.id}
                      className="text-sm flex flex-wrap items-center justify-between gap-2"
                    >
                      <span>{r.user_name || r.user_email || r.user_id}</span>
                      <span className="flex items-center gap-2">
                        <span className="text-[var(--color-fg-muted)]">
                          {r.status}
                        </span>
                        {/* Phase 21 — one-tap orientation credit grant */}
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() =>
                            grantOrientationMut.mutate(r.signup_id || r.id)
                          }
                          disabled={grantOrientationMut.isPending}
                        >
                          Grant orientation
                        </Button>
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            ))}
          </div>
        )}
      </section>

      <Modal
        open={confirmExport}
        onClose={() => setConfirmExport(false)}
        title="Download roster CSV"
      >
        <p className="text-sm">
          Download the roster for this event as a CSV file? Volunteer names
          will be shown using the privacy setting you selected
          ({privacy === "full" ? "full names" : "initials only"}).
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setConfirmExport(false)}>
            Cancel
          </Button>
          <Button onClick={doExport}>
            Download CSV
          </Button>
        </div>
      </Modal>
    </div>
  );
}
