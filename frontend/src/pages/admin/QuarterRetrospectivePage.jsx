// src/pages/admin/QuarterRetrospectivePage.jsx
//
// Issue #38 — quarter retrospective: how a past quarter's events ran.
// Read-only drill-in from the Quarters table ("View events"): headline
// totals plus a per-event signup/capacity/attended/no-show table.

import React from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import api from "../../lib/api";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Skeleton,
} from "../../components/ui";
import StatCard from "../../components/admin/StatCard";
import { useAdminPageTitle } from "./AdminLayout";

function formatQuarterDate(iso) {
  if (!iso) return "";
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

function formatEventDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export default function QuarterRetrospectivePage() {
  useAdminPageTitle("Quarters");
  const { quarterId } = useParams();

  const retroQ = useQuery({
    queryKey: ["adminQuarterRetro", quarterId],
    queryFn: () => api.admin.quarters.retrospective(quarterId),
  });

  if (retroQ.isPending) {
    return <Skeleton className="h-64 rounded-xl" />;
  }
  if (retroQ.error) {
    return (
      <ErrorState
        title="Couldn't load this quarter"
        body={retroQ.error.message}
        action={<Button onClick={() => retroQ.refetch()}>Try again</Button>}
      />
    );
  }

  const { quarter, totals, events } = retroQ.data;
  const rate = `${Math.round(totals.attendance_rate * 100)}%`;

  return (
    <div className="space-y-6">
      <Link
        to="/admin/quarters"
        className="text-sm font-medium text-[var(--color-brand)] underline"
      >
        ← All quarters
      </Link>

      <PageHeader
        title={
          <>
            {quarter.display_name}
            {quarter.archived_at && (
              <span className="ml-2 inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 align-middle text-xs font-medium text-slate-600">
                Archived
              </span>
            )}
          </>
        }
        subtitle={`${formatQuarterDate(quarter.start_date)} – ${formatQuarterDate(quarter.end_date)} · ${quarter.weeks_in_quarter} weeks`}
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Events ran" value={totals.events} />
        <StatCard
          label="Signups"
          value={totals.signups}
          subline={`Capacity: ${totals.capacity}`}
        />
        <StatCard
          label="Attended"
          value={totals.attended}
          subline={`Attendance rate: ${rate}`}
        />
        <StatCard label="No-shows" value={totals.no_shows} />
      </div>

      {events.length === 0 ? (
        <EmptyState
          title="No events ran in this quarter"
          body="Events linked to this quarter will appear here."
        />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[var(--color-fg-muted)]">
                <th className="py-2 pr-4">Week</th>
                <th className="py-2 pr-4">Event</th>
                <th className="py-2 pr-4">Date</th>
                <th className="py-2 pr-4">Signups</th>
                <th className="py-2 pr-4">Attended</th>
                <th className="py-2">No-shows</th>
              </tr>
            </thead>
            <tbody>
              {events.map((row) => (
                <tr
                  key={row.event_id}
                  className="border-t border-[var(--color-border)]"
                >
                  <td className="py-3 pr-4">{row.week_number ?? "—"}</td>
                  <td className="py-3 pr-4 font-medium">
                    <Link
                      to={`/admin/events/${row.event_id}`}
                      className="text-[var(--color-brand)] underline"
                    >
                      {row.title}
                    </Link>
                  </td>
                  <td className="py-3 pr-4">{formatEventDate(row.start_date)}</td>
                  <td className="py-3 pr-4">
                    <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                      {row.signups}/{row.capacity}
                    </span>
                  </td>
                  <td className="py-3 pr-4">{row.attended}</td>
                  <td className="py-3">{row.no_shows}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
