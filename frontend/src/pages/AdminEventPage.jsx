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
  Input,
  FieldError,
  EmptyState,
  Skeleton,
} from "../components/ui";
import {
  ClipboardCheck,
  Copy,
  Download,
  Mail,
  QrCode,
  Settings,
} from "lucide-react";
import FormFieldsDrawer from "../components/admin/FormFieldsDrawer";
import EventSettingsModal from "../components/admin/EventSettingsModal";
import DuplicateEventDrawer from "../components/admin/DuplicateEventDrawer";
import BroadcastModal from "../components/BroadcastModal";
import CheckInQRModal from "../components/admin/CheckInQRModal";
import { toast } from "../state/toast";
import { useQuarters } from "../lib/useQuarters";
import { findQuarterById } from "../lib/weekUtils";
import { useAdminPageTitle } from "./admin/AdminLayout";
import { useAuth } from "../state/useAuth";

// Issue #31 — slot headers lead with the weekday ("Tuesday, Sep 29, 2026").
function fmtSlotDay(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      weekday: "long",
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function fmtTimeRange(startIso, endIso) {
  const fmt = (iso) =>
    iso
      ? new Date(iso).toLocaleTimeString(undefined, {
          hour: "numeric",
          minute: "2-digit",
        })
      : "";
  const start = fmt(startIso);
  const end = fmt(endIso);
  return end ? `${start} – ${end}` : start || "—";
}

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

// A roster can run to ninety-odd rows across seventeen slots, so status has to
// be readable at a glance rather than as another run of grey lowercase text.
const STATUS_STYLES = {
  confirmed: "bg-green-100 text-green-800",
  checked_in: "bg-[var(--color-brand-soft)] text-[var(--color-brand)]",
  attended: "bg-[var(--color-brand-soft)] text-[var(--color-brand)]",
  waitlisted: "bg-amber-100 text-amber-800",
  pending: "bg-slate-100 text-slate-700",
  no_show: "bg-red-100 text-red-700",
  cancelled: "bg-slate-100 text-slate-500 line-through",
};

function StatusPill({ status, waitlistPosition }) {
  const label =
    status === "waitlisted" && waitlistPosition
      ? `Waitlist #${waitlistPosition}`
      : String(status || "—").replace(/_/g, " ");
  return (
    <span
      className={
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium capitalize " +
        (STATUS_STYLES[status] || "bg-slate-100 text-slate-700")
      }
    >
      {label}
    </span>
  );
}

function StatCard({ label, value }) {
  return (
    <Card>
      <p className="text-sm uppercase tracking-wide text-[var(--color-fg-muted)] font-medium">
        {label}
      </p>
      <p className="mt-1 text-3xl font-semibold">{value ?? "—"}</p>
    </Card>
  );
}

function DetailRow({ label, value }) {
  return (
    <div>
      <dt className="text-sm uppercase tracking-wide text-[var(--color-fg-muted)] font-medium">
        {label}
      </dt>
      <dd className="mt-1 text-base">{value}</dd>
    </div>
  );
}

export default function AdminEventPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
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
  // Reconfigure title / where / when / slots without going back to the list
  const [settingsOpen, setSettingsOpen] = useState(false);

  const analyticsQ = useQuery({
    queryKey: ["adminEventAnalytics", eventId],
    queryFn: () => api.admin.eventAnalytics(eventId),
  });

  const eventQ = useQuery({
    queryKey: ["adminEventDetail", eventId],
    queryFn: () => api.events.get(eventId),
  });

  // Admins and organizers always see full names — this is the staff-side
  // roster, and the initials-only view just made check-in harder. The
  // endpoint still takes a privacy argument for the public event page.
  const rosterQ = useQuery({
    queryKey: ["adminEventRoster", eventId, "full"],
    queryFn: () => api.admin.eventRoster(eventId, "full"),
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
    mutationFn: ({ signupId, allowOverfill = false }) =>
      api.organizer.promoteSignup(eventId, signupId, { allowOverfill }),
    onSuccess: () => {
      toast.success("Promoted from waitlist.");
      qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventAnalytics", eventId] });
    },
    onError: (e) => {
      // "slot is full" isn't an error the organizer needs shouting at them —
      // the click handler turns it into the over-capacity confirmation.
      if (/full/i.test(e?.message || "")) return;
      toast.error(e?.message || "Promote failed");
    },
  });

  // Admin/organizer cancel signup (triggers Phase 25 FIFO auto-promote).
  const cancelMut = useMutation({
    mutationFn: (signupId) => api.admin.signups.cancel(signupId),
    onSuccess: () => {
      toast.success("Signup cancelled.");
      qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventAnalytics", eventId] });
    },
    onError: (e) => toast.error(e?.message || "Cancel failed"),
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
  // drawer can highlight conflict weeks. Issue #24: keyed on the quarter
  // ROW (quarter_id) with its real week count — session-aware.
  const quartersQ = useQuarters();
  const eventQuarterRow = findQuarterById(
    quartersQ.data || [],
    eventQ.data?.quarter_id,
  );
  const siblingEventsQ = useQuery({
    queryKey: [
      "adminSiblingEvents",
      eventQ.data?.quarter_id,
      eventQ.data?.module_slug,
    ],
    enabled: !!eventQ.data?.quarter_id && !!eventQuarterRow,
    queryFn: async () => {
      // Reuse public list endpoint across each week of the quarter row.
      const quarterId = eventQ.data.quarter_id;
      const results = [];
      for (let w = 1; w <= eventQuarterRow.weeks_in_quarter; w += 1) {
        // eslint-disable-next-line no-await-in-loop
        const weekEvents = await api.public.listEvents({
          quarter_id: quarterId,
          week_number: w,
        });
        for (const e of weekEvents || []) {
          if (e.module_slug === eventQ.data.module_slug) {
            results.push({
              id: e.id,
              module_slug: e.module_slug,
              week_number: e.week_number,
              year: e.year,
              quarter: e.quarter,
              quarter_id: e.quarter_id,
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
      if (!map.has(key))
        map.set(key, {
          slot: {
            id: key,
            start: r.slot_start,
            end: r.slot_end,
            // Issue #31 — headers name the slot kind and location.
            type: r.slot_type,
            location: r.slot_location,
          },
          rows: [],
        });
      map.get(key).rows.push(r);
    }
    return Array.from(map.values());
  }, [roster]);

  async function doExport() {
    setErr("");
    try {
      await downloadBlob(
        `/admin/events/${eventId}/export_csv`,
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
          /* Six actions no longer fit on one line, and letting the labels
             wrap inside the buttons looked broken. Wrap the row instead, keep
             each label on one line, and lead each with an icon so the row
             stays scannable once it spills. */
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              as={Link}
              to={`/admin/events/${eventId}/roster`}
              className="whitespace-nowrap"
            >
              <ClipboardCheck className="h-4 w-4" />
              Live roster (check-in)
            </Button>
            <Button
              variant="secondary"
              onClick={() => setSettingsOpen(true)}
              className="whitespace-nowrap"
            >
              <Settings className="h-4 w-4" />
              Event settings
            </Button>
            <Button
              variant="secondary"
              onClick={() => setQrOpen(true)}
              className="whitespace-nowrap"
            >
              <QrCode className="h-4 w-4" />
              Check-in QR
            </Button>
            <Button
              variant="secondary"
              onClick={() => setBroadcastOpen(true)}
              className="whitespace-nowrap"
            >
              <Mail className="h-4 w-4" />
              Message volunteers
            </Button>
            {/* Duplicating an event is admin-only on the server. Rendering it
                for organizers meant filling in the whole week-picker drawer and
                only then being told no. */}
            {isAdmin ? (
              <Button
                variant="secondary"
                onClick={() => setDuplicateOpen(true)}
                className="whitespace-nowrap"
              >
                <Copy className="h-4 w-4" />
                Duplicate…
              </Button>
            ) : null}
            <Button
              variant="secondary"
              onClick={() => setConfirmExport(true)}
              className="whitespace-nowrap"
            >
              <Download className="h-4 w-4" />
              Roster CSV
            </Button>
          </div>
        }
      />

      {/* Page-level errors (e.g. a failed CSV export) used to live in the
          privacy-setting card. That card is gone, so only surface the strip
          when there is something to say. */}
      {err ? (
        <Card>
          <FieldError>{err}</FieldError>
        </Card>
      ) : null}

      <section>
        <h2 className="text-base font-semibold text-[var(--color-fg-muted)] uppercase tracking-wide mb-3">
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
        <h2 className="mb-3 text-base font-semibold text-[var(--color-fg-muted)] uppercase tracking-wide">
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
            <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 text-base">
              <DetailRow label="Location" value={eventQ.data.location || "—"} />
              <DetailRow label="Visibility" value={eventQ.data.visibility || "—"} />
              <DetailRow label="Starts" value={fmtDateTime(eventQ.data.start_date)} />
              <DetailRow label="Ends" value={fmtDateTime(eventQ.data.end_date)} />
              <DetailRow
                label="Max signups per user"
                value={eventQ.data.max_signups_per_user ?? "No limit"}
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
        <h2 className="text-base font-semibold text-[var(--color-fg-muted)] uppercase tracking-wide mb-3">
          Form fields
        </h2>
        <Card>
          {formSchemaQ.isPending ? (
            <Skeleton className="h-10" />
          ) : (() => {
            const schema = formSchemaQ.data?.schema || [];
            const count = schema.length;
            return (
              <>
                <div className="flex items-start justify-between gap-3 mb-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium">Extra signup questions</p>
                    <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                      {count === 0
                        ? "None yet — name, email, and phone are always collected."
                        : `${count} question${count === 1 ? "" : "s"} on this event's signup form.`}
                    </p>
                  </div>
                  <Button onClick={() => setFormFieldsOpen(true)}>
                    {count === 0 ? "Add a question" : "Edit"}
                  </Button>
                </div>
                {count > 0 && (
                  <ul className="flex flex-col gap-1.5">
                    {schema.map((f) => (
                      <li
                        key={f.id}
                        className="flex items-center justify-between gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm"
                      >
                        <span className="truncate">{f.label}</span>
                        <span className="flex items-center gap-2 text-xs text-[var(--color-fg-muted)] shrink-0">
                          <span className="uppercase tracking-wide">{f.type}</span>
                          {f.required && (
                            <span className="rounded-full bg-red-100 text-red-700 px-2 py-0.5 font-medium">
                              Required
                            </span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
                <p className="text-xs text-[var(--color-fg-muted)] mt-3">
                  Answers appear on the roster and in the CSV export.
                </p>
              </>
            );
          })()}
        </Card>
      </section>

      <section>
        <h2 className="text-base font-semibold text-[var(--color-fg-muted)] uppercase tracking-wide mb-3">
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
              // Not <Card>: its padding is baked in and cn() is a plain join
              // with no Tailwind conflict resolution, so p-0 can't override it.
              // The table needs to run edge to edge.
              <div
                key={slot.id}
                className="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] shadow-sm"
              >
                {/* Group header: tinted band so each slot reads as its own
                    table rather than one continuous wall of names. */}
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3">
                  <p className="text-sm font-medium">
                    {/* Issue #31 — say what kind of shift this is and which
                        day, so orientation vs module rosters read at a glance. */}
                    <span
                      className={`mr-2 inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${
                        slot.type === "orientation"
                          ? "bg-purple-100 text-purple-700"
                          : "bg-blue-100 text-blue-700"
                      }`}
                    >
                      {slot.type === "orientation" ? "Orientation" : "Module"}
                    </span>
                    {fmtSlotDay(slot.start)} · {fmtTimeRange(slot.start, slot.end)}
                    {slot.location ? (
                      <span className="font-normal text-[var(--color-fg-muted)]">
                        {" "}· {slot.location}
                      </span>
                    ) : null}
                  </p>
                  <div className="flex items-center gap-2">
                  <span className="rounded-full border border-[var(--color-border)] bg-white px-2 py-0.5 text-xs font-medium tabular-nums text-[var(--color-fg-muted)]">
                    {rows.length} signed up
                  </span>
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
                </div>
                <div className="overflow-x-auto">
                <table className="w-full border-collapse text-sm">
                  {/* Column headers repeat per slot rather than once at the
                      top: each slot table scrolls past independently, so a
                      single shared header would be off-screen immediately. */}
                  <thead>
                    <tr className="border-b border-[var(--color-border)] text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">
                      <th scope="col" className="px-4 py-2 text-left font-semibold">
                        Volunteer
                      </th>
                      <th scope="col" className="px-4 py-2 text-left font-semibold">
                        Status
                      </th>
                      <th scope="col" className="px-4 py-2 text-right font-semibold">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--color-border)]">
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
                      <tr
                        key={r.signup_id || r.id}
                        className="align-top transition-colors hover:bg-[var(--color-brand-soft)]/50"
                      >
                        <td className="px-4 py-2.5">
                          <div className="font-medium">{name}</div>
                          {email && email !== name ? (
                            <div className="text-xs text-[var(--color-fg-muted)]">
                              {email}
                            </div>
                          ) : null}
                          {Array.isArray(r.responses) && r.responses.length > 0 && (
                            <dl className="mt-1.5 grid grid-cols-1 gap-x-4 gap-y-1 text-xs text-[var(--color-fg-muted)] sm:grid-cols-2">
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
                        </td>
                        <td className="px-4 py-2.5 whitespace-nowrap">
                          <StatusPill
                            status={r.status}
                            waitlistPosition={r.waitlist_position}
                          />
                        </td>
                        <td className="px-4 py-2 text-right">
                          <div className="inline-flex items-center justify-end gap-2">
                            {r.status === "waitlisted" && (
                              <Button
                                type="button"
                                variant="primary"
                                data-testid="promote-btn"
                                onClick={async () => {
                                  const signupId = r.signup_id || r.id;
                                  try {
                                    await promoteMut.mutateAsync({ signupId });
                                  } catch (err) {
                                    // A full slot is the usual reason this
                                    // person is waitlisted, so "no" isn't a
                                    // useful answer — ask whether to seat
                                    // them over capacity and retry if so.
                                    if (
                                      !/full/i.test(err?.message || "") ||
                                      !window.confirm(
                                        `This slot is already at capacity. Promote ${name} anyway, putting the slot one over?`,
                                      )
                                    ) {
                                      return;
                                    }
                                    promoteMut.mutate({
                                      signupId,
                                      allowOverfill: true,
                                    });
                                  }
                                }}
                                disabled={promoteMut.isPending}
                              >
                                Promote
                              </Button>
                            )}
                            {/* Not for cancelled signups — the volunteer isn't
                                coming, so there's no attendance to credit. The
                                server rejects it now too. */}
                            {r.status !== "cancelled" && (
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
                            )}
                            {r.status !== "cancelled" && (
                              <Button
                                type="button"
                                variant="ghost"
                                onClick={() => {
                                  if (
                                    window.confirm(
                                      `Cancel ${name}'s signup? If this was a confirmed seat, the next person on the waitlist will auto-promote.`
                                    )
                                  ) {
                                    cancelMut.mutate(r.signup_id || r.id);
                                  }
                                }}
                                disabled={cancelMut.isPending}
                              >
                                Cancel
                              </Button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                  </tbody>
                </table>
                </div>
              </div>
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
                quarter_id: eventQ.data.quarter_id,
              }
            : null
        }
        existingEvents={siblingEventsQ.data || []}
        quarters={quartersQ.data}
        submitting={duplicateMut.isPending}
        onSubmit={(payload) => duplicateMut.mutateAsync(payload)}
      />

      {/* Reconfigure the event in place — same form the Events list uses. */}
      <EventSettingsModal
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        event={eventQ.data}
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
          Download the roster for this event as a CSV file? Volunteer full
          names and contact details are included.
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
