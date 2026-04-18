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
import FormFieldsDrawer from "../components/admin/FormFieldsDrawer";
import DuplicateEventDrawer from "../components/admin/DuplicateEventDrawer";
import BroadcastModal from "../components/BroadcastModal";
import CheckInQRModal from "../components/admin/CheckInQRModal";
import { toast } from "../state/toast";
import { useAdminPageTitle } from "./admin/AdminLayout";
import { useAuth } from "../state/useAuth";

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
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [privacy, setPrivacy] = useState("full");
  const [confirmExport, setConfirmExport] = useState(false);
  const [err, setErr] = useState("");
  // Phase 22 — form fields drawer
  const [formFieldsOpen, setFormFieldsOpen] = useState(false);
  // Phase 23 — duplicate drawer
  const [duplicateOpen, setDuplicateOpen] = useState(false);
  // Phase 25 — waitlist reorder modal
  const [reorderState, setReorderState] = useState(null); // { slotId, ids: [...] }
  // Phase 26 — broadcast messages
  const [broadcastOpen, setBroadcastOpen] = useState(false);
  // Event-QR check-in (post-integration)
  const [qrOpen, setQrOpen] = useState(false);

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

  // Phase 25 — organizer manual waitlist promote (WAIT-03).
  const promoteMut = useMutation({
    mutationFn: (signupId) =>
      api.organizer.promoteSignup(eventId, signupId),
    onSuccess: () => {
      toast.success("Promoted from waitlist.");
      qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventAnalytics", eventId] });
    },
    onError: (e) => {
      toast.error(e?.message || "Promote failed");
    },
  });

  // Phase 25 — admin reorder waitlist (WAIT-05).
  const reorderMut = useMutation({
    mutationFn: ({ slotId, orderedIds }) =>
      api.admin.reorderWaitlist(eventId, slotId, orderedIds),
    onSuccess: () => {
      toast.success("Waitlist order saved.");
      qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
      setReorderState(null);
    },
    onError: (e) => {
      toast.error(e?.message || "Reorder failed");
    },
  });

  // Phase 23 — list sibling events in the same quarter/module so the
  // drawer can highlight conflict weeks.
  const siblingEventsQ = useQuery({
    queryKey: [
      "adminSiblingEvents",
      eventQ.data?.quarter,
      eventQ.data?.year,
      eventQ.data?.module_slug,
    ],
    enabled: !!eventQ.data?.quarter && !!eventQ.data?.year,
    queryFn: async () => {
      // Reuse public list endpoint across each week 1..11; cheap enough.
      const quarter = eventQ.data.quarter;
      const year = eventQ.data.year;
      const results = [];
      for (let w = 1; w <= 11; w += 1) {
        // eslint-disable-next-line no-await-in-loop
        const weekEvents = await api.public.listEvents({
          quarter,
          year,
          week_number: w,
        });
        for (const e of weekEvents || []) {
          if (e.module_slug === eventQ.data.module_slug) {
            results.push({
              id: e.id,
              module_slug: e.module_slug,
              week_number: e.week_number,
              year: e.year,
            });
          }
        }
      }
      return results;
    },
  });

  const duplicateMut = useMutation({
    mutationFn: (payload) => api.admin.duplicateEvent(eventId, payload),
    onSuccess: (result) => {
      const created = result?.created?.length || 0;
      const skipped = result?.skipped_conflicts?.length || 0;
      toast.success(
        `Created ${created} event${created === 1 ? "" : "s"}` +
          (skipped > 0 ? `, skipped ${skipped} conflict${skipped === 1 ? "" : "s"}.` : "."),
      );
      setDuplicateOpen(false);
      qc.invalidateQueries({ queryKey: ["adminSiblingEvents"] });
    },
    onError: (e) => {
      toast.error(e?.message || "Duplicate failed");
    },
  });

  // Phase 22 — effective form schema + save
  const formSchemaQ = useQuery({
    queryKey: ["eventFormSchema", eventId],
    queryFn: () => api.public.getFormSchema(eventId),
  });
  const setEventSchemaMut = useMutation({
    mutationFn: (schema) => api.admin.setEventFormSchema(eventId, schema),
    onSuccess: () => {
      toast.success("Form fields saved");
      setFormFieldsOpen(false);
      qc.invalidateQueries({ queryKey: ["eventFormSchema", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
    },
    onError: (e) => toast.error(e?.message || "Save failed"),
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
            <Button variant="secondary" onClick={() => setQrOpen(true)}>
              Show check-in QR
            </Button>
            <Button variant="secondary" onClick={() => setBroadcastOpen(true)}>
              Message volunteers
            </Button>
            <Button variant="secondary" onClick={() => setDuplicateOpen(true)}>
              Duplicate…
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
          Form fields
        </h2>
        <Card>
          {formSchemaQ.isPending ? (
            <Skeleton className="h-10" />
          ) : (
            <>
              <p className="text-sm text-[var(--color-fg-muted)] mb-2">
                {(formSchemaQ.data?.schema || []).length === 0
                  ? "No custom signup questions configured. Volunteers will see only the standard name / email / phone fields."
                  : `${(formSchemaQ.data?.schema || []).length} custom question${
                      (formSchemaQ.data?.schema || []).length === 1 ? "" : "s"
                    } on the signup form.`}
              </p>
              <Button onClick={() => setFormFieldsOpen(true)}>
                Edit form fields
              </Button>
            </>
          )}
        </Card>
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
            {grouped.map(({ slot, rows }) => {
              const waitlistedRows = rows.filter((r) => r.status === "waitlisted");
              return (
              <Card key={slot.id}>
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium">
                    Slot: {fmtDateTime(slot.start)} → {fmtDateTime(slot.end)}
                  </p>
                  {/* Phase 25 — admin-only reorder waitlist button per slot. */}
                  {isAdmin && waitlistedRows.length >= 2 && (
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={() =>
                        setReorderState({
                          slotId: slot.id,
                          ids: waitlistedRows
                            .slice()
                            .sort(
                              (a, b) =>
                                (a.waitlist_position ?? 0) -
                                (b.waitlist_position ?? 0),
                            )
                            .map((r) => ({
                              signup_id: r.signup_id || r.id,
                              name: r.user_name || r.user_email || r.user_id,
                            })),
                        })
                      }
                    >
                      Reorder waitlist
                    </Button>
                  )}
                </div>
                <ul className="mt-2 space-y-1">
                  {rows.map((r) => {
                    const name =
                      r.participant?.name ||
                      r.participant?.email ||
                      r.user_name ||
                      r.user_email ||
                      r.volunteer_id ||
                      r.user_id ||
                      "Volunteer";
                    const email = r.participant?.email;
                    return (
                      <li
                        key={r.signup_id || r.id}
                        className="text-sm py-1"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span>
                            {name}
                            {email && email !== name ? (
                              <span className="text-[var(--color-fg-muted)] ml-2">
                                ({email})
                              </span>
                            ) : null}
                          </span>
                          <span className="flex items-center gap-2">
                            <span className="text-[var(--color-fg-muted)]">
                              {r.status === "waitlisted" && r.waitlist_position
                                ? `waitlist #${r.waitlist_position}`
                                : r.status}
                            </span>
                            {r.status === "waitlisted" && (
                              <Button
                                type="button"
                                variant="primary"
                                data-testid="promote-btn"
                                onClick={() =>
                                  promoteMut.mutate(r.signup_id || r.id)
                                }
                                disabled={promoteMut.isPending}
                              >
                                Promote
                              </Button>
                            )}
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
                        </div>
                        {Array.isArray(r.responses) && r.responses.length > 0 && (
                          <dl className="mt-1 grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-[var(--color-fg-muted)]">
                            {r.responses.map((resp) => (
                              <div key={resp.field_id} className="flex gap-1">
                                <dt className="font-medium">{resp.label}:</dt>
                                <dd>
                                  {resp.value_text ??
                                    (resp.value_json
                                      ? JSON.stringify(resp.value_json)
                                      : "—")}
                                </dd>
                              </div>
                            ))}
                          </dl>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </Card>
              );
            })}
          </div>
        )}
      </section>

      {/* Phase 23 — duplicate event drawer */}
      <DuplicateEventDrawer
        open={duplicateOpen}
        onClose={() => setDuplicateOpen(false)}
        sourceEvent={
          eventQ.data
            ? {
                id: eventQ.data.id,
                title: eventQ.data.title,
                module_slug: eventQ.data.module_slug,
                quarter: eventQ.data.quarter,
                year: eventQ.data.year,
                week_number: eventQ.data.week_number,
              }
            : null
        }
        existingEvents={siblingEventsQ.data || []}
        submitting={duplicateMut.isPending}
        onSubmit={(payload) => duplicateMut.mutateAsync(payload)}
      />

      {/* Phase 22 — event form schema drawer */}
      <FormFieldsDrawer
        open={formFieldsOpen}
        onClose={() => setFormFieldsOpen(false)}
        title="Form fields — this event"
        schema={formSchemaQ.data?.schema || []}
        saving={setEventSchemaMut.isPending}
        onSave={(nextSchema) => setEventSchemaMut.mutate(nextSchema)}
      />

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

      {/* Phase 25 — admin reorder waitlist modal (WAIT-05). Up / down arrows
          reorder the waitlist; drag-and-drop is deferred to keep the phase
          scoped (context decision). */}
      <Modal
        open={!!reorderState}
        onClose={() => !reorderMut.isPending && setReorderState(null)}
        title="Reorder waitlist"
      >
        {reorderState && (
          <div className="space-y-3" data-testid="reorder-modal">
            <p className="text-sm text-[var(--color-fg-muted)]">
              Rearrange the waitlist to decide who gets promoted next. The top
              row is promoted first.
            </p>
            <ol className="space-y-1">
              {reorderState.ids.map((row, idx) => (
                <li
                  key={row.signup_id}
                  className="flex items-center justify-between gap-2 rounded border border-[var(--color-border)] px-2 py-1 text-sm"
                >
                  <span>
                    #{idx + 1} {row.name}
                  </span>
                  <span className="flex items-center gap-1">
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={idx === 0 || reorderMut.isPending}
                      onClick={() =>
                        setReorderState((prev) => {
                          if (!prev) return prev;
                          const next = prev.ids.slice();
                          [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                          return { ...prev, ids: next };
                        })
                      }
                      aria-label="Move up"
                    >
                      Up
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={
                        idx === reorderState.ids.length - 1 ||
                        reorderMut.isPending
                      }
                      onClick={() =>
                        setReorderState((prev) => {
                          if (!prev) return prev;
                          const next = prev.ids.slice();
                          [next[idx + 1], next[idx]] = [next[idx], next[idx + 1]];
                          return { ...prev, ids: next };
                        })
                      }
                      aria-label="Move down"
                    >
                      Down
                    </Button>
                  </span>
                </li>
              ))}
            </ol>
            <div className="flex justify-end gap-2">
              <Button
                variant="ghost"
                onClick={() => setReorderState(null)}
                disabled={reorderMut.isPending}
              >
                Cancel
              </Button>
              <Button
                onClick={() =>
                  reorderMut.mutate({
                    slotId: reorderState.slotId,
                    orderedIds: reorderState.ids.map((r) => r.signup_id),
                  })
                }
                disabled={reorderMut.isPending}
              >
                {reorderMut.isPending ? "Saving…" : "Save order"}
              </Button>
            </div>
          </div>
        )}
      </Modal>

      {/* Phase 26 — broadcast messages */}
      <BroadcastModal
        open={broadcastOpen}
        onClose={() => setBroadcastOpen(false)}
        eventId={eventId}
        scope={isAdmin ? "admin" : "organizer"}
      />

      {/* Event-QR check-in (post-integration) */}
      <CheckInQRModal
        open={qrOpen}
        onClose={() => setQrOpen(false)}
        eventId={eventId}
        eventTitle={eventTitle}
      />
    </div>
  );
}
