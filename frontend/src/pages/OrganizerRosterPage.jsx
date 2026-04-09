import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchRoster, checkInSignup } from "../api/roster";
import { PageHeader, Button, Skeleton } from "../components/ui";
import { toast } from "../state/toast";
import ResolveEventModal from "../components/ResolveEventModal";

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
    </div>
  );
}
