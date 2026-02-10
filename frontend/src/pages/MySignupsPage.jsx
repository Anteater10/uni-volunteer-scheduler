import React, { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, downloadBlob } from "../lib/api";

export default function MySignupsPage() {
  const qc = useQueryClient();
  const [err, setErr] = useState("");

  const signupsQ = useQuery({
    queryKey: ["mySignups"],
    queryFn: api.signups.my,
  });

  const signups = signupsQ.data || [];

  const sorted = useMemo(() => {
    return [...signups].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
  }, [signups]);

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

  return (
    <div>
      <h2>My Signups</h2>
      {err && <div style={{ color: "crimson", marginBottom: 8 }}>{err}</div>}

      {sorted.length === 0 ? (
        <div>No signups yet.</div>
      ) : (
        <div style={{ display: "grid", gap: 10 }}>
          {sorted.map((s) => (
            <div key={s.id} style={{ padding: 12, border: "1px solid #3333", borderRadius: 8 }}>
              <div style={{ fontWeight: 700 }}>{s.status}</div>
              <div style={{ opacity: 0.8, fontSize: 13 }}>Signup created: {new Date(s.timestamp).toLocaleString()}</div>
              <div style={{ opacity: 0.8, fontSize: 13 }}>slot_id: {s.slot_id}</div>

              <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
                <button onClick={() => downloadIcs(s.id)}>Download .ics</button>
                {s.status !== "cancelled" && (
                  <button onClick={() => cancel(s.id)}>Cancel</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginTop: 12, opacity: 0.8, fontSize: 13 }}>
        (Next improvement: enrich each signup with slot time + event title by fetching slot/event details.)
      </div>
    </div>
  );
}
