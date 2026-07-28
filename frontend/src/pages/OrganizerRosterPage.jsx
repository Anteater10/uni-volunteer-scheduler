import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../state/useAuth";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRoster, checkInSignup, undoCheckInSignup } from "../api/roster";
import api from "../lib/api";
import { PageHeader, Button, Skeleton, Modal, Input, Label } from "../components/ui";
import { toast } from "../state/toast";
import ResolveEventModal from "../components/ResolveEventModal";
import BroadcastModal from "../components/BroadcastModal";

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

// Issue #31 — slot section header time range, e.g. "9:00 AM – 10:00 AM".
function fmtSlotRange(startIso, endIso) {
  const fmt = (iso) =>
    iso
      ? new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })
      : "";
  const start = fmt(startIso);
  const end = fmt(endIso);
  return end ? `${start} – ${end}` : start;
}

// TODO(brand): final status chip palette
const STATUS_CHIP = {
  confirmed: "bg-gray-200 text-gray-800",
  checked_in: "bg-green-200 text-green-800",
  attended: "bg-emerald-300 text-emerald-900",
  no_show: "bg-red-200 text-red-800",
  pending: "bg-yellow-100 text-yellow-800",
  waitlisted: "bg-purple-100 text-purple-800",
  cancelled: "bg-gray-100 text-gray-500 line-through",
};

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
  const { role } = useAuth();
  const backTarget =
    role === "admin" ? `/admin/events/${eventId}` : "/admin/events";
  const [resolveOpen, setResolveOpen] = useState(false);
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

  const checkInMut = useMutation({
    mutationFn: (signupId) => checkInSignup(signupId),
    onMutate: async (signupId) => {
      // Optimistic update
      await qc.cancelQueries({ queryKey: ["roster", eventId] });
      const prev = qc.getQueryData(["roster", eventId]);
      qc.setQueryData(["roster", eventId], (old) => {
        if (!old) return old;
        return {
          ...old,
          checked_in_count: old.checked_in_count + 1,
          rows: old.rows.map((r) =>
            r.signup_id === signupId ? { ...r, status: "checked_in" } : r,
          ),
        };
      });
      return { prev };
    },
    onError: (_err, _signupId, context) => {
      // Rollback
      if (context?.prev) {
        qc.setQueryData(["roster", eventId], context.prev);
      }
      toast.error("Check-in failed. Please retry.");
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["roster", eventId] });
    },
  });

  // Issue #31 — mis-tap recovery: tapping a checked-in card reverts it.
  const undoMut = useMutation({
    mutationFn: (signupId) => undoCheckInSignup(signupId),
    onMutate: async (signupId) => {
      await qc.cancelQueries({ queryKey: ["roster", eventId] });
      const prev = qc.getQueryData(["roster", eventId]);
      qc.setQueryData(["roster", eventId], (old) => {
        if (!old) return old;
        return {
          ...old,
          checked_in_count: Math.max(0, old.checked_in_count - 1),
          rows: old.rows.map((r) =>
            r.signup_id === signupId ? { ...r, status: "confirmed" } : r,
          ),
        };
      });
      return { prev };
    },
    onError: (_err, _signupId, context) => {
      if (context?.prev) {
        qc.setQueryData(["roster", eventId], context.prev);
      }
      toast.error("Undo failed. Please retry.");
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
  const canCheckIn = (status) =>
    status === "confirmed" || status === "pending";

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
    for (const r of roster.rows || []) {
      const key = r.slot_id || "unknown";
      if (!map.has(key)) {
        map.set(key, {
          key,
          slotType: r.slot_type || "period",
          start: r.slot_time,
          end: r.slot_end,
          location: r.slot_location,
          rows: [],
          expected: 0,
          checkedIn: 0,
          attended: 0,
          noShow: 0,
        });
      }
      const g = map.get(key);
      g.rows.push(r);
      if (!["cancelled", "waitlisted"].includes(r.status)) g.expected += 1;
      if (["checked_in", "attended"].includes(r.status)) g.checkedIn += 1;
      if (r.status === "attended") g.attended += 1;
      if (r.status === "no_show") g.noShow += 1;
    }
    // Ending a slot resolves every expected signup to attended or no_show, so
    // that is what "this slot is over" looks like in the data — there is no
    // separate resolved flag on the slot itself.
    for (const g of map.values()) {
      g.resolved = g.expected > 0 && g.attended + g.noShow === g.expected;
    }
    return Array.from(map.values()).sort(
      (a, b) => new Date(a.start) - new Date(b.start),
    );
  })();

  const eventResolved =
    slotGroups.length > 0 &&
    slotGroups.every((g) => g.resolved || g.expected === 0);

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
            Live check-in. Tap a volunteer to mark them checked in.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
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
          {/* Nothing left to resolve once every slot is ended. */}
          <Button
            onClick={() => setResolveOpen(true)}
            disabled={eventResolved}
            className="disabled:bg-slate-200 disabled:text-slate-500"
            title={eventResolved ? "Every slot has already been ended." : undefined}
          >
            {eventResolved ? "Event ended" : "End event"}
          </Button>
        </div>
      </div>

      {/* PR #51 — once every slot is resolved the event is done; say so with
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
          <div>
            <p className="text-base font-semibold text-emerald-900">
              Event complete 🎉
            </p>
            <p className="text-sm text-emerald-800/80">
              Every session is resolved —{" "}
              {slotGroups.reduce((n, g) => n + g.attended, 0)} attended,{" "}
              {slotGroups.reduce((n, g) => n + g.noShow, 0)} no-shows on the
              books.
              {slotGroups.some((g) => g.slotType === "orientation")
                ? " Orientation credit was granted with each ended session."
                : ""}
            </p>
          </div>
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
      {slotGroups.map((group) => (
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
              {fmtSlotRange(group.start, group.end)}
              {group.location ? (
                <span className="ml-2 font-normal text-[var(--color-fg-muted)]">
                  · {group.location}
                </span>
              ) : null}
              {/* Ending a slot is irreversible from this screen, so say so
                  plainly rather than leaving a live-looking header above a
                  grid of frozen cards. */}
              {group.resolved && (
                <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-slate-200 px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide text-slate-600">
                  <span aria-hidden="true">✓</span> Ended
                </span>
              )}
            </h2>
            <div className="flex items-center gap-3">
              <span className="text-sm text-[var(--color-fg-muted)] tabular-nums">
                {group.resolved
                  ? `${group.attended} attended · ${group.noShow} no show`
                  : `${group.checkedIn}/${group.expected} checked in`}
              </span>
              {group.key !== "unknown" && (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={group.resolved}
                  // Button's base only fades on :disabled, which leaves a
                  // white pill. Grey the fill too so it reads as spent rather
                  // than momentarily unavailable. The disabled: variants
                  // out-specify the plain colours from variant="secondary".
                  className="disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-500"
                  title={
                    group.resolved
                      ? "This slot has already been ended."
                      : undefined
                  }
                  onClick={() => setResolveSlotGroup(group)}
                >
                  {group.resolved
                    ? group.slotType === "orientation"
                      ? "Orientation ended"
                      : "Slot ended"
                    : group.slotType === "orientation"
                      ? "End orientation"
                      : "End slot"}
                </Button>
              )}
            </div>
          </div>
          {/* Dim the whole grid once the slot is ended: nothing here is
              actionable any more, and a full-strength card still reads as a
              tap target. */}
          <ul
            className={`grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 ${
              group.resolved ? "opacity-[0.55]" : ""
            }`}
          >
            {group.rows.map((row) => {
              const active = canCheckIn(row.status);
              // Issue #31 — a checked-in card stays tappable so a mis-tap can
              // be undone in place; resolved states (attended) stay locked.
              const canUndo = row.status === "checked_in";
              const done = row.status === "checked_in" || row.status === "attended";
              const busy = checkInMut.isPending || undoMut.isPending;
              return (
                <li key={row.signup_id}>
                  <button
                    type="button"
                    className={`w-full min-h-[84px] flex items-center justify-between px-5 py-4 rounded-xl border-2 text-left transition-all shadow-sm ${
                      // An ended slot goes uniformly grey regardless of
                      // outcome — the attended green would otherwise still
                      // read as a live, tappable card. Attended vs no-show is
                      // carried by the status chip, which stays coloured.
                      group.resolved
                        ? "bg-slate-100 border-slate-200 cursor-not-allowed"
                        : done
                          ? `bg-green-50 border-green-300 ${canUndo ? "hover:bg-green-100 cursor-pointer" : "cursor-not-allowed"}`
                          : active
                            ? "bg-white border-gray-200 hover:border-blue-400 hover:shadow-md cursor-pointer"
                            : "bg-gray-50 border-gray-200 opacity-70 cursor-not-allowed"
                    }`}
                    disabled={(!active && !canUndo) || busy}
                    onClick={() => {
                      if (active) {
                        checkInMut.mutate(row.signup_id);
                      } else if (canUndo) {
                        undoMut.mutate(row.signup_id);
                      }
                    }}
                  >
                    <div className="min-w-0 flex-1">
                      <span className="block text-base font-semibold text-gray-900 truncate">
                        {row.student_name}
                      </span>
                      <span className="block text-sm text-[var(--color-fg-muted)] mt-0.5">
                        {new Date(row.slot_time).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                        {canUndo ? (
                          <span className="ml-2 text-xs text-green-700">
                            · tap again to undo
                          </span>
                        ) : null}
                      </span>
                    </div>
                    <span
                      className={`ml-3 text-xs font-medium px-2.5 py-1 rounded-full whitespace-nowrap ${STATUS_CHIP[row.status] || "bg-gray-100"}`}
                    >
                      {row.status.replace("_", " ")}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <ResolveEventModal
        eventId={eventId}
        signups={roster.rows}
        isOpen={resolveOpen}
        onClose={() => setResolveOpen(false)}
        onResolved={() => {
          qc.invalidateQueries({ queryKey: ["roster", eventId] });
        }}
      />

      <ResolveEventModal
        eventId={eventId}
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
        onSubmit={(field) => quickFieldMut.mutate(field)}
      />

      {/* Phase 26 — broadcast messages from the roster surface */}
      <BroadcastModal
        open={broadcastOpen}
        onClose={() => setBroadcastOpen(false)}
        eventId={eventId}
        scope="organizer"
      />
    </div>
  );
}
