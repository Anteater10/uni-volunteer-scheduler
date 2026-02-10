// adminDashboardPage.jsx
import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../lib/api";

export default function AdminDashboardPage() {
  const q = useQuery({ queryKey: ["adminSummary"], queryFn: api.admin.summary });

  if (q.isLoading) return <div>Loading admin summary…</div>;
  if (q.error) return <div style={{ color: "crimson" }}>Failed: {q.error.message}</div>;

  const s = q.data;

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <h2>Admin</h2>

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap" }}>
        <Stat label="Users" value={s.total_users} />
        <Stat label="Events" value={s.total_events} />
        <Stat label="Slots" value={s.total_slots} />
        <Stat label="Signups" value={s.total_signups} />
        <Stat label="Signups (7d)" value={s.signups_last_7d} />
      </div>

      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <Link to="/admin/users">Manage Users</Link>
        <Link to="/admin/portals">Manage Portals</Link>
        <Link to="/admin/audit-logs">Audit Logs</Link>
      </div>

      <div style={{ opacity: 0.8 }}>
        To view per-event analytics/roster/export/notify: open any event ID and go to <code>/admin/events/&lt;eventId&gt;</code>
      </div>
    </div>
  );
}

function Stat({ label, value }) {
  return (
    <div style={{ padding: 12, border: "1px solid #3333", borderRadius: 8, minWidth: 140 }}>
      <div style={{ opacity: 0.8, fontSize: 12 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 800 }}>{value}</div>
    </div>
  );
}
