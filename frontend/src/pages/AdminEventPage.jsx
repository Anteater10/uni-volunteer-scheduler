// AdmineventPage.jsx
import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";

export default function AdminEventPage() {
  const { eventId } = useParams();
  const [privacy, setPrivacy] = useState("full");
  const [err, setErr] = useState("");
  const [notify, setNotify] = useState({ subject: "", body: "", include_waitlisted: false });
  const [statusFilter, setStatusFilter] = useState({
    confirmed: true,
    waitlisted: true,
    cancelled: false,
  });
  const [openAnswers, setOpenAnswers] = useState({});
  const [moveTargets, setMoveTargets] = useState({});
  const qc = useQueryClient();

  const analyticsQ = useQuery({
    queryKey: ["adminEventAnalytics", eventId],
    queryFn: () => api.admin.eventAnalytics(eventId),
  });

  const rosterQ = useQuery({
    queryKey: ["adminEventRoster", eventId, privacy],
    queryFn: () => api.admin.eventRoster(eventId, privacy),
  });

  const slotsQ = useQuery({
    queryKey: ["slots", eventId],
    queryFn: () => api.listSlots({ event_id: eventId }),
  });

  const roster = rosterQ.data || [];
  const slots = slotsQ.data || [];

  const slotOptions = useMemo(() => {
    if (slots.length > 0) return slots;
    const unique = new Map();
    for (const r of roster) {
      if (!unique.has(r.slot_id)) {
        unique.set(r.slot_id, {
          id: r.slot_id,
          start_time: r.slot_start,
          end_time: r.slot_end,
        });
      }
    }
    return Array.from(unique.values());
  }, [roster, slots]);

  const groupedRoster = useMemo(() => {
    const groups = new Map();
    for (const row of roster) {
      if (!statusFilter[row.status]) continue;
      if (!groups.has(row.slot_id)) groups.set(row.slot_id, []);
      groups.get(row.slot_id).push(row);
    }
    return Array.from(groups.entries()).map(([slotId, rows]) => ({
      slotId,
      rows,
      slotStart: rows[0]?.slot_start,
      slotEnd: rows[0]?.slot_end,
      slotCapacity: rows[0]?.slot_capacity,
      slotCurrentCount: rows[0]?.slot_current_count,
    }));
  }, [roster, statusFilter]);

  function fmtTime(iso) {
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  }

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

  async function runRosterAction(fn, fallback) {
    setErr("");
    try {
      await fn();
      await qc.invalidateQueries({ queryKey: ["adminEventRoster", eventId] });
      await qc.invalidateQueries({ queryKey: ["slots", eventId] });
    } catch (e) {
      setErr(e.message || fallback);
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
        <div style={{ display: "flex", gap: 12, marginTop: 10 }}>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={statusFilter.confirmed}
              onChange={(e) => setStatusFilter((p) => ({ ...p, confirmed: e.target.checked }))}
            />
            Confirmed
          </label>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={statusFilter.waitlisted}
              onChange={(e) => setStatusFilter((p) => ({ ...p, waitlisted: e.target.checked }))}
            />
            Waitlisted
          </label>
          <label style={{ display: "flex", gap: 6, alignItems: "center" }}>
            <input
              type="checkbox"
              checked={statusFilter.cancelled}
              onChange={(e) => setStatusFilter((p) => ({ ...p, cancelled: e.target.checked }))}
            />
            Cancelled
          </label>
        </div>

        {rosterQ.isLoading ? (
          <div>Loading…</div>
        ) : rosterQ.error ? (
          <div style={{ color: "crimson" }}>{rosterQ.error.message}</div>
        ) : (
          <div style={{ display: "grid", gap: 12, marginTop: 10 }}>
            {groupedRoster.length === 0 ? (
              <div>No signups for selected filters.</div>
            ) : (
              groupedRoster.map((group) => (
                <div key={group.slotId} style={{ border: "1px solid #3333", borderRadius: 8, padding: 10 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 10, marginBottom: 6 }}>
                    <div style={{ fontWeight: 600 }}>
                      Slot: {fmtTime(group.slotStart)} → {fmtTime(group.slotEnd)}
                    </div>
                    <div style={{ opacity: 0.8 }}>
                      Capacity: {group.slotCurrentCount}/{group.slotCapacity}
                    </div>
                  </div>
                  <div style={{ display: "grid", gap: 8 }}>
                    {group.rows.map((row) => {
                      const name = row.participant?.name || "Volunteer";
                      const email = row.participant?.email;
                      const waitlistLabel =
                        row.status === "waitlisted" && row.waitlist_position
                          ? ` (position #${row.waitlist_position})`
                          : "";
                      const targetValue = moveTargets[row.signup_id] || "";
                      const otherSlots = slotOptions.filter((s) => String(s.id) !== String(row.slot_id));

                      return (
                        <div key={row.signup_id} style={{ border: "1px solid #3332", borderRadius: 6, padding: 8 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", gap: 10 }}>
                            <div>
                              <div style={{ fontWeight: 600 }}>
                                {name}
                                {email ? <span style={{ marginLeft: 8, opacity: 0.75 }}>{email}</span> : null}
                              </div>
                              <div style={{ opacity: 0.8 }}>
                                Status: {row.status}
                                {waitlistLabel}
                              </div>
                            </div>
                            <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
                              {row.status !== "cancelled" && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    runRosterAction(
                                      () => api.admin.signups.cancel(row.signup_id),
                                      "Cancel failed",
                                    )
                                  }
                                >
                                  Cancel
                                </button>
                              )}
                              {row.status === "waitlisted" && (
                                <button
                                  type="button"
                                  onClick={() =>
                                    runRosterAction(
                                      () => api.admin.signups.promote(row.signup_id),
                                      "Promote failed",
                                    )
                                  }
                                >
                                  Promote
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() =>
                                  runRosterAction(
                                    () => api.admin.signups.resend(row.signup_id),
                                    "Resend failed",
                                  )
                                }
                              >
                                Resend
                              </button>
                            </div>
                          </div>

                          <div style={{ display: "flex", gap: 8, marginTop: 6, alignItems: "center", flexWrap: "wrap" }}>
                            <select
                              value={targetValue}
                              onChange={(e) =>
                                setMoveTargets((p) => ({ ...p, [row.signup_id]: e.target.value }))
                              }
                              disabled={otherSlots.length === 0 || row.status === "cancelled"}
                            >
                              <option value="">Move to slot…</option>
                              {otherSlots.map((s) => (
                                <option key={s.id} value={s.id}>
                                  {fmtTime(s.start_time)} → {fmtTime(s.end_time)}
                                </option>
                              ))}
                            </select>
                            <button
                              type="button"
                              disabled={!targetValue || row.status === "cancelled"}
                              onClick={() =>
                                runRosterAction(
                                  () => api.admin.signups.move(row.signup_id, targetValue),
                                  "Move failed",
                                )
                              }
                            >
                              Move
                            </button>
                            <button
                              type="button"
                              onClick={() =>
                                setOpenAnswers((p) => ({ ...p, [row.signup_id]: !p[row.signup_id] }))
                              }
                            >
                              {openAnswers[row.signup_id] ? "Hide answers" : "View answers"}
                            </button>
                          </div>

                          {openAnswers[row.signup_id] && (
                            <div style={{ marginTop: 6, paddingLeft: 6 }}>
                              {row.answers && Object.keys(row.answers).length > 0 ? (
                                <ul style={{ margin: 0, paddingLeft: 18 }}>
                                  {Object.entries(row.answers).map(([q, a]) => (
                                    <li key={q}>
                                      <strong>{q}:</strong> {a}
                                    </li>
                                  ))}
                                </ul>
                              ) : (
                                <div style={{ opacity: 0.7 }}>No answers.</div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))
            )}
          </div>
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
