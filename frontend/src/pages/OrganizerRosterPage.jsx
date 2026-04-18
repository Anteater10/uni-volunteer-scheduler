import React, { useState } from "react";
import { useParams } from "react-router-dom";
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

export default function OrganizerRosterPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
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

  return (
    <div className="pb-20">
      {/* TODO(copy) */}
      <PageHeader title={roster.event_name || "Roster"} />

      <div className="flex items-center justify-between px-1 mb-4">
        <p className="text-sm font-medium">
          {roster.checked_in_count} of {roster.total} checked in
        </p>
        {roster.venue_code && (
          <p className="text-xs text-[var(--color-fg-muted)]">
            Code: <span className="font-mono font-bold">{roster.venue_code}</span>
          </p>
        )}
      </div>

      <div className="flex items-center justify-end gap-2 px-1 mb-2">
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
      </div>

      <ul className="space-y-1">
        {roster.rows.map((row) => (
          <li key={row.signup_id}>
            <button
              type="button"
              className="w-full min-h-[56px] flex items-center justify-between px-4 py-3 rounded-xl hover:bg-[var(--color-bg-muted)] transition-colors text-left"
              disabled={!canCheckIn(row.status) || checkInMut.isPending}
              onClick={() => {
                if (canCheckIn(row.status)) {
                  checkInMut.mutate(row.signup_id);
                }
              }}
            >
              <div>
                <span className="text-sm font-medium">{row.student_name}</span>
                <span className="block text-xs text-[var(--color-fg-muted)]">
                  {new Date(row.slot_time).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <span
                className={`text-xs px-2 py-0.5 rounded-full ${STATUS_CHIP[row.status] || "bg-gray-100"}`}
              >
                {row.status.replace("_", " ")}
              </span>
            </button>
          </li>
        ))}
      </ul>

      {/* Sticky footer: End event */}
      <div className="sticky bottom-0 w-full pt-3 pb-3 bg-[var(--color-bg)]">
        <Button
          className="w-full h-14"
          onClick={() => setResolveOpen(true)}
        >
          {/* TODO(copy) */}
          End event
        </Button>
      </div>

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
