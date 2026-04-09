import React, { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { formatApiDateTimeLocal, toEpochMs } from "../lib/datetime";
import {
  PageHeader,
  Card,
  Chip,
  Skeleton,
  EmptyState,
  Button,
} from "../components/ui";
import { useAuth } from "../state/useAuth";
import { useDocumentMeta } from "../lib/useDocumentMeta";

const FILTERS = [
  { value: "upcoming", label: "Upcoming" }, // TODO(copy)
  { value: "this-week", label: "This week" }, // TODO(copy)
  { value: "mine", label: "My signups" }, // TODO(copy)
];

export default function EventsPage() {
  const { isAuthed } = useAuth();
  const [filter, setFilter] = useState("upcoming");

  useDocumentMeta({
    title: "Events — Volunteer Scheduler", // TODO(copy)
    description:
      "Browse upcoming volunteer shifts and sign up in three taps.", // TODO(copy)
    ogType: "website",
  });

  const eventsQ = useQuery({
    queryKey: ["events"],
    queryFn: api.events.list,
  });

  const mySignupsQ = useQuery({
    queryKey: ["mySignups"],
    queryFn: api.signups.my,
    enabled: isAuthed,
  });

  const events = eventsQ.data || [];
  // Capture "now" once at mount so render stays pure; a stale filter window by a
  // few seconds is fine for this view.
  const [now] = useState(() => Date.now());

  const filtered = useMemo(() => {
    const weekMs = 7 * 24 * 60 * 60 * 1000;
    if (filter === "upcoming") {
      return events.filter((e) => toEpochMs(e.start_date) >= now);
    }
    if (filter === "this-week") {
      return events.filter((e) => {
        const t = toEpochMs(e.start_date);
        return t >= now && t <= now + weekMs;
      });
    }
    if (filter === "mine") {
      const ids = new Set(
        (mySignupsQ.data || [])
          .map((s) => s.event_id)
          .filter(Boolean),
      );
      return events.filter((e) => ids.has(e.id));
    }
    return events;
  }, [events, filter, mySignupsQ.data, now]);

  return (
    <div>
      {/* TODO(copy): page title */}
      <PageHeader title="Events" />

      <div
        className="sticky top-[calc(var(--header-h))] z-10 -mx-4 px-4 py-2 bg-[var(--color-bg)]/90 backdrop-blur border-b border-[var(--color-border)]"
      >
        <div className="flex gap-2 overflow-x-auto">
          {FILTERS.map((f) => (
            <Chip
              key={f.value}
              active={filter === f.value}
              onClick={() => setFilter(f.value)}
            >
              {/* TODO(copy): filter label */}
              {f.label}
            </Chip>
          ))}
        </div>
      </div>

      <div className="space-y-3 mt-4">
        {eventsQ.isPending ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))
        ) : eventsQ.error ? (
          <EmptyState
            /* TODO(copy) */
            title="Couldn't load events"
            /* TODO(copy) */
            body={eventsQ.error.message}
            action={
              <Button onClick={() => eventsQ.refetch()}>
                {/* TODO(copy) */}
                Retry
              </Button>
            }
          />
        ) : filtered.length === 0 ? (
          <EmptyState
            /* TODO(copy) */
            title="No events yet"
            /* TODO(copy) */
            body="Check back soon."
          />
        ) : (
          filtered.map((e) => (
            <Card key={e.id}>
              <h2 className="text-lg font-semibold">
                <Link to={`/events/${e.id}`}>{e.title}</Link>
              </h2>
              <p className="text-sm text-[var(--color-fg-muted)] mt-1">
                {e.location || "TBD"} •{" "}
                {formatApiDateTimeLocal(e.start_date)}
              </p>
              {e.description && (
                <p className="text-sm mt-2 line-clamp-2">{e.description}</p>
              )}
              <div className="mt-3">
                <Button as={Link} to={`/events/${e.id}`}>
                  {/* TODO(copy) */}
                  View slots
                </Button>
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
