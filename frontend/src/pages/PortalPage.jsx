import React from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  EmptyState,
  ErrorState,
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
      <div aria-busy="true" aria-live="polite" className="space-y-3 px-4 md:px-8 py-4">
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }
  if (q.error) {
    return (
      <div className="px-4 md:px-8 py-4">
        <ErrorState
          title="We couldn't load this page"
          body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
          action={
            <Button variant="secondary" onClick={() => q.refetch()}>
              Try again
            </Button>
          }
        />
      </div>
    );
  }

  const portal = q.data;
  const portalEvents = portal.events || [];

  return (
    <div className="space-y-4 px-4 md:px-8 py-4">
      <PageHeader
        title={portal.name || "Partner portal"}
        subtitle={portal.description || ""}
      />

      <Card>
        <p className="text-sm">
          Welcome to {portal.name}. Browse upcoming events and sign up for a slot.
        </p>
        <div className="mt-3">
          <Button as={Link} to="/events" size="lg">
            See this week's events
          </Button>
        </div>
      </Card>

      {portalEvents.length === 0 ? (
        <EmptyState
          title="No events from this partner yet"
          body="Sci Trek will post new events here as they're scheduled."
          action={
            <Button as={Link} to="/events" variant="secondary">
              View all events
            </Button>
          }
        />
      ) : (
        <div>
          <h2 className="text-sm font-medium text-[var(--color-fg-muted)] mt-4 mb-2 uppercase tracking-wide">
            Events
          </h2>
          <div className="space-y-2">
            {portalEvents.map((e) => (
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
