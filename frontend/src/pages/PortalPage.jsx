import React from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  EmptyState,
  Skeleton,
} from "../components/ui";

export default function PortalPage() {
  const { slug } = useParams();

  const q = useQuery({
    queryKey: ["portal", slug],
    queryFn: () => api.portals.getBySlug(slug),
  });

  if (q.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (q.error) {
    return (
      <EmptyState
        /* TODO(copy) */
        title="Couldn't load portal"
        /* TODO(copy) */
        body={q.error.message}
      />
    );
  }

  const portal = q.data;

  return (
    <div className="space-y-4">
      <PageHeader
        /* TODO(copy) */
        title={portal.name}
        subtitle={portal.description || ""}
      />

      <Card>
        <p className="text-sm">
          {/* TODO(copy) */}
          Welcome to {portal.name}. Browse upcoming events and grab a slot.
        </p>
        <div className="mt-3">
          <Button as={Link} to="/events" size="lg">
            {/* TODO(copy) */}
            Browse events
          </Button>
        </div>
      </Card>

      {(portal.events || []).length > 0 && (
        <div>
          {/* TODO(copy) */}
          <h2 className="text-sm font-medium text-[var(--color-fg-muted)] mt-4 mb-2 uppercase tracking-wide">
            Events
          </h2>
          <div className="space-y-2">
            {portal.events.map((e) => (
              <Card key={e.id}>
                <Link to={`/events/${e.id}`} className="font-semibold">
                  {e.title}
                </Link>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
