// Phase 24 — admin Reminders page.
//
// Lists the computed upcoming reminders for the next 7 days (signup_id,
// event_title, kind, scheduled_for). "Send now" button per row triggers the
// short-circuit send endpoint. Opt-out and already-sent rows are shown so
// admins can see the full picture.

import React, { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import api from "../../lib/api";
import { useAdminPageTitle } from "./AdminLayout";
import { Button, Card, EmptyState, Modal, Skeleton } from "../../components/ui";
import { toast } from "../../state/toast";

function fmtWhen(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "America/Los_Angeles",
    });
  } catch {
    return iso;
  }
}

function KindBadge({ kind }) {
  const label =
    kind === "kickoff"
      ? "Kickoff"
      : kind === "pre_24h"
        ? "24h"
        : kind === "pre_2h"
          ? "2h"
          : kind;
  const cls =
    kind === "kickoff"
      ? "bg-sky-100 text-sky-800"
      : kind === "pre_24h"
        ? "bg-indigo-100 text-indigo-800"
        : "bg-amber-100 text-amber-800";
  return (
    <span className={`inline-block text-xs px-2 py-0.5 rounded-full ${cls}`}>
      {label}
    </span>
  );
}

function StatusChip({ row }) {
  if (row.already_sent) {
    return (
      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-gray-200 text-gray-700">
        already sent
      </span>
    );
  }
  if (row.opted_out) {
    return (
      <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-rose-100 text-rose-800">
        opted out
      </span>
    );
  }
  return (
    <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-green-100 text-green-800">
      scheduled
    </span>
  );
}

export default function AdminRemindersPage() {
  useAdminPageTitle("Reminders");
  const qc = useQueryClient();

  const [confirmRow, setConfirmRow] = useState(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "reminders", 7],
    queryFn: () => api.admin.reminders.listUpcoming(7),
  });

  const sendNow = useMutation({
    mutationFn: ({ signupId, kind }) =>
      api.admin.reminders.sendNow(signupId, kind),
    onSuccess: (res) => {
      if (res?.sent) {
        toast.success("Reminder sent.");
      } else if (res?.reason === "opted_out") {
        toast.error("Volunteer has opted out; reminder not sent.");
      } else if (res?.reason === "already_sent") {
        toast.info?.("Already sent — skipped.");
      } else {
        toast.error(`Not sent: ${res?.reason || "unknown"}`);
      }
      qc.invalidateQueries({ queryKey: ["admin", "reminders"] });
    },
    onError: (e) => toast.error(e?.message || "Failed to send reminder."),
  });

  if (isLoading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 rounded-lg" />
        <Skeleton className="h-16 rounded-lg" />
        <Skeleton className="h-16 rounded-lg" />
      </div>
    );
  }

  if (isError) {
    return (
      <Card className="p-4">
        <p className="text-sm text-gray-700">
          Couldn't load the reminders preview. Please try again.
        </p>
      </Card>
    );
  }

  const rows = data || [];

  if (rows.length === 0) {
    return (
      <EmptyState
        title="No upcoming reminders"
        body="Once there are confirmed signups in the next 7 days, their kickoff / 24-hour / 2-hour reminders will appear here."
      />
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm text-gray-600">
        Preview of automatic email reminders for the next 7 days. Opted-out and
        already-sent rows are shown for transparency.
      </p>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm" data-testid="reminders-table">
          <thead className="text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="py-2 pr-4">When</th>
              <th className="py-2 pr-4">Kind</th>
              <th className="py-2 pr-4">Volunteer</th>
              <th className="py-2 pr-4">Event</th>
              <th className="py-2 pr-4">Status</th>
              <th className="py-2 pr-4 text-right">Action</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr
                key={`${r.signup_id}-${r.kind}`}
                className="border-t border-gray-100"
              >
                <td className="py-2 pr-4 whitespace-nowrap">
                  {fmtWhen(r.scheduled_for)}
                </td>
                <td className="py-2 pr-4">
                  <KindBadge kind={r.kind} />
                </td>
                <td className="py-2 pr-4">
                  <div className="font-medium text-gray-900">
                    {r.volunteer_name || "—"}
                  </div>
                  <div className="text-xs text-gray-500">
                    {r.volunteer_email}
                  </div>
                </td>
                <td className="py-2 pr-4">{r.event_title}</td>
                <td className="py-2 pr-4">
                  <StatusChip row={r} />
                </td>
                <td className="py-2 pr-4 text-right">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setConfirmRow(r)}
                    disabled={r.already_sent || sendNow.isPending}
                  >
                    Send now
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <Modal
        open={!!confirmRow}
        onClose={() => !sendNow.isPending && setConfirmRow(null)}
        title="Send this reminder now?"
      >
        <p className="text-sm text-gray-600 mb-4">
          This fires the <strong>{confirmRow?.kind}</strong> reminder for{" "}
          <strong>{confirmRow?.volunteer_email}</strong> immediately. Opt-outs
          and already-sent rules still apply.
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            variant="secondary"
            onClick={() => setConfirmRow(null)}
            disabled={sendNow.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={() => {
              const row = confirmRow;
              setConfirmRow(null);
              sendNow.mutate({ signupId: row.signup_id, kind: row.kind });
            }}
            disabled={sendNow.isPending}
          >
            {sendNow.isPending ? "Sending…" : "Send now"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
