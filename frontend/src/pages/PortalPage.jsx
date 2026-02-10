import React from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function PortalPage() {
  const { slug } = useParams();

  const q = useQuery({
    queryKey: ["portal", slug],
    queryFn: () => api.portals.getBySlug(slug),
  });

  if (q.isLoading) return <div>Loading portal…</div>;
  if (q.error) return <div style={{ color: "crimson" }}>Failed: {q.error.message}</div>;

  const portal = q.data;

  return (
    <div>
      <h2>{portal.name}</h2>
      <div style={{ opacity: 0.8 }}>{portal.description || ""}</div>
      <h3 style={{ marginTop: 16 }}>Events</h3>
      {(portal.events || []).length === 0 ? (
        <div>No events attached.</div>
      ) : (
        <ul style={{ paddingLeft: 18 }}>
          {portal.events.map((e) => (
            <li key={e.id}>
              <Link to={`/events/${e.id}`}>{e.title}</Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
