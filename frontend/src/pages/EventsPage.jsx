import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

export default function EventsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["events"],
    queryFn: api.events.list,
  });

  if (isLoading) return <div>Loading events…</div>;
  if (error) return <div style={{ color: "crimson" }}>Failed: {error.message}</div>;

  const events = data || [];

  return (
    <div>
      <h2>Events</h2>
      {events.length === 0 ? (
        <div>No events yet.</div>
      ) : (
        <ul style={{ display: "grid", gap: 10, paddingLeft: 18 }}>
          {events.map((e) => (
            <li key={e.id}>
              <Link to={`/events/${e.id}`} style={{ fontWeight: 600 }}>
                {e.title}
              </Link>
              <div style={{ opacity: 0.8, fontSize: 13 }}>
                {e.location || "TBD"} • {new Date(e.start_date).toLocaleString()} → {new Date(e.end_date).toLocaleString()}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
