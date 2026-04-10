// adminDashboardPage.jsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  Skeleton,
  EmptyState,
} from "../components/ui";

function Stat({ label, value }) {
  return (
    <Card className="!p-3">
      {/* TODO(copy) */}
      <p className="text-xs text-[var(--color-fg-muted)]">{label}</p>
      <p className="text-2xl font-bold">{value ?? "—"}</p>
    </Card>
  );
}

export default function AdminDashboardPage() {
  const q = useQuery({ queryKey: ["adminSummary"], queryFn: api.admin.summary });

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Admin" />

      {q.isPending ? (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : q.error ? (
        <EmptyState
          /* TODO(copy) */
          title="Couldn't load summary"
          /* TODO(copy) */
          body={q.error.message}
          action={
            <Button onClick={() => q.refetch()}>
              {/* TODO(copy) */}
              Retry
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Stat label="Users" value={q.data?.total_users} />
          <Stat label="Events" value={q.data?.total_events} />
          <Stat label="Slots" value={q.data?.total_slots} />
          <Stat label="Signups" value={q.data?.total_signups} />
          <Stat label="Signups (7d)" value={q.data?.signups_last_7d} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Card>
          <h3 className="font-semibold">
            {/* TODO(copy) */}
            Users
          </h3>
          <p className="text-sm text-[var(--color-fg-muted)] mt-1">
            {/* TODO(copy) */}
            Manage accounts and roles.
          </p>
          <div className="mt-3">
            <Button variant="secondary" as={Link} to="/admin/users">
              {/* TODO(copy) */}
              Manage users
            </Button>
          </div>
        </Card>
        <Card>
          <h3 className="font-semibold">
            {/* TODO(copy) */}
            Portals
          </h3>
          <p className="text-sm text-[var(--color-fg-muted)] mt-1">
            {/* TODO(copy) */}
            Branded landing pages.
          </p>
          <div className="mt-3">
            <Button variant="secondary" as={Link} to="/admin/portals">
              {/* TODO(copy) */}
              Manage portals
            </Button>
          </div>
        </Card>
        <Card>
          <h3 className="font-semibold">
            {/* TODO(copy) */}
            Audit logs
          </h3>
          <p className="text-sm text-[var(--color-fg-muted)] mt-1">
            {/* TODO(copy) */}
            Trail of admin actions.
          </p>
          <div className="mt-3">
            <Button variant="secondary" as={Link} to="/admin/audit-logs">
              {/* TODO(copy) */}
              View logs
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
