// src/pages/OrganizerEventPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import api from "../lib/api";
import { parseApiDate, toEpochMs } from "../lib/datetime";

function toDateTimeLocalValue(iso) {
  if (!iso) return "";
  const d = parseApiDate(iso);
  if (!d || Number.isNaN(d.getTime())) return "";
  const pad = (n) => String(n).padStart(2, "0");
  const yyyy = d.getFullYear();
  const mm = pad(d.getMonth() + 1);
  const dd = pad(d.getDate());
  const hh = pad(d.getHours());
  const mi = pad(d.getMinutes());
  return `${yyyy}-${mm}-${dd}T${hh}:${mi}`;
}

// Converts a datetime-local string (local time) -> ISO string (UTC) for backend
function fromDateTimeLocalToIso(value) {
  if (!value) return null;
  const d = new Date(value); // interpreted as local time
  return d.toISOString(); // stored as UTC
}

export default function OrganizerEventPage() {
  const { eventId } = useParams();
  const nav = useNavigate();

  const [event, setEvent] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [slots, setSlots] = useState([]);

  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  // Event edit draft
  const [eventDraft, setEventDraft] = useState(null);
  const [savingEvent, setSavingEvent] = useState(false);

  // Slot CRUD drafts
  const [slotDrafts, setSlotDrafts] = useState({}); // { [slotId]: {start_time,end_time,capacity} }
  const [savingSlotIds, setSavingSlotIds] = useState({}); // { [slotId]: true }
  const [creatingSlot, setCreatingSlot] = useState(false);
  const [newSlot, setNewSlot] = useState({
    start_time: "",
    end_time: "",
    capacity: 1,
  });

  // Generate slots
  const [gen, setGen] = useState({
    start_time: "",
    end_time: "",
    capacity: 1,
    frequency: "weekly",
    count: 4,
  });
  const [generating, setGenerating] = useState(false);

  // Questions CRUD
  const [qDrafts, setQDrafts] = useState({}); // { [qid]: {prompt, field_type, required, options, sort_order} }
  const [savingQIds, setSavingQIds] = useState({});
  const [creatingQ, setCreatingQ] = useState(false);
  const [newQ, setNewQ] = useState({
    prompt: "",
    field_type: "text",
    required: false,
    optionsCsv: "",
    sort_order: 0,
  });

  const attachedSlotsSorted = useMemo(() => {
    const copy = [...(slots || [])];
    copy.sort((a, b) => toEpochMs(a.start_time) - toEpochMs(b.start_time));
    return copy;
  }, [slots]);

  async function loadAll() {
    setErr("");
    setLoading(true);
    try {
      const e = await api.getEvent(eventId);
      setEvent(e);

      // EventRead includes slots in your schema, but we still refresh slots explicitly
      // to stay consistent with slot CRUD endpoints.
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);

      const qs = await api.listEventQuestions(eventId);
      setQuestions(qs || []);

      // Initialize draft
      setEventDraft({
        title: e.title || "",
        description: e.description || "",
        location: e.location || "",
        visibility: e.visibility || "public",
        branding_id: e.branding_id || "",
        start_date_local: toDateTimeLocalValue(e.start_date),
        end_date_local: toDateTimeLocalValue(e.end_date),
        max_signups_per_user: e.max_signups_per_user ?? "",
        signup_open_at_local: toDateTimeLocalValue(e.signup_open_at),
        signup_close_at_local: toDateTimeLocalValue(e.signup_close_at),
      });
    } catch (e) {
      setErr(e?.message || "Failed to load organizer event page");
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
        visibility: eventDraft.visibility || "public",
        branding_id: eventDraft.branding_id?.trim() || null,

        start_date: fromDateTimeLocalToIso(eventDraft.start_date_local),
        end_date: fromDateTimeLocalToIso(eventDraft.end_date_local),

        max_signups_per_user:
          eventDraft.max_signups_per_user === "" ? null : Number(eventDraft.max_signups_per_user),

        signup_open_at: fromDateTimeLocalToIso(eventDraft.signup_open_at_local),
        signup_close_at: fromDateTimeLocalToIso(eventDraft.signup_close_at_local),
      };

      const updated = await api.updateEvent(eventId, payload);
      setEvent(updated);

      // Refresh slots/questions too
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
      const qs = await api.listEventQuestions(eventId);
      setQuestions(qs || []);

      // keep local draft in sync
      setEventDraft((d) => ({
        ...d,
        start_date_local: toDateTimeLocalValue(updated.start_date),
        end_date_local: toDateTimeLocalValue(updated.end_date),
        signup_open_at_local: toDateTimeLocalValue(updated.signup_open_at),
        signup_close_at_local: toDateTimeLocalValue(updated.signup_close_at),
      }));
    } catch (e) {
      setErr(e?.message || "Failed to save event");
    } finally {
      setSavingEvent(false);
    }
  }

  async function deleteEvent() {
    if (!event) return;
    const ok = window.confirm(
      `Delete event "${event.title}"?\n\nThis will remove the event and related slots/questions.`
    );
    if (!ok) return;

    setErr("");
    try {
      await api.deleteEvent(eventId);
      nav("/organizer");
    } catch (e) {
      setErr(e?.message || "Failed to delete event");
    }
  }

  async function cloneEvent() {
    if (!event) return;
    setErr("");
    try {
      const cloned = await api.cloneEvent(eventId);
      nav(`/organizer/events/${cloned.id}`);
    } catch (e) {
      setErr(e?.message || "Failed to clone event");
    }
  }

  // -----------------
  // Slots
  // -----------------

  function setSlotDraft(slotId, patch) {
    setSlotDrafts((prev) => ({
      ...prev,
      [slotId]: { ...(prev[slotId] || {}), ...patch },
    }));
  }

  function getSlotDraftValue(slot, field) {
    const d = slotDrafts[slot.id] || {};
    return d[field] !== undefined ? d[field] : slot[field];
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
      const payload = {
        start_time: fromDateTimeLocalToIso(newSlot.start_time),
        end_time: fromDateTimeLocalToIso(newSlot.end_time),
        capacity: Number(newSlot.capacity || 1),
      };
      await api.createSlot(eventId, payload);

      setNewSlot({ start_time: "", end_time: "", capacity: 1 });
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
    } catch (e2) {
      setErr(e2?.message || "Failed to create slot");
    } finally {
      setCreatingSlot(false);
    }
  }

  async function saveSlot(slotId) {
    const patch = slotDrafts[slotId];
    if (!patch) return;

    setErr("");
    setSavingSlotIds((p) => ({ ...p, [slotId]: true }));
    try {
      const payload = {};
      if (patch.start_time_local !== undefined) payload.start_time = fromDateTimeLocalToIso(patch.start_time_local);
      if (patch.end_time_local !== undefined) payload.end_time = fromDateTimeLocalToIso(patch.end_time_local);
      if (patch.capacity !== undefined) payload.capacity = Number(patch.capacity);

      const updated = await api.updateSlot(slotId, payload);

      setSlots((prev) => prev.map((s) => (s.id === slotId ? updated : s)));
      setSlotDrafts((prev) => {
        const copy = { ...prev };
        delete copy[slotId];
        return copy;
      });
    } catch (e) {
      setErr(e?.message || "Failed to update slot");
    } finally {
      setSavingSlotIds((p) => {
        const copy = { ...p };
        delete copy[slotId];
        return copy;
      });
    }
  }

  async function deleteSlot(slotId) {
    const ok = window.confirm("Delete this slot?");
    if (!ok) return;

    setErr("");
    try {
      await api.deleteSlot(slotId);
      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
    } catch (e) {
      setErr(e?.message || "Failed to delete slot");
    }
  }

  async function generateSlots(e) {
    e.preventDefault();
    setErr("");

    if (!gen.start_time || !gen.end_time) {
      setErr("Generate slots requires start/end time.");
      return;
    }

    setGenerating(true);
    try {
      const payload = {
        start_time: fromDateTimeLocalToIso(gen.start_time),
        end_time: fromDateTimeLocalToIso(gen.end_time),
        capacity: Number(gen.capacity || 1),
        frequency: gen.frequency,
        count: Number(gen.count || 1),
      };
      await api.generateSlots(eventId, payload);

      const s = await api.listSlots({ event_id: eventId });
      setSlots(s || []);
    } catch (e2) {
      setErr(e2?.message || "Failed to generate slots");
    } finally {
      setGenerating(false);
    }
  }

  // -----------------
  // Questions
  // -----------------

  function setQDraft(qid, patch) {
    setQDrafts((prev) => ({
      ...prev,
      [qid]: { ...(prev[qid] || {}), ...patch },
    }));
  }

  function getQDraftValue(q, field) {
    const d = qDrafts[q.id] || {};
    return d[field] !== undefined ? d[field] : q[field];
  }

  async function createQuestion(e) {
    e.preventDefault();
    setErr("");

    if (!newQ.prompt.trim()) {
      setErr("Question prompt is required.");
      return;
    }

    setCreatingQ(true);
    try {
      const options =
        newQ.optionsCsv.trim() === ""
          ? null
          : newQ.optionsCsv
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean);

      await api.createEventQuestion(eventId, {
        prompt: newQ.prompt.trim(),
        field_type: newQ.field_type,
        required: !!newQ.required,
        options,
        sort_order: Number(newQ.sort_order || 0),
      });

      setNewQ({ prompt: "", field_type: "text", required: false, optionsCsv: "", sort_order: 0 });
      const qs = await api.listEventQuestions(eventId);
      setQuestions(qs || []);
    } catch (e2) {
      setErr(e2?.message || "Failed to create question");
    } finally {
      setCreatingQ(false);
    }
  }

  async function saveQuestion(qid) {
    const patch = qDrafts[qid];
    if (!patch) return;

    setErr("");
    setSavingQIds((p) => ({ ...p, [qid]: true }));
    try {
      const payload = {};

      if (patch.prompt !== undefined) payload.prompt = patch.prompt;
      if (patch.field_type !== undefined) payload.field_type = patch.field_type;
      if (patch.required !== undefined) payload.required = !!patch.required;
      if (patch.sort_order !== undefined) payload.sort_order = Number(patch.sort_order || 0);

      if (patch.optionsCsv !== undefined) {
        const options =
          patch.optionsCsv.trim() === ""
            ? null
            : patch.optionsCsv
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean);
        payload.options = options;
      }

      const updated = await api.updateEventQuestion(qid, payload);
      setQuestions((prev) => prev.map((q) => (q.id === qid ? updated : q)));

      setQDrafts((prev) => {
        const copy = { ...prev };
        delete copy[qid];
        return copy;
      });
    } catch (e) {
      setErr(e?.message || "Failed to update question");
    } finally {
      setSavingQIds((p) => {
        const copy = { ...p };
        delete copy[qid];
        return copy;
      });
    }
  }

  async function deleteQuestion(qid) {
    const ok = window.confirm("Delete this question?");
    if (!ok) return;

    setErr("");
    try {
      await api.deleteEventQuestion(qid);
      const qs = await api.listEventQuestions(eventId);
      setQuestions(qs || []);
    } catch (e) {
      setErr(e?.message || "Failed to delete question");
    }
  }

  if (loading) {
    return (
      <div style={{ padding: 16 }}>
        <div>Loading event…</div>
      </div>
    );
  }

  if (!event) {
    return (
      <div style={{ padding: 16 }}>
        <div style={{ marginBottom: 10 }}>Event not found.</div>
        <Link to="/organizer">Back to Organizer</Link>
      </div>
    );
  }

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap" }}>
        <div>
          <h1 style={{ marginBottom: 6 }}>Organizer: Manage Event</h1>
          <div style={{ opacity: 0.85 }}>
            <div>
              <strong>{event.title}</strong> — <code>{event.id}</code>
            </div>
            <div style={{ marginTop: 6 }}>
              <Link to="/organizer">← Back to Organizer Dashboard</Link>{" "}
              <span style={{ opacity: 0.7 }}>·</span>{" "}
              <Link to={`/events/${event.id}`}>View public event page</Link>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button onClick={cloneEvent} type="button">
            Clone
          </button>
          <button onClick={deleteEvent} type="button">
            Delete
          </button>
        </div>
      </div>

      {err ? (
        <div
          style={{
            background: "rgba(255,0,0,0.08)",
            border: "1px solid rgba(255,0,0,0.25)",
            padding: 12,
            borderRadius: 10,
            margin: "14px 0",
            whiteSpace: "pre-wrap",
          }}
        >
          {err}
        </div>
      ) : null}

      <hr style={{ margin: "18px 0", opacity: 0.2 }} />

      {/* EVENT SETTINGS */}
      <section>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Event settings</h2>

        {!eventDraft ? (
          <div>Preparing form…</div>
        ) : (
          <>
            <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr" }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span>Title</span>
                <input
                  value={eventDraft.title}
                  onChange={(e) => setEventDraft((p) => ({ ...p, title: e.target.value }))}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Location</span>
                <input
                  value={eventDraft.location}
                  onChange={(e) => setEventDraft((p) => ({ ...p, location: e.target.value }))}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Visibility</span>
                <select
                  value={eventDraft.visibility}
                  onChange={(e) => setEventDraft((p) => ({ ...p, visibility: e.target.value }))}
                >
                  <option value="public">public</option>
                  <option value="private">private</option>
                </select>
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Branding ID (optional)</span>
                <input
                  value={eventDraft.branding_id}
                  onChange={(e) => setEventDraft((p) => ({ ...p, branding_id: e.target.value }))}
                  placeholder="e.g., scitrek"
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Start date/time</span>
                <input
                  type="datetime-local"
                  value={eventDraft.start_date_local}
                  onChange={(e) => setEventDraft((p) => ({ ...p, start_date_local: e.target.value }))}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>End date/time</span>
                <input
                  type="datetime-local"
                  value={eventDraft.end_date_local}
                  onChange={(e) => setEventDraft((p) => ({ ...p, end_date_local: e.target.value }))}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Max signups per user (optional)</span>
                <input
                  type="number"
                  value={eventDraft.max_signups_per_user}
                  onChange={(e) => setEventDraft((p) => ({ ...p, max_signups_per_user: e.target.value }))}
                  placeholder="(none)"
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Signup open at (optional)</span>
                <input
                  type="datetime-local"
                  value={eventDraft.signup_open_at_local}
                  onChange={(e) => setEventDraft((p) => ({ ...p, signup_open_at_local: e.target.value }))}
                />
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Signup close at (optional)</span>
                <input
                  type="datetime-local"
                  value={eventDraft.signup_close_at_local}
                  onChange={(e) => setEventDraft((p) => ({ ...p, signup_close_at_local: e.target.value }))}
                />
              </label>

              <label style={{ display: "grid", gap: 6, gridColumn: "1 / -1" }}>
                <span>Description</span>
                <textarea
                  rows={4}
                  value={eventDraft.description}
                  onChange={(e) => setEventDraft((p) => ({ ...p, description: e.target.value }))}
                />
              </label>
            </div>

            <div style={{ display: "flex", gap: 10, marginTop: 12 }}>
              <button onClick={saveEvent} disabled={savingEvent} type="button">
                {savingEvent ? "Saving…" : "Save event"}
              </button>
              <button onClick={loadAll} type="button">
                Refresh
              </button>
            </div>

            <p style={{ marginTop: 10, opacity: 0.8 }}>
              Note: we convert <code>datetime-local</code> to UTC ISO strings on submit to avoid the “works
              locally, breaks on deploy” timezone issue.
            </p>
          </>
        )}
      </section>

      <hr style={{ margin: "18px 0", opacity: 0.2 }} />

      {/* SLOTS */}
      <section>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Slots</h2>

        <div style={{ display: "grid", gap: 18, gridTemplateColumns: "1fr 1fr" }}>
          <div>
            <h3 style={{ fontSize: 16, marginBottom: 8 }}>Create single slot</h3>
            <form onSubmit={createSlot} style={{ display: "grid", gap: 10 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span>Start</span>
                <input
                  type="datetime-local"
                  value={newSlot.start_time}
                  onChange={(e) => setNewSlot((p) => ({ ...p, start_time: e.target.value }))}
                />
              </label>
              <label style={{ display: "grid", gap: 6 }}>
                <span>End</span>
                <input
                  type="datetime-local"
                  value={newSlot.end_time}
                  onChange={(e) => setNewSlot((p) => ({ ...p, end_time: e.target.value }))}
                />
              </label>
              <label style={{ display: "grid", gap: 6 }}>
                <span>Capacity</span>
                <input
                  type="number"
                  value={newSlot.capacity}
                  onChange={(e) => setNewSlot((p) => ({ ...p, capacity: e.target.value }))}
                  min={1}
                />
              </label>

              <button type="submit" disabled={creatingSlot}>
                {creatingSlot ? "Creating…" : "Create slot"}
              </button>
            </form>
          </div>

          <div>
            <h3 style={{ fontSize: 16, marginBottom: 8 }}>Generate recurring slots</h3>
            <form onSubmit={generateSlots} style={{ display: "grid", gap: 10 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span>First start</span>
                <input
                  type="datetime-local"
                  value={gen.start_time}
                  onChange={(e) => setGen((p) => ({ ...p, start_time: e.target.value }))}
                />
              </label>
              <label style={{ display: "grid", gap: 6 }}>
                <span>First end</span>
                <input
                  type="datetime-local"
                  value={gen.end_time}
                  onChange={(e) => setGen((p) => ({ ...p, end_time: e.target.value }))}
                />
              </label>

              <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr" }}>
                <label style={{ display: "grid", gap: 6 }}>
                  <span>Capacity</span>
                  <input
                    type="number"
                    value={gen.capacity}
                    onChange={(e) => setGen((p) => ({ ...p, capacity: e.target.value }))}
                    min={1}
                  />
                </label>
                <label style={{ display: "grid", gap: 6 }}>
                  <span>Frequency</span>
                  <select
                    value={gen.frequency}
                    onChange={(e) => setGen((p) => ({ ...p, frequency: e.target.value }))}
                  >
                    <option value="daily">daily</option>
                    <option value="weekly">weekly</option>
                  </select>
                </label>
                <label style={{ display: "grid", gap: 6 }}>
                  <span>Count</span>
                  <input
                    type="number"
                    value={gen.count}
                    onChange={(e) => setGen((p) => ({ ...p, count: e.target.value }))}
                    min={1}
                  />
                </label>
              </div>

              <button type="submit" disabled={generating}>
                {generating ? "Generating…" : "Generate"}
              </button>
            </form>
          </div>
        </div>

        <div style={{ marginTop: 16 }}>
          <h3 style={{ fontSize: 16, marginBottom: 8 }}>All slots</h3>
          {attachedSlotsSorted.length === 0 ? (
            <div style={{ opacity: 0.8 }}>No slots yet.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ textAlign: "left" }}>
                    <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Start</th>
                    <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>End</th>
                    <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Capacity</th>
                    <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Confirmed</th>
                    <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {attachedSlotsSorted.map((s) => {
                    const dirty = !!slotDrafts[s.id];
                    const saving = !!savingSlotIds[s.id];

                    return (
                      <tr key={s.id}>
                        <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                          <input
                            type="datetime-local"
                            value={
                              slotDrafts[s.id]?.start_time_local !== undefined
                                ? slotDrafts[s.id].start_time_local
                                : toDateTimeLocalValue(s.start_time)
                            }
                            onChange={(e) => setSlotDraft(s.id, { start_time_local: e.target.value })}
                          />
                        </td>
                        <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                          <input
                            type="datetime-local"
                            value={
                              slotDrafts[s.id]?.end_time_local !== undefined
                                ? slotDrafts[s.id].end_time_local
                                : toDateTimeLocalValue(s.end_time)
                            }
                            onChange={(e) => setSlotDraft(s.id, { end_time_local: e.target.value })}
                          />
                        </td>
                        <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                          <input
                            type="number"
                            min={1}
                            value={getSlotDraftValue(s, "capacity")}
                            onChange={(e) => setSlotDraft(s.id, { capacity: e.target.value })}
                          />
                        </td>
                        <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                          {s.current_count}
                        </td>
                        <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                          <div style={{ display: "flex", gap: 10 }}>
                            <button disabled={!dirty || saving} onClick={() => saveSlot(s.id)} type="button">
                              {saving ? "Saving…" : "Save"}
                            </button>
                            <button onClick={() => deleteSlot(s.id)} type="button">
                              Delete
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      <hr style={{ margin: "18px 0", opacity: 0.2 }} />

      {/* QUESTIONS */}
      <section>
        <h2 style={{ fontSize: 18, marginBottom: 8 }}>Custom questions</h2>

        <div style={{ display: "grid", gap: 18, gridTemplateColumns: "1fr 1fr" }}>
          <div>
            <h3 style={{ fontSize: 16, marginBottom: 8 }}>Create question</h3>
            <form onSubmit={createQuestion} style={{ display: "grid", gap: 10 }}>
              <label style={{ display: "grid", gap: 6 }}>
                <span>Prompt</span>
                <input
                  value={newQ.prompt}
                  onChange={(e) => setNewQ((p) => ({ ...p, prompt: e.target.value }))}
                  placeholder="e.g., Do you have prior experience?"
                />
              </label>

              <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr" }}>
                <label style={{ display: "grid", gap: 6 }}>
                  <span>Field type</span>
                  <select
                    value={newQ.field_type}
                    onChange={(e) => setNewQ((p) => ({ ...p, field_type: e.target.value }))}
                  >
                    <option value="text">text</option>
                    <option value="textarea">textarea</option>
                    <option value="select">select</option>
                    <option value="checkbox">checkbox</option>
                    <option value="radio">radio</option>
                  </select>
                </label>

                <label style={{ display: "grid", gap: 6 }}>
                  <span>Sort order</span>
                  <input
                    type="number"
                    value={newQ.sort_order}
                    onChange={(e) => setNewQ((p) => ({ ...p, sort_order: e.target.value }))}
                  />
                </label>
              </div>

              <label style={{ display: "flex", gap: 10, alignItems: "center" }}>
                <input
                  type="checkbox"
                  checked={newQ.required}
                  onChange={(e) => setNewQ((p) => ({ ...p, required: e.target.checked }))}
                />
                <span>Required</span>
              </label>

              <label style={{ display: "grid", gap: 6 }}>
                <span>Options (comma-separated; only for select/checkbox/radio)</span>
                <input
                  value={newQ.optionsCsv}
                  onChange={(e) => setNewQ((p) => ({ ...p, optionsCsv: e.target.value }))}
                  placeholder="Yes, No"
                />
              </label>

              <button type="submit" disabled={creatingQ}>
                {creatingQ ? "Creating…" : "Create question"}
              </button>
            </form>
          </div>

          <div>
            <h3 style={{ fontSize: 16, marginBottom: 8 }}>Existing questions</h3>
            {questions.length === 0 ? (
              <div style={{ opacity: 0.8 }}>No questions yet.</div>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {questions
                  .slice()
                  .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0))
                  .map((q) => {
                    const dirty = !!qDrafts[q.id];
                    const saving = !!savingQIds[q.id];

                    const optionsCsv =
                      qDrafts[q.id]?.optionsCsv !== undefined
                        ? qDrafts[q.id].optionsCsv
                        : (q.options || []).join(", ");

                    return (
                      <div
                        key={q.id}
                        style={{
                          border: "1px solid rgba(255,255,255,0.12)",
                          borderRadius: 12,
                          padding: 12,
                        }}
                      >
                        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "1fr 1fr" }}>
                          <label style={{ display: "grid", gap: 6, gridColumn: "1 / -1" }}>
                            <span>Prompt</span>
                            <input
                              value={getQDraftValue(q, "prompt") || ""}
                              onChange={(e) => setQDraft(q.id, { prompt: e.target.value })}
                            />
                          </label>

                          <label style={{ display: "grid", gap: 6 }}>
                            <span>Field type</span>
                            <select
                              value={getQDraftValue(q, "field_type") || "text"}
                              onChange={(e) => setQDraft(q.id, { field_type: e.target.value })}
                            >
                              <option value="text">text</option>
                              <option value="textarea">textarea</option>
                              <option value="select">select</option>
                              <option value="checkbox">checkbox</option>
                              <option value="radio">radio</option>
                            </select>
                          </label>

                          <label style={{ display: "grid", gap: 6 }}>
                            <span>Sort order</span>
                            <input
                              type="number"
                              value={getQDraftValue(q, "sort_order") ?? 0}
                              onChange={(e) => setQDraft(q.id, { sort_order: e.target.value })}
                            />
                          </label>

                          <label style={{ display: "flex", gap: 10, alignItems: "center" }}>
                            <input
                              type="checkbox"
                              checked={!!getQDraftValue(q, "required")}
                              onChange={(e) => setQDraft(q.id, { required: e.target.checked })}
                            />
                            <span>Required</span>
                          </label>

                          <label style={{ display: "grid", gap: 6, gridColumn: "1 / -1" }}>
                            <span>Options (comma-separated)</span>
                            <input
                              value={optionsCsv}
                              onChange={(e) => setQDraft(q.id, { optionsCsv: e.target.value })}
                              placeholder="(empty for text/textarea)"
                            />
                          </label>
                        </div>

                        <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                          <button disabled={!dirty || saving} onClick={() => saveQuestion(q.id)} type="button">
                            {saving ? "Saving…" : "Save"}
                          </button>
                          <button onClick={() => deleteQuestion(q.id)} type="button">
                            Delete
                          </button>
                        </div>

                        <div style={{ marginTop: 8, opacity: 0.75, fontSize: 12 }}>
                          <code>{q.id}</code>
                        </div>
                      </div>
                    );
                  })}
              </div>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
