// src/pages/NotificationsPage.jsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  EmptyState,
  Skeleton,
} from "../components/ui";

export default function NotificationsPage() {
  const q = useQuery({
    queryKey: ["myNotifications"],
    queryFn: api.notifications.my,
  });

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Notifications" />

      {q.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : q.error ? (
        <EmptyState
          /* TODO(copy) */
          title="Couldn't load notifications"
          /* TODO(copy) */
          body={q.error.message}
          action={
            <Button onClick={() => q.refetch()}>
              {/* TODO(copy) */}
              Retry
            </Button>
          }
        />
      ) : (q.data || []).length === 0 ? (
        <EmptyState
          /* TODO(copy) */
          title="No notifications yet"
        />
      ) : (
        <div className="space-y-3">
          {(q.data || []).map((n) => (
            <Card key={n.id}>
              <h3 className="font-semibold">
                {n.subject || "(no subject)"}
              </h3>
              <p className="text-xs text-[var(--color-fg-muted)]">
                {/* TODO(copy) */}
                {n.type} &middot; {new Date(n.created_at).toLocaleString()}
              </p>
              {n.body && (
                <p className="text-sm mt-1 whitespace-pre-wrap">{n.body}</p>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
