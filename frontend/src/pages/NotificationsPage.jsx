import React from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../lib/api";

export default function NotificationsPage() {
  const q = useQuery({
    queryKey: ["myNotifications"],
    queryFn: api.notifications.my,
  });

  if (q.isLoading) return <div>Loading notifications…</div>;
  if (q.error) return <div style={{ color: "crimson" }}>Failed: {q.error.message}</div>;

  const items = q.data || [];

  return (
    <div>
      <h2>Notifications</h2>
      {items.length === 0 ? (
        <div>No notifications yet.</div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {items.map((n) => (
            <div key={n.id} style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
              <div style={{ fontWeight: 700 }}>{n.subject || "(no subject)"}</div>
              <div style={{ opacity: 0.8, fontSize: 13 }}>
                {n.type} • {new Date(n.created_at).toLocaleString()}
              </div>
              <pre style={{ whiteSpace: "pre-wrap", marginTop: 8 }}>{n.body}</pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
