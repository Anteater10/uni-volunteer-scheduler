// src/pages/admin/OverviewSection.jsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import {
  Card,
  Button,
  Skeleton,
  EmptyState,
} from "../../components/ui";

function Stat({ label, value }) {
  return (
    <Card className="!p-3">
      {/* TODO(copy) */}
      <p className="text-xs text-[var(--color-fg-muted)]">{label}</p>
      <p className="text-2xl font-bold">{value ?? "--"}</p>
    </Card>
  );
}

function formatTs(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts || "");
  }
}

export default function OverviewSection() {
  const summaryQ = useQuery({
    queryKey: ["adminSummary"],
    queryFn: api.admin.summary,
  });

  const activityQ = useQuery({
    queryKey: ["adminRecentActivity"],
    queryFn: () => api.admin.auditLogs({ limit: 10 }),
  });

  return (
    <div className="space-y-4">
      {/* Stats grid */}
      {summaryQ.isPending ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : summaryQ.error ? (
        <EmptyState
          /* TODO(copy) */
          title="Couldn't load summary"
          body={summaryQ.error.message}
          action={
            <Button onClick={() => summaryQ.refetch()}>
              {/* TODO(copy) */}
              Retry
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="Users" value={summaryQ.data?.total_users} />
          <Stat label="Events" value={summaryQ.data?.total_events} />
          <Stat label="Slots" value={summaryQ.data?.total_slots} />
          <Stat label="Signups" value={summaryQ.data?.total_signups} />
          <Stat label="Signups (7d)" value={summaryQ.data?.signups_last_7d} />
        </div>
      )}

      {/* Recent Activity */}
      <Card>
        <h3 className="font-semibold mb-3">
          {/* TODO(copy) */}
          Recent Activity
        </h3>
        {activityQ.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-8" />
            ))}
          </div>
        ) : activityQ.error ? (
          <p className="text-sm text-[var(--color-fg-muted)]">
            {/* TODO(copy) */}
            Could not load recent activity.
          </p>
        ) : (activityQ.data?.length || activityQ.data?.items?.length) ? (
          <div className="divide-y divide-[var(--color-border)]">
            {(activityQ.data?.items || activityQ.data || []).slice(0, 10).map((entry) => (
              <div key={entry.id} className="py-2 flex flex-wrap items-baseline gap-2 text-sm">
                <span className="font-medium">{entry.action}</span>
                <span className="text-[var(--color-fg-muted)]">
                  {entry.entity_type}
                  {entry.entity_id ? ` #${entry.entity_id}` : ""}
                </span>
                <span className="text-xs text-[var(--color-fg-muted)] ml-auto">
                  {formatTs(entry.timestamp)}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--color-fg-muted)]">
            {/* TODO(copy) */}
            No recent activity.
          </p>
        )}
      </Card>
    </div>
  );
}
