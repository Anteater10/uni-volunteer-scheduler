// src/pages/OrganizerEventPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../lib/api";
import { parseApiDate, toEpochMs } from "../lib/datetime";
import {
  PageHeader,
  Card,
  Button,
  Modal,
  Input,
  Label,
  FieldError,
  EmptyState,
  Skeleton,
} from "../components/ui";
import { toast } from "../state/toast";
import { cn } from "../lib/cn";

function toDateTimeLocalValue(iso) {
  if (!iso) return "";
  const d = parseApiDate(iso);
  if (!d || Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fromDateTimeLocalToIso(value) {
  if (!value) return null;
  const d = new Date(value);
  return d.toISOString();
}

function CheckInPill({ checkedIn }) {
  return (
    <span
      className={cn(
        "inline-flex min-h-6 items-center rounded-full px-3 text-xs font-medium",
        checkedIn
          ? "bg-[var(--color-success)] text-white"
          : "bg-[var(--color-surface)] text-[var(--color-fg-muted)] border border-[var(--color-border)]",
      )}
    >
      {/* TODO(copy) */}
      {checkedIn ? "Checked in" : "Not yet"}
    </span>
  );
}

export default function OrganizerEventPage() {
  const { eventId } = useParams();
  const nav = useNavigate();

  const [event, setEvent] = useState(null);
  const [slots, setSlots] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [eventDraft, setEventDraft] = useState(null);
  const [savingEvent, setSavingEvent] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDeleteSlot, setConfirmDeleteSlot] = useState(null);
  const [newSlot, setNewSlot] = useState({ start_time: "", end_time: "", capacity: 1 });
  const [creatingSlot, setCreatingSlot] = useState(false);

  // Local-only check-in UI state; backend wiring is a TODO for a future phase.
  const [checkedIn, setCheckedIn] = useState({});

  const attachedSlotsSorted = useMemo(() => {
    return [...(slots || [])].sort(
      (a, b) => toEpochMs(a.start_time) - toEpochMs(b.start_time),
    );
  }, [slots]);

  // Derive a simple roster from slots. Real roster wiring is a future backend hookup.
  const roster = useMemo(() => {
    const rows = [];
    attachedSlotsSorted.forEach((s) => {
      for (let i = 0; i < (s.current_count || 0); i += 1) {
        const id = `${s.id}:${i}`;
        rows.push({
          id,
          /* TODO(copy): attendee label placeholder */
          name: `Attendee ${i + 1}`,
          slotLabel: toDateTimeLocalValue(s.start_time),
        });
      }
    });
    return rows;
  }, [attachedSlotsSorted]);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      const e = await api.getEvent(eventId);
      setEvent(e);
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
      setEventDraft({
        title: e.title || "",
        description: e.description || "",
        location: e.location || "",
        start_date_local: toDateTimeLocalValue(e.start_date),
        end_date_local: toDateTimeLocalValue(e.end_date),
      });
    } catch (e) {
      setErr(e?.message || "Failed to load event");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId]);

  async function saveEvent() {
    if (!eventDraft) return;
    setErr("");
    setSavingEvent(true);
    try {
      const payload = {
        title: eventDraft.title?.trim() || null,
        description: eventDraft.description?.trim() || null,
        location: eventDraft.location?.trim() || null,
        start_date: fromDateTimeLocalToIso(eventDraft.start_date_local),
        end_date: fromDateTimeLocalToIso(eventDraft.end_date_local),
      };
      const updated = await api.updateEvent(eventId, payload);
      setEvent(updated);
      // TODO(copy): saved toast
      toast.success("Event saved.");
    } catch (e) {
      setErr(e?.message || "Failed to save event");
    } finally {
      setSavingEvent(false);
    }
  }

  async function doDeleteEvent() {
    try {
      await api.deleteEvent(eventId);
      setConfirmDelete(false);
      // TODO(copy)
      toast.success("Event deleted.");
      nav("/organizer");
    } catch (e) {
      setErr(e?.message || "Failed to delete event");
    }
  }

  async function doDeleteSlot() {
    if (!confirmDeleteSlot) return;
    try {
      await api.deleteSlot(confirmDeleteSlot);
      setConfirmDeleteSlot(null);
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
      // TODO(copy)
      toast.success("Slot deleted.");
    } catch (e) {
      setErr(e?.message || "Failed to delete slot");
    }
  }

  async function createSlot(e) {
    e.preventDefault();
    setErr("");
    if (!newSlot.start_time || !newSlot.end_time) {
      setErr("Slot start/end time required.");
      return;
    }
    setCreatingSlot(true);
    try {
      await api.createSlot(eventId, {
        start_time: fromDateTimeLocalToIso(newSlot.start_time),
        end_time: fromDateTimeLocalToIso(newSlot.end_time),
        capacity: Number(newSlot.capacity || 1),
      });
      setNewSlot({ start_time: "", end_time: "", capacity: 1 });
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
      // TODO(copy)
      toast.success("Slot created.");
    } catch (e2) {
      setErr(e2?.message || "Failed to create slot");
    } finally {
      setCreatingSlot(false);
    }
  }

  function toggleCheckIn(rowId) {
    setCheckedIn((prev) => {
      const next = { ...prev, [rowId]: !prev[rowId] };
      // TODO(copy): checked-in toast
      toast.success(next[rowId] ? "Checked in." : "Undid check-in.");
      return next;
    });
  }

  if (loading) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (!event) {
    return (
      <EmptyState
        /* TODO(copy) */
        title="Event not found"
        action={
          <Button as={Link} to="/organizer">
            {/* TODO(copy) */}
            Back to organizer
          </Button>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={event.title}
        /* TODO(copy) */
        subtitle="Roster"
        action={
          <div className="flex gap-2">
            <Button variant="danger" onClick={() => setConfirmDelete(true)}>
              {/* TODO(copy) */}
              Delete
            </Button>
          </div>
        }
      />

      {err && (
        <FieldError>
          {err}
        </FieldError>
      )}

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Roster
        </h2>
        {roster.length === 0 ? (
          <EmptyState
            /* TODO(copy) */
            title="No signups yet"
          />
        ) : (
          <ul className="divide-y divide-[var(--color-border)] rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)]">
            {roster.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => toggleCheckIn(r.id)}
                  className="flex w-full min-h-14 items-center justify-between gap-3 px-3 py-2 text-left hover:bg-[var(--color-surface)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
                >
                  <div>
                    <p className="font-medium">{r.name}</p>
                    <p className="text-sm text-[var(--color-fg-muted)]">{r.slotLabel}</p>
                  </div>
                  <CheckInPill checkedIn={!!checkedIn[r.id]} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Event settings
        </h2>
        {eventDraft && (
          <Card>
            <div className="space-y-3">
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="ev-title">Title</Label>
                <Input
                  id="ev-title"
                  value={eventDraft.title}
                  onChange={(e) =>
                    setEventDraft((p) => ({ ...p, title: e.target.value }))
                  }
                />
              </div>
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="ev-location">Location</Label>
                <Input
                  id="ev-location"
                  value={eventDraft.location}
                  onChange={(e) =>
                    setEventDraft((p) => ({ ...p, location: e.target.value }))
                  }
                />
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  {/* TODO(copy) */}
                  <Label htmlFor="ev-start">Start</Label>
                  <Input
                    id="ev-start"
                    type="datetime-local"
                    value={eventDraft.start_date_local}
                    onChange={(e) =>
                      setEventDraft((p) => ({ ...p, start_date_local: e.target.value }))
                    }
                  />
                </div>
                <div>
                  {/* TODO(copy) */}
                  <Label htmlFor="ev-end">End</Label>
                  <Input
                    id="ev-end"
                    type="datetime-local"
                    value={eventDraft.end_date_local}
                    onChange={(e) =>
                      setEventDraft((p) => ({ ...p, end_date_local: e.target.value }))
                    }
                  />
                </div>
              </div>
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="ev-desc">Description</Label>
                <textarea
                  id="ev-desc"
                  rows={3}
                  value={eventDraft.description}
                  onChange={(e) =>
                    setEventDraft((p) => ({ ...p, description: e.target.value }))
                  }
                  className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-base"
                />
              </div>
              <div className="flex justify-end">
                <Button onClick={saveEvent} disabled={savingEvent}>
                  {/* TODO(copy) */}
                  {savingEvent ? "Saving..." : "Save event"}
                </Button>
              </div>
            </div>
          </Card>
        )}
      </section>

      <section>
        {/* TODO(copy) */}
        <h2 className="text-sm font-medium text-[var(--color-fg-muted)] uppercase tracking-wide mb-2">
          Slots
        </h2>
        <Card className="mb-3">
          <form onSubmit={createSlot} className="space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="slot-start">Start</Label>
                <Input
                  id="slot-start"
                  type="datetime-local"
                  value={newSlot.start_time}
                  onChange={(e) => setNewSlot((p) => ({ ...p, start_time: e.target.value }))}
                />
              </div>
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="slot-end">End</Label>
                <Input
                  id="slot-end"
                  type="datetime-local"
                  value={newSlot.end_time}
                  onChange={(e) => setNewSlot((p) => ({ ...p, end_time: e.target.value }))}
                />
              </div>
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="slot-cap">Capacity</Label>
                <Input
                  id="slot-cap"
                  type="number"
                  min={1}
                  value={newSlot.capacity}
                  onChange={(e) => setNewSlot((p) => ({ ...p, capacity: e.target.value }))}
                />
              </div>
            </div>
            <div className="flex justify-end">
              <Button type="submit" disabled={creatingSlot}>
                {/* TODO(copy) */}
                {creatingSlot ? "Creating..." : "Create slot"}
              </Button>
            </div>
          </form>
        </Card>
        {attachedSlotsSorted.length === 0 ? (
          <EmptyState
            /* TODO(copy) */
            title="No slots yet"
          />
        ) : (
          <ul className="space-y-2">
            {attachedSlotsSorted.map((s) => (
              <li key={s.id}>
                <Card>
                  <div className="flex items-center justify-between gap-3">
                    <div className="text-sm">
                      <p className="font-medium">
                        {toDateTimeLocalValue(s.start_time)} → {toDateTimeLocalValue(s.end_time)}
                      </p>
                      <p className="text-[var(--color-fg-muted)] text-xs">
                        {/* TODO(copy) */}
                        {s.current_count}/{s.capacity} signups
                      </p>
                    </div>
                    <Button
                      variant="ghost"
                      onClick={() => setConfirmDeleteSlot(s.id)}
                    >
                      {/* TODO(copy) */}
                      Delete
                    </Button>
                  </div>
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Modal
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        /* TODO(copy) */
        title="Delete event"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Permanently delete "{event.title}"? This removes slots and questions too.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setConfirmDelete(false)}>
            {/* TODO(copy) */}
            Keep it
          </Button>
          <Button variant="danger" onClick={doDeleteEvent}>
            {/* TODO(copy) */}
            Delete event
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!confirmDeleteSlot}
        onClose={() => setConfirmDeleteSlot(null)}
        /* TODO(copy) */
        title="Delete slot"
      >
        <p className="text-sm">
          {/* TODO(copy) */}
          Delete this slot? Any signups for it will be affected.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setConfirmDeleteSlot(null)}>
            {/* TODO(copy) */}
            Keep it
          </Button>
          <Button variant="danger" onClick={doDeleteSlot}>
            {/* TODO(copy) */}
            Delete slot
          </Button>
        </div>
      </Modal>
    </div>
  );
}
