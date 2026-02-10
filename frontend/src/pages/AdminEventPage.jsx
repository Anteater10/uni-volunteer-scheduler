// AdmineventPage.jsx
import React, { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";

export default function AdminEventPage() {
  const { eventId } = useParams();
  const [privacy, setPrivacy] = useState("full");
  const [err, setErr] = useState("");
  const [notify, setNotify] = useState({ subject: "", body: "", include_waitlisted: false });

  const analyticsQ = useQuery({
    queryKey: ["adminEventAnalytics", eventId],
    queryFn: () => api.admin.eventAnalytics(eventId),
  });

  const rosterQ = useQuery({
    queryKey: ["adminEventRoster", eventId, privacy],
    queryFn: () => api.admin.eventRoster(eventId, privacy),
  });

  async function exportCsv() {
    setErr("");
    try {
      await downloadBlob(`/admin/events/${eventId}/export_csv`, `event_${eventId}.csv`, { auth: true });
    } catch (e) {
      setErr(e.message || "Export failed");
    }
  }

  async function sendNotify(e) {
    e.preventDefault();
    setErr("");
    try {
      await api.admin.notify(eventId, notify);
      alert("Sent!");
      setNotify({ subject: "", body: "", include_waitlisted: false });
    } catch (e2) {
      setErr(e2.message || "Notify failed");
    }
  }

  return (
    <div style={{ display: "grid", gap: 14 }}>
      <h2>Admin: Event</h2>
      <div style={{ opacity: 0.8 }}>eventId: {eventId}</div>

      {err && <div style={{ color: "crimson" }}>{err}</div>}

      <section style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
        <h3>Analytics</h3>
        {analyticsQ.isLoading ? (
          <div>Loading…</div>
        ) : analyticsQ.error ? (
          <div style={{ color: "crimson" }}>{analyticsQ.error.message}</div>
        ) : (
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(analyticsQ.data, null, 2)}</pre>
        )}
      </section>

      <section style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
        <h3>Roster</h3>
        <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
          Privacy:
          <select value={privacy} onChange={(e) => setPrivacy(e.target.value)}>
            <option value="full">full</option>
            <option value="initials">initials</option>
            <option value="anonymous">anonymous</option>
          </select>
          <button type="button" onClick={exportCsv}>Export CSV</button>
        </label>

        {rosterQ.isLoading ? (
          <div>Loading…</div>
        ) : rosterQ.error ? (
          <div style={{ color: "crimson" }}>{rosterQ.error.message}</div>
        ) : (
          <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify(rosterQ.data, null, 2)}</pre>
        )}
      </section>

      <section style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
        <h3>Notify Participants</h3>
        <form onSubmit={sendNotify} style={{ display: "grid", gap: 10, maxWidth: 700 }}>
          <label>
            Subject
            <input value={notify.subject} onChange={(e) => setNotify((p) => ({ ...p, subject: e.target.value }))} required />
          </label>
          <label>
            Body
            <textarea value={notify.body} onChange={(e) => setNotify((p) => ({ ...p, body: e.target.value }))} rows={5} required />
          </label>
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={notify.include_waitlisted}
              onChange={(e) => setNotify((p) => ({ ...p, include_waitlisted: e.target.checked }))}
            />
            Include waitlisted
          </label>
          <button>Send</button>
        </form>
      </section>
    </div>
  );
}
