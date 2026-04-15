// src/pages/OrganizerDashboardPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import api from "../lib/api";
import { toEpochMs } from "../lib/datetime";
import {
  PageHeader,
  Card,
  Button,
  Input,
  Label,
  FieldError,
  Skeleton,
  EmptyState,
} from "../components/ui";
import { toast } from "../state/toast";

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
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    title: "",
    description: "",
    location: "",
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
      .sort(
        (a, b) =>
          toEpochMs(b.created_at || b.start_date) -
          toEpochMs(a.created_at || a.start_date),
      );
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
        visibility: "public",
        start_date: fromDateTimeLocalToIso(form.start_date),
        end_date: fromDateTimeLocalToIso(form.end_date),
      };
      const created = await api.createEvent(payload);
      setForm({ title: "", description: "", location: "", start_date: "", end_date: "" });
      // TODO(copy)
      toast.success("Event created.");
      nav(`/organizer/events/${created.id}`);
    } catch (e2) {
      setErr(e2?.message || "Failed to create event");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* TODO(copy) */}
      <PageHeader title="My Events" />

      {loading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-28 w-full rounded-xl" />
          ))}
        </div>
      ) : myEvents.length === 0 ? (
        <EmptyState
          /* TODO(copy) */
          title="No events yet"
          /* TODO(copy) */
          body="Create one below."
        />
      ) : (
        <div className="space-y-3">
          {myEvents.map((e) => (
            <Card key={e.id}>
              <h3 className="text-base font-semibold">{e.title}</h3>
              <p className="text-sm text-[var(--color-fg-muted)]">
                {e.location || ""}
              </p>
              <div className="mt-3 flex gap-2">
                <Button
                  variant="secondary"
                  as={Link}
                  to={`/organizer/events/${e.id}`}
                >
                  {/* TODO(copy) */}
                  Open roster
                </Button>
                <Button variant="ghost" as={Link} to={`/events/${e.id}`}>
                  {/* TODO(copy) */}
                  View public
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Create event
        </h2>
        <Card>
          <form onSubmit={createEvent} className="space-y-3">
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="org-title">Title</Label>
              <Input
                id="org-title"
                value={form.title}
                onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="org-location">Location</Label>
              <Input
                id="org-location"
                value={form.location}
                onChange={(e) => setForm((p) => ({ ...p, location: e.target.value }))}
              />
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="org-start">Start</Label>
                <Input
                  id="org-start"
                  type="datetime-local"
                  value={form.start_date}
                  onChange={(e) => setForm((p) => ({ ...p, start_date: e.target.value }))}
                />
              </div>
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="org-end">End</Label>
                <Input
                  id="org-end"
                  type="datetime-local"
                  value={form.end_date}
                  onChange={(e) => setForm((p) => ({ ...p, end_date: e.target.value }))}
                />
              </div>
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="org-desc">Description</Label>
              <textarea
                id="org-desc"
                rows={3}
                value={form.description}
                onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
                className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-base"
              />
            </div>
            <FieldError>{err}</FieldError>
            <div className="flex justify-end">
              <Button type="submit" disabled={creating}>
                {/* TODO(copy) */}
                {creating ? "Creating..." : "Create event"}
              </Button>
            </div>
          </form>
        </Card>
      </section>
    </div>
  );
}
