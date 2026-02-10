import React, { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../lib/api";
import { useAuth } from "../state/authContext";

function isPast(endTime) {
  try {
    return new Date(endTime).getTime() <= Date.now();
  } catch {
    return false;
  }
}

export default function EventDetailPage() {
  const { eventId } = useParams();
  const qc = useQueryClient();
  const { isAuthed, role } = useAuth();

  const [err, setErr] = useState("");
  const [busySlot, setBusySlot] = useState(null);

  const eventQ = useQuery({
    queryKey: ["event", eventId],
    queryFn: () => api.events.get(eventId),
  });

  const event = eventQ.data;

  const sortedSlots = useMemo(() => {
    const slots = event?.slots || [];
    return [...slots].sort((a, b) => new Date(a.start_time) - new Date(b.start_time));
  }, [event]);

  async function signup(slotId) {
    setErr("");
    setBusySlot(slotId);
    try {
      await api.signups.create({ slot_id: slotId });
      await qc.invalidateQueries({ queryKey: ["mySignups"] });
      alert("Signed up!");
    } catch (e) {
      setErr(e.message || "Signup failed");
    } finally {
      setBusySlot(null);
    }
  }

  if (eventQ.isLoading) return <div>Loading event…</div>;
  if (eventQ.error) return <div style={{ color: "crimson" }}>Failed: {eventQ.error.message}</div>;
  if (!event) return <div>Not found.</div>;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div>
        <h2 style={{ marginBottom: 4 }}>{event.title}</h2>
        <div style={{ opacity: 0.8 }}>
          {event.location || "TBD"} • {new Date(event.start_date).toLocaleString()} → {new Date(event.end_date).toLocaleString()}
        </div>
      </div>

      {event.description && <p style={{ whiteSpace: "pre-wrap" }}>{event.description}</p>}

      {err && <div style={{ color: "crimson" }}>{err}</div>}

      <div>
        <h3>Slots</h3>
        {sortedSlots.length === 0 ? (
          <div>No slots yet.</div>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {sortedSlots.map((s) => {
              const full = s.current_count >= s.capacity;
              const past = isPast(s.end_time);
              const disabled = !isAuthed || role === "admin" || role === "organizer" || past;
              const canSignup = isAuthed && role === "participant" && !past;

              return (
                <div key={s.id} style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
                  <div style={{ fontWeight: 600 }}>
                    {new Date(s.start_time).toLocaleString()} → {new Date(s.end_time).toLocaleString()}
                  </div>
                  <div style={{ opacity: 0.8, fontSize: 13 }}>
                    Capacity: {s.current_count}/{s.capacity} {full ? "(Full → waitlist if you signup)" : ""}
                    {past ? " • Past slot" : ""}
                  </div>

                  {!isAuthed && <div style={{ marginTop: 8, opacity: 0.8 }}>Login to sign up.</div>}

                  {canSignup && (
                    <button
                      style={{ marginTop: 8 }}
                      disabled={busySlot === s.id}
                      onClick={() => signup(s.id)}
                    >
                      {busySlot === s.id ? "Submitting…" : "Sign up"}
                    </button>
                  )}

                  {isAuthed && (role === "admin" || role === "organizer") && (
                    <div style={{ marginTop: 8, opacity: 0.8, fontSize: 13 }}>
                      (Organizer/Admin view: signup actions are intended for participants.)
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div style={{ opacity: 0.8, fontSize: 13 }}>
        Note: event custom questions are currently organizer/admin-only in your backend, so the participant UI can’t display them yet.
      </div>
    </div>
  );
}
