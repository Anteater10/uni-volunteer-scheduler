import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../state/useAuth";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchRoster,
  checkInSignup,
  undoCheckInSignup,
  checkInSession,
  undoCheckInSession,
  reopenEvent,
  reopenSlot,
  isSlotClosedError,
} from "../api/roster";
import { fmtVenueDate, fmtVenueTime } from "../lib/venueTime";
import api from "../lib/api";
import { PageHeader, Button, Skeleton, Modal, Input, Label } from "../components/ui";
import { toast } from "../state/toast";
import NoShowFlag from "../components/NoShowFlag";
import ResolveEventModal from "../components/ResolveEventModal";
import BroadcastModal from "../components/BroadcastModal";
// The same modal the desktop event page uses. Organizers run check-in from
// a phone as often as a laptop, and every /admin/* route is behind the
// desktop-only banner, so without this the QR was laptop-only for them.
import CheckInQRModal from "../components/admin/CheckInQRModal";

// Phase 22 — organizer quick-add custom field modal
function QuickAddFieldModal({ open, onClose, onSubmit, saving }) {
  const [label, setLabel] = useState("");
  const [type, setType] = useState("text");
  const [required, setRequired] = useState(false);
  const [options, setOptions] = useState("");
  function reset() {
    setLabel("");
    setType("text");
    setRequired(false);
    setOptions("");
  }
  function handleClose() {
    reset();
    onClose && onClose();
  }
  function handleSubmit(e) {
    e.preventDefault();
    if (!label.trim()) return;
    const id = label
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 48);
    const field = { id, label: label.trim(), type, required };
    if (["select", "radio", "checkbox"].includes(type)) {
      field.options = options
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      if (field.options.length === 0) {
        toast.error("Options are required for this field type.");
        return;
      }
    }
    onSubmit(field, () => reset());
  }
  return (
    <Modal open={open} onClose={handleClose} title="Add a custom question">
      <form onSubmit={handleSubmit} className="space-y-3">
        <div>
          <Label htmlFor="qaf-label">Question</Label>
          <Input
            id="qaf-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="e.g. Parking pass needed?"
            required
          />
        </div>
        <div>
          <Label htmlFor="qaf-type">Answer type</Label>
          <select
            id="qaf-type"
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
          >
            <option value="text">Short text</option>
            <option value="textarea">Long text</option>
            <option value="select">Dropdown</option>
            <option value="radio">Radio</option>
            <option value="checkbox">Checkboxes</option>
            <option value="phone">Phone</option>
            <option value="email">Email</option>
          </select>
        </div>
        {["select", "radio", "checkbox"].includes(type) && (
          <div>
            <Label htmlFor="qaf-options">Options (comma-separated)</Label>
            <Input
              id="qaf-options"
              value={options}
              onChange={(e) => setOptions(e.target.value)}
              placeholder="yes, no"
              required
            />
          </div>
        )}
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={required}
            onChange={(e) => setRequired(e.target.checked)}
          />
          Required
        </label>
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={saving}>
            {saving ? "Adding..." : "Add field"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}

// Issue #31 — slot section header, e.g. "Sun, Jul 26 · 9:00 AM – 10:00 AM".
// The date matters: a multi-day event otherwise shows two identical-looking
// time-only sections and the organizer can't tell which day is which.
// 2026-10-13: in venue (Pacific) time, like the public page — the browser's
// own timezone put a laptop east of Pacific on the wrong hour.
function fmtSlotRange(startIso, endIso) {
  const start = fmtVenueTime(startIso);
  const end = fmtVenueTime(endIso);
  const range = end ? `${start} – ${end}` : start;
  const date = fmtVenueDate(startIso || endIso);
  return date ? `${date} · ${range}` : range;
}

// Screen-reader name for a slot's End / Reopen button: every section has
// one, so "End slot" alone doesn't say which. e.g. "Tue morning · Period 1,
// Tue, Oct 6 · 9:00 AM – 10:00 AM".
function groupLabel(group) {
  const name = group.shiftName
    ? [group.shiftName, group.sessionName].filter(Boolean).join(" · ")
    : null;
  return [name, fmtSlotRange(group.start, group.end)].filter(Boolean).join(", ");
}

// 2026-10-13 (Kim's report): "attended" and "no show" exist only on a closed
// slot. While a slot is open a seated volunteer is either checked in or not,
// and pending and confirmed both read "not checked in" — the organizer has no
// use for the difference at the door, and showing it made them look like two
// different states to act on.
// Both read "not checked in" and both are what a tap checks in.
const NOT_CHECKED_IN = ["pending", "confirmed"];

// Issue #189: a stray attended / no show left on an OPEN slot (old "End
// event" data) reads as what it means while the slot is open — checked in, or
// not — so staff can tap it like any other card. The QR page sends the
// volunteer to staff for exactly this. A closed slot shows results as they are.
const OPEN_SLOT_STATUS = { attended: "checked_in", no_show: "confirmed" };

function openSlotStatus(r) {
  return r.slot_closed_at ? r.status : OPEN_SLOT_STATUS[r.status] || r.status;
}

// TODO(brand): final status chip palette
const CHIP = {
  checked_in: ["checked in", "bg-green-200 text-green-800"],
  not_checked_in: ["not checked in", "bg-gray-200 text-gray-800"],
  attended: ["attended", "bg-emerald-300 text-emerald-900"],
  no_show: ["no show", "bg-red-200 text-red-800"],
  waitlisted: ["waitlisted", "bg-purple-100 text-purple-800"],
  cancelled: ["cancelled", "bg-gray-100 text-gray-500 line-through"],
};

function chipFor(status) {
  if (NOT_CHECKED_IN.includes(status)) return CHIP.not_checked_in;
  return CHIP[status] || [String(status).replace("_", " "), "bg-gray-100"];
}

const NOT_STARTED_HINT =
  "This session hasn't started yet — you can close it once it starts.";

const SLOT_CLOSED_MESSAGE =
  "This slot is closed — reopen it to change attendance.";

function RosterStat({ label, value, tone = "default" }) {
  const toneClass = {
    default: "bg-white border-gray-200",
    green: "bg-green-50 border-green-200 text-green-900",
    amber: "bg-amber-50 border-amber-200 text-amber-900",
    blue: "bg-blue-50 border-blue-200 text-blue-900",
  }[tone];
  return (
    <div className={`rounded-xl border ${toneClass} px-5 py-4 shadow-sm`}>
      <p className="text-xs uppercase tracking-wide opacity-70 font-medium">
        {label}
      </p>
      <p className="mt-1 text-3xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}

export default function OrganizerRosterPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
  const [qrOpen, setQrOpen] = useState(false);
  const { role } = useAuth();
  const backTarget =
    role === "admin" ? `/admin/events/${eventId}` : "/admin/events";
  // "End event" offers only sessions that have started, judged at the moment
  // the button is pressed. Null while the event-mode modal is closed.
  const [resolveOpenedAt, setResolveOpenedAt] = useState(null);
  // Grant-on-slot-end (2026-07-24): per-slot "End slot" — holds the slot
  // group being resolved, or null when the modal is closed.
  const [resolveSlotGroup, setResolveSlotGroup] = useState(null);
  const [quickFieldOpen, setQuickFieldOpen] = useState(false);
  // Phase 26 — broadcast modal
  const [broadcastOpen, setBroadcastOpen] = useState(false);

  // Phase 22 — organizer quick-add field
  const quickFieldMut = useMutation({
    mutationFn: (field) => api.organizer.appendEventField(eventId, field),
    onSuccess: () => {
      toast.success("Question added to this event's signup form.");
      setQuickFieldOpen(false);
      qc.invalidateQueries({ queryKey: ["publicEventFormSchema", eventId] });
    },
    onError: (err) => toast.error(err?.message || "Failed to add field"),
  });

  const rosterQ = useQuery({
    queryKey: ["roster", eventId],
    queryFn: () => fetchRoster(eventId),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
    meta: { errorMessage: "Failed to load roster" },
  });

  // fix/ux-quarter-batch — undo "End event". The server reopens every closed
  // slot (attended goes back to checked in, keeping its timestamp; no show
  // back to not checked in) and clears the event's completed stamp;
  // orientation credits are left for the next close to reconcile.
  const reopenMut = useMutation({
    mutationFn: () => reopenEvent(eventId),
    onSuccess: (fresh) => {
      qc.setQueryData(["roster", eventId], fresh);
      qc.invalidateQueries({ queryKey: ["roster", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      toast.success("Event reopened — volunteers are back on the live roster.");
    },
    onError: (err) => toast.error(err?.message || "Couldn't reopen the event"),
  });

  // 2026-10-13: reopen one closed slot so a mistake can be fixed — same
  // conversion as reopening the event, for this slot only.
  const reopenSlotMut = useMutation({
    mutationFn: (slotId) => reopenSlot(slotId),
    onSuccess: (fresh) => {
      if (fresh) qc.setQueryData(["roster", eventId], fresh);
      qc.invalidateQueries({ queryKey: ["roster", eventId] });
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      toast.success("Slot reopened — tap volunteers to change attendance, then end it again.");
    },
    onError: (err) => toast.error(err?.message || "Couldn't reopen the slot"),
  });

  // 2026-08-05 shifts: a card is one volunteer at one *session*, so the
  // mutations take the whole row. A shift row has no signup_id — passing one
  // through was a request to /signups/undefined/check-in — and check-in is
  // keyed on (commitment, session) because a Tue+Wed volunteer is checked in
  // once per day and can be present Tuesday and absent Wednesday.
  const rowMatches = (r, target) =>
    target.shift_signup_id
      ? r.shift_signup_id === target.shift_signup_id &&
        r.slot_id === target.slot_id
      : r.signup_id === target.signup_id;

  // Optimistic tap: flip one card and the headline count straight away, and
  // remember the roster as it was so a failed request can roll back.
  async function applyTap(row, status, delta) {
    await qc.cancelQueries({ queryKey: ["roster", eventId] });
    const prev = qc.getQueryData(["roster", eventId]);
    qc.setQueryData(
      ["roster", eventId],
      (old) =>
        old && {
          ...old,
          checked_in_count: Math.max(0, (old.checked_in_count || 0) + delta),
          rows: old.rows.map((r) => (rowMatches(r, row) ? { ...r, status } : r)),
        },
    );
    return { prev };
  }

  const checkInMut = useMutation({
    mutationFn: (row) =>
      row.shift_signup_id
        ? checkInSession(row.shift_signup_id, row.slot_id)
        : checkInSignup(row.signup_id),
    onMutate: (row) => applyTap(row, "checked_in", 1),
    onError: (err, _row, context) => {
      // Rollback
      if (context?.prev) {
        qc.setQueryData(["roster", eventId], context.prev);
      }
      // A closed slot isn't a retryable failure; onSettled refetches so the
      // card shows the slot's real, locked state.
      toast.error(
        isSlotClosedError(err) ? SLOT_CLOSED_MESSAGE : "Check-in failed. Please retry.",
      );
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["roster", eventId] });
    },
  });

  // Issue #31 — mis-tap recovery: tapping a checked-in card reverts it.
  const undoMut = useMutation({
    mutationFn: (row) =>
      row.shift_signup_id
        ? undoCheckInSession(row.shift_signup_id, row.slot_id)
        : undoCheckInSignup(row.signup_id),
    onMutate: (row) => applyTap(row, "confirmed", -1),
    onError: (err, _row, context) => {
      if (context?.prev) {
        qc.setQueryData(["roster", eventId], context.prev);
      }
      toast.error(
        isSlotClosedError(err) ? SLOT_CLOSED_MESSAGE : "Undo failed. Please retry.",
      );
    },
    onSuccess: () => {
      toast.info("Check-in undone.");
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["roster", eventId] });
    },
  });

  if (rosterQ.isPending) {
    return (
      <div>
        {/* TODO(copy) */}
        <PageHeader title="Roster" />
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (rosterQ.error) {
    // Every failure used to read "you appear to be offline", so a permission
    // problem or a bad event id looked like a network blip and gave the
    // organizer nothing to act on — and no way to retry.
    const status = rosterQ.error?.status;
    const message =
      status === 403
        ? "You don't have access to this event's roster. Ask an admin to check your account."
        : status === 404
          ? "This event no longer exists. It may have been deleted."
          : "Couldn't load the roster. Check your connection and try again.";
    return (
      <div>
        <PageHeader title="Roster" />
        <p className="text-sm text-red-600 mt-4">{message}</p>
        {status !== 403 && status !== 404 ? (
          <Button
            variant="secondary"
            className="mt-3"
            onClick={() => rosterQ.refetch()}
          >
            Try again
          </Button>
        ) : null}
      </div>
    );
  }

  const roster = rosterQ.data;

  const total = roster.total || 0;
  const checkedIn = roster.checked_in_count || 0;
  const pct = total > 0 ? Math.round((checkedIn / total) * 100) : 0;
  const statusCounts = (roster.rows || []).reduce((acc, r) => {
    acc[r.status] = (acc[r.status] || 0) + 1;
    return acc;
  }, {});

  // Issue #31 — group rows by slot, orientation sections first, then by time.
  // Legacy rows without slot metadata fall into a single unlabeled group.
  const slotGroups = (() => {
    const map = new Map();
    for (const raw of roster.rows || []) {
      const r = { ...raw, status: openSlotStatus(raw) };
      const key = r.slot_id || "unknown";
      if (!map.has(key)) {
        map.set(key, {
          key,
          slotType: r.slot_type || "period",
          // 2026-08-05 shifts: a session's own name plus the shift it belongs
          // to. Times alone can't tell "Tue morning · Period 2" from another
          // shift running the same hour.
          shiftName: r.shift_name || null,
          sessionName: r.session_name || null,
          start: r.slot_time,
          end: r.slot_end,
          location: r.slot_location,
          // 2026-10-13: closed is a fact about the slot, set and cleared only
          // by a person pressing End / Reopen. It used to be inferred from
          // every row being attended/no_show, which is how an all-no-show
          // future session read as "Ended".
          closed: false,
          rows: [],
          expected: 0,
          checkedIn: 0,
          attended: 0,
          noShow: 0,
        });
      }
      const g = map.get(key);
      g.rows.push(r);
      if (r.slot_closed_at) g.closed = true;
      if (!["cancelled", "waitlisted"].includes(r.status)) g.expected += 1;
      if (r.status === "checked_in") g.checkedIn += 1;
      if (r.status === "attended") g.attended += 1;
      if (r.status === "no_show") g.noShow += 1;
    }
    return Array.from(map.values()).sort(
      (a, b) => new Date(a.start) - new Date(b.start),
    );
  })();

  // The event is done when every slot anyone is booked into is closed. A
  // slot with nobody seated has nothing to close and doesn't hold it open,
  // and neither do legacy rows with no slot — they can never be closed.
  const seatedGroups = slotGroups.filter(
    (g) => g.key !== "unknown" && g.expected > 0,
  );
  const eventResolved =
    seatedGroups.length > 0 && seatedGroups.every((g) => g.closed);

  return (
    <div className="pb-8 pt-4">
      <Link
        to={backTarget}
        className="inline-flex items-center gap-1 text-sm text-blue-600 hover:underline mb-3"
      >
        <span aria-hidden="true">←</span> Back to event
      </Link>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6 border-b border-gray-200 pb-4">
        <div>
          <h1 className="text-3xl font-semibold tracking-tight">
            {roster.event_name || "Roster"}
          </h1>
          <p className="mt-1 text-base text-[var(--color-fg-muted)]">
            Live check-in. Tap a volunteer to check them in, tap again to
            undo. Ending a slot records who attended and who didn't show —
            you can reopen it to fix a mistake.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => setQrOpen(true)}
          >
            Check-in QR
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setBroadcastOpen(true)}
          >
            Message volunteers
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setQuickFieldOpen(true)}
          >
            Add a question
          </Button>
          {/* Nothing left to close once every booked slot is closed. */}
          <Button
            onClick={() => setResolveOpenedAt(Date.now())}
            disabled={eventResolved}
            className="disabled:bg-slate-200 disabled:text-slate-500"
            title={eventResolved ? "Every slot has already been closed." : undefined}
          >
            {eventResolved ? "Event ended" : "End event"}
          </Button>
        </div>
      </div>

      {/* PR #51 — once every slot is closed the event is done; say so with
          a little ceremony instead of just greying the buttons out. */}
      {eventResolved ? (
        <div
          data-testid="event-complete-banner"
          className="animate-fade-up mb-6 flex items-center gap-4 rounded-2xl border border-emerald-200 bg-gradient-to-r from-emerald-50 via-white to-[var(--color-brand-soft)] p-4 shadow-sm"
        >
          <span className="animate-badge-pop flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-emerald-500 text-white shadow-md">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-6 w-6"
              aria-hidden="true"
            >
              <path
                d="M4.5 12.5l5 5 10-11"
                pathLength="1"
                className="animate-draw-check"
              />
            </svg>
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-base font-semibold text-emerald-900">
              Event complete 🎉
            </p>
            <p className="text-sm text-emerald-800/80">
              Every session is closed —{" "}
              {slotGroups.reduce((n, g) => n + g.attended, 0)} attended,{" "}
              {slotGroups.reduce((n, g) => n + g.noShow, 0)}{" "}
              {slotGroups.reduce((n, g) => n + g.noShow, 0) === 1
                ? "no-show"
                : "no-shows"}{" "}
              on the books.
              {slotGroups.some((g) => g.slotType === "orientation")
                ? " Orientation credit was granted with each closed orientation."
                : ""}
              {" "}Reopen a slot to fix a mistake.
            </p>
          </div>
          {/* Ended too early? Reopening puts every slot back on the live
              roster (real check-ins keep their timestamps). */}
          <Button
            type="button"
            variant="secondary"
            className="shrink-0"
            disabled={reopenMut.isPending}
            onClick={() => reopenMut.mutate()}
          >
            {reopenMut.isPending ? "Reopening…" : "Reopen event"}
          </Button>
        </div>
      ) : null}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <RosterStat label="Checked in" value={checkedIn} tone="green" />
        <RosterStat label="Total signups" value={total} />
        <RosterStat
          label="Waitlisted"
          value={statusCounts.waitlisted || 0}
          tone="amber"
        />
        <RosterStat
          label="Venue code"
          value={roster.venue_code || "—"}
          tone="blue"
        />
      </div>

      <div className="mb-6 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm font-medium text-gray-700">
            Check-in progress
          </p>
          <p className="text-sm text-gray-600 tabular-nums">
            {checkedIn} / {total} ({pct}%)
          </p>
        </div>
        <div
          className="h-3 w-full rounded-full bg-gray-100 overflow-hidden"
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          <div
            className="h-full bg-green-500 transition-all duration-300"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      {/* Issue #31 — check-in is per-slot: group volunteers under their slot
          (orientation vs module period) so the organizer works one section at
          a time instead of hunting through a flat list of names. */}
      {slotGroups.map((group) => {
        const isOrientation = group.slotType === "orientation";
        // 2026-10-14: a slot can't be closed before it starts — no-shows only
        // exist for a session that has begun. Judged on the roster's own
        // clock (the time of the last poll, every 5s), since a render can't
        // read the clock itself.
        const started =
          !group.start ||
          new Date(group.start).getTime() <= rosterQ.dataUpdatedAt;
        const endVerb = isOrientation ? "End orientation" : "End slot";
        const reopenVerb = isOrientation ? "Reopen orientation" : "Reopen slot";
        // Only the slot being reopened shows it; the others stay usable.
        const reopening =
          reopenSlotMut.isPending && reopenSlotMut.variables === group.key;
        return (
          <section key={group.key} className="space-y-3">
            <div className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--color-border)] pb-2">
              <h2 className="text-base font-semibold">
                <span
                  className={`mr-2 inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${
                    group.slotType === "orientation"
                      ? "bg-purple-100 text-purple-700"
                      : "bg-blue-100 text-blue-700"
                  }`}
                >
                  {group.slotType === "orientation" ? "Orientation" : "Module"}
                </span>
                {group.shiftName ? (
                  <span className="mr-2">
                    {group.shiftName}
                    {group.sessionName ? ` · ${group.sessionName}` : ""}
                  </span>
                ) : null}
                {fmtSlotRange(group.start, group.end)}
                {group.location ? (
                  <span className="ml-2 font-normal text-[var(--color-fg-muted)]">
                    · {group.location}
                  </span>
                ) : null}
                {/* A closed slot is read-only until someone reopens it, so say
                    so plainly rather than leaving a live-looking header above
                    a grid of frozen cards. */}
                {group.closed && (
                  <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
                    <span aria-hidden="true">✓</span> Closed
                  </span>
                )}
              </h2>
              <div className="flex items-center gap-3">
                <span className="text-sm text-[var(--color-fg-muted)] tabular-nums">
                  {group.closed
                    ? `${group.attended} attended · ${group.noShow} no show`
                    : `${group.checkedIn}/${group.expected} checked in`}
                </span>
                {group.key !== "unknown" && (
                  group.closed ? (
                    // Closing is never final: reopening puts attended back to
                    // checked in and no show back to not checked in.
                    <Button
                      type="button"
                      variant="secondary"
                      aria-label={`${reopenVerb} ${groupLabel(group)}`}
                      disabled={reopening}
                      onClick={() => reopenSlotMut.mutate(group.key)}
                    >
                      {reopening ? "Reopening…" : reopenVerb}
                    </Button>
                  ) : (
                    <Button
                      type="button"
                      variant="secondary"
                      aria-label={`${endVerb} ${groupLabel(group)}${started ? "" : ` — ${NOT_STARTED_HINT}`}`}
                      title={started ? undefined : NOT_STARTED_HINT}
                      disabled={!started}
                      // Grey the fill too, so it reads as "not yet" rather
                      // than a white pill that merely faded.
                      className="disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-500"
                      onClick={() => setResolveSlotGroup(group)}
                    >
                      {endVerb}
                    </Button>
                  )
                )}
              </div>
            </div>
            {/* Dim the whole grid while the slot is closed: nothing here is
                actionable until it's reopened, and a full-strength card still
                reads as a tap target. */}
            <ul
              className={`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 ${
                group.closed ? "opacity-[0.55]" : ""
              }`}
            >
              {group.rows.map((row) => {
                // Only an open slot takes taps. Issue #31 — a checked-in card
                // stays tappable so a mis-tap can be undone in place.
                const active = !group.closed && NOT_CHECKED_IN.includes(row.status);
                const canUndo = !group.closed && row.status === "checked_in";
                const done = row.status === "checked_in" || row.status === "attended";
                const busy = checkInMut.isPending || undoMut.isPending;
                const [chipLabel, chipClass] = chipFor(row.status);
                return (
                  <li
                    key={`${row.shift_signup_id || row.signup_id}|${row.slot_id || ""}`}
                  >
                    <button
                      type="button"
                      className={`w-full min-h-[84px] flex items-center justify-between px-5 py-4 rounded-xl border-2 text-left transition-all shadow-sm ${
                        // A closed slot goes uniformly grey regardless of
                        // outcome — the attended green would otherwise still
                        // read as a live, tappable card. Attended vs no-show is
                        // carried by the status chip, which stays coloured.
                        group.closed
                          ? "bg-slate-100 border-slate-200 cursor-not-allowed"
                          : done
                            ? `bg-green-50 border-green-300 ${canUndo ? "hover:bg-green-100 cursor-pointer" : "cursor-not-allowed"}`
                            : active
                              ? "bg-white border-gray-200 hover:border-blue-400 hover:shadow-md cursor-pointer"
                              : "bg-gray-50 border-gray-200 opacity-70 cursor-not-allowed"
                      }`}
                      disabled={(!active && !canUndo) || busy}
                      // Disabled unless one of the two applies.
                      onClick={() =>
                        active ? checkInMut.mutate(row) : undoMut.mutate(row)
                      }
                    >
                      <div className="min-w-0 flex-1">
                        {/* Flag sits outside the truncating span so a long name
                            can't clip it away. */}
                        <span className="flex items-center text-base font-semibold text-gray-900">
                          <span className="truncate">{row.student_name}</span>
                          <NoShowFlag count={row.no_show_count} />
                        </span>
                        <span className="block text-sm text-[var(--color-fg-muted)] mt-0.5">
                          {fmtVenueTime(row.slot_time)}
                          {canUndo ? (
                            <span className="ml-2 text-xs text-green-700">
                              · tap again to undo
                            </span>
                          ) : null}
                        </span>
                      </div>
                      <span
                        className={`ml-3 text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${chipClass}`}
                      >
                        {chipLabel}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {/* Event mode: the modal itself narrows this to open slots that have
          started, and closes them one slot at a time. */}
      <ResolveEventModal
        signups={roster.rows}
        openedAt={resolveOpenedAt}
        isOpen={resolveOpenedAt !== null}
        onClose={() => setResolveOpenedAt(null)}
        onResolved={() => {
          qc.invalidateQueries({ queryKey: ["roster", eventId] });
        }}
      />

      <ResolveEventModal
        signups={resolveSlotGroup ? resolveSlotGroup.rows : []}
        slot={
          resolveSlotGroup
            ? {
                id: resolveSlotGroup.key,
                slot_type: resolveSlotGroup.slotType,
              }
            : null
        }
        isOpen={resolveSlotGroup !== null}
        onClose={() => setResolveSlotGroup(null)}
        onResolved={() => {
          qc.invalidateQueries({ queryKey: ["roster", eventId] });
        }}
      />

      <QuickAddFieldModal
        open={quickFieldOpen}
        onClose={() => setQuickFieldOpen(false)}
        saving={quickFieldMut.isPending}
        // Clear the form only once the question is saved, so a failure
        // leaves what the organizer typed in place to retry.
        onSubmit={(field, reset) =>
          quickFieldMut.mutate(field, { onSuccess: reset })
        }
      />

      {/* Phase 26 — broadcast messages from the roster surface */}
      <BroadcastModal
        open={broadcastOpen}
        onClose={() => setBroadcastOpen(false)}
        eventId={eventId}
        scope="organizer"
      />

      {/* Event check-in QR. The modal reads the venue code off the same
          roster query this page already runs, so opening it costs an
          organizer nothing extra and needs no permission they lack. */}
      <CheckInQRModal
        open={qrOpen}
        onClose={() => setQrOpen(false)}
        eventId={eventId}
        eventTitle={roster.event_name || ""}
      />
    </div>
  );
}
