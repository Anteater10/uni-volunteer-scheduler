// src/pages/OrganizerDashboardPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../lib/api";
import { toEpochMs } from "../lib/datetime";

function fromDateTimeLocalToIso(value) {
  if (!value) return null;
  const d = new Date(value);
  return d.toISOString();
}

export default function OrganizerDashboardPage() {
  const nav = useNavigate();

  const [me, setMe] = useState(null);
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // Create event form (simple MVP)
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    location: "",
    visibility: "public",
    start_date: "",
    end_date: "",
  });

  async function load() {
    setErr("");
    setLoading(true);
    try {
      const [u, evs] = await Promise.all([api.me(), api.listEvents()]);
      setMe(u);
      setEvents(evs || []);
    } catch (e) {
      setErr(e?.message || "Failed to load organizer dashboard");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const myEvents = useMemo(() => {
    if (!me) return [];
    return (events || [])
      .filter((e) => String(e.owner_id) === String(me.id))
      .sort((a, b) => toEpochMs(b.created_at || b.start_date) - toEpochMs(a.created_at || a.start_date));
  }, [events, me]);

  async function createEvent(e) {
    e.preventDefault();
    setErr("");

    if (!form.title.trim() || !form.start_date || !form.end_date) {
      setErr("Title, start date, and end date are required.");
      return;
    }

    setCreating(true);
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description?.trim() || null,
        location: form.location?.trim() || null,
        visibility: form.visibility || "public",
        start_date: fromDateTimeLocalToIso(form.start_date),
        end_date: fromDateTimeLocalToIso(form.end_date),
      };

      const created = await api.createEvent(payload);

      setForm({
        title: "",
        description: "",
        location: "",
        visibility: "public",
        start_date: "",
        end_date: "",
      });

      // Go straight to manage page
      nav(`/organizer/events/${created.id}`);
    } catch (e2) {
      setErr(e2?.message || "Failed to create event");
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 16 }}>
        <div>Loading…</div>
      </div>
    );
  }

  return (
    <div style={{ padding: 16, maxWidth: 1100, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>Organizer Dashboard</h1>

      {err ? (
        <div
          style={{
            background: "rgba(255,0,0,0.08)",
            border: "1px solid rgba(255,0,0,0.25)",
            padding: 12,
            borderRadius: 10,
            marginBottom: 12,
            whiteSpace: "pre-wrap",
          }}
        >
          {err}
        </div>
      ) : null}

      <div style={{ display: "grid", gap: 18, gridTemplateColumns: "1fr 1fr" }}>
        <section>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>My events</h2>

          {!me ? (
            <div style={{ opacity: 0.8 }}>Could not load user profile.</div>
          ) : myEvents.length === 0 ? (
            <div style={{ opacity: 0.8 }}>
              No events yet. Create one on the right.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 10 }}>
              {myEvents.map((e) => (
                <div
                  key={e.id}
                  style={{
                    border: "1px solid rgba(255,255,255,0.12)",
                    borderRadius: 12,
                    padding: 12,
                  }}
                >
                  <div style={{ fontWeight: 700 }}>{e.title}</div>
                  <div style={{ opacity: 0.8, marginTop: 4 }}>
                    <code style={{ fontSize: 12 }}>{e.id}</code>
                  </div>

                  <div style={{ display: "flex", gap: 10, marginTop: 10, flexWrap: "wrap" }}>
                    <Link to={`/organizer/events/${e.id}`}>Manage</Link>
                    <span style={{ opacity: 0.6 }}>·</span>
                    <Link to={`/events/${e.id}`}>Public view</Link>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div style={{ marginTop: 12 }}>
            <button onClick={load} type="button">
              Refresh
            </button>
          </div>
        </section>

        <section>
          <h2 style={{ fontSize: 18, marginBottom: 8 }}>Create event</h2>
          <form onSubmit={createEvent} style={{ display: "grid", gap: 10 }}>
            <label style={{ display: "grid", gap: 6 }}>
              <span>Title</span>
              <input
                value={form.title}
                onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
                placeholder="e.g., SciTrek Day 1 Volunteers"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Description</span>
              <textarea
                rows={3}
                value={form.description}
                onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Location</span>
              <input
                value={form.location}
                onChange={(e) => setForm((p) => ({ ...p, location: e.target.value }))}
                placeholder="Optional"
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Visibility</span>
              <select
                value={form.visibility}
                onChange={(e) => setForm((p) => ({ ...p, visibility: e.target.value }))}
              >
                <option value="public">public</option>
                <option value="private">private</option>
              </select>
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>Start date/time</span>
              <input
                type="datetime-local"
                value={form.start_date}
                onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))}
              />
            </label>

            <label style={{ display: "grid", gap: 6 }}>
              <span>End date/time</span>
              <input
                type="datetime-local"
                value={form.end_date}
                onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value }))}
              />
            </label>

            <button type="submit" disabled={creating}>
              {creating ? "Creating…" : "Create event"}
            </button>
          </form>
        </section>
      </div>
    </div>
  );
}
