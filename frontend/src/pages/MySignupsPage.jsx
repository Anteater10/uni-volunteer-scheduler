import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";
import { formatApiDateTimeLocal, toEpochMs } from "../lib/datetime";

export default function MySignupsPage() {
  const qc = useQueryClient();
  const [err, setErr] = useState("");

  const signupsQ = useQuery({
    queryKey: ["mySignups"],
    queryFn: api.signups.my,
  });

  const signups = signupsQ.data || [];

  const sorted = useMemo(() => {
    return [...signups].sort((a, b) => toEpochMs(b.timestamp) - toEpochMs(a.timestamp));
  }, [signups]);

  const { upcoming, past } = useMemo(() => {
    const now = Date.now();
    const groups = { upcoming: [], past: [] };

    sorted.forEach((signup) => {
      const slotEnd = signup.slot_end_time ? toEpochMs(signup.slot_end_time) : null;
      if (slotEnd !== null && slotEnd < now) {
        groups.past.push(signup);
      } else {
        groups.upcoming.push(signup);
      }
    });

    return groups;
  }, [sorted]);

  async function cancel(signupId) {
    setErr("");
    try {
      await api.signups.cancel(signupId);
      await qc.invalidateQueries({ queryKey: ["mySignups"] });
    } catch (e) {
      setErr(e.message || "Cancel failed");
    }
  }

  async function downloadIcs(signupId) {
    setErr("");
    try {
      await downloadBlob(`/signups/${signupId}/ics`, `signup_${signupId}.ics`, { auth: true });
    } catch (e) {
      setErr(e.message || "Download failed");
    }
  }

  if (signupsQ.isLoading) return <div>Loading your signups…</div>;
  if (signupsQ.error) return <div style={{ color: "crimson" }}>Failed: {signupsQ.error.message}</div>;

  function renderSignupCard(s) {
    const timeLabel = s.slot_start_time && s.slot_end_time
      ? `${formatApiDateTimeLocal(s.slot_start_time)} - ${formatApiDateTimeLocal(s.slot_end_time)}`
      : "Time unavailable";

    return (
      <div key={s.id} style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
        <div style={{ fontWeight: 700 }}>{s.event_title || "Volunteer event"}</div>
        <div style={{ opacity: 0.9, fontSize: 14 }}>
          Status: {s.status}
          {s.status === "waitlisted" && s.waitlist_position ? ` (position #${s.waitlist_position})` : ""}
        </div>
        <div style={{ opacity: 0.8, fontSize: 13 }}>{timeLabel}</div>
        <div style={{ opacity: 0.8, fontSize: 13 }}>
          {s.event_location || "Location TBD"}{s.timezone_label ? ` (${s.timezone_label})` : ""}
        </div>
        <div style={{ opacity: 0.7, fontSize: 12 }}>Signup created: {formatApiDateTimeLocal(s.timestamp)}</div>

        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button onClick={() => downloadIcs(s.id)}>Download .ics</button>
          {s.status !== "cancelled" && (
            <button onClick={() => cancel(s.id)}>Cancel</button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div>
      <h2>My Signups</h2>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}

      {sorted.length === 0 ? (
        <div>No signups yet.</div>
      ) : (
        <div style={{ display: "grid", gap: 18 }}>
          <section>
            <h3 style={{ marginBottom: 8 }}>Upcoming</h3>
            {upcoming.length === 0 ? (
              <div style={{ opacity: 0.8 }}>No upcoming signups.</div>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {upcoming.map((s) => renderSignupCard(s))}
              </div>
            )}
          </section>

          <section>
            <h3 style={{ marginBottom: 8 }}>Past</h3>
            {past.length === 0 ? (
              <div style={{ opacity: 0.8 }}>No past signups.</div>
            ) : (
              <div style={{ display: "grid", gap: 10 }}>
                {past.map((s) => renderSignupCard(s))}
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
