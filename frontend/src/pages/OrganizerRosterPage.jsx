import React, { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useAuth } from "../state/useAuth";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRoster, checkInSignup } from "../api/roster";
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
    return (
      <div>
        <PageHeader title="Roster" />
        <p className="text-sm text-red-600 mt-4">
          {/* TODO(copy): offline message */}
          You appear to be offline — retry in 5s
        </p>
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
          <Button onClick={() => setResolveOpen(true)}>End event</Button>
        </div>
      </div>

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

      <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {roster.rows.map((row) => {
          const active = canCheckIn(row.status);
          const done = row.status === "checked_in" || row.status === "attended";
          return (
            <li key={row.signup_id}>
              <button
                type="button"
                className={`w-full min-h-[84px] flex items-center justify-between px-5 py-4 rounded-xl border-2 text-left transition-all shadow-sm ${
                  done
                    ? "bg-green-50 border-green-300 hover:bg-green-100"
                    : active
                      ? "bg-white border-gray-200 hover:border-blue-400 hover:shadow-md cursor-pointer"
                      : "bg-gray-50 border-gray-200 opacity-70 cursor-not-allowed"
                }`}
                disabled={!active || checkInMut.isPending}
                onClick={() => {
                  if (active) {
                    checkInMut.mutate(row.signup_id);
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

      <ResolveEventModal
        eventId={eventId}
        signups={roster.rows}
        isOpen={resolveOpen}
        onClose={() => setResolveOpen(false)}
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
