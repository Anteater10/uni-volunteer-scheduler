// src/pages/AuditLogsPage.jsx
import React, { useEffect, useMemo, useState } from "react";
import api from "../lib/api";

function formatTs(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts || "");
  }
}

export default function AuditLogsPage() {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");
  const [query, setQuery] = useState("");

  async function load() {
    setErr("");
    setLoading(true);
    try {
      const data = await api.adminAuditLogs();
      setLogs(data || []);
    } catch (e) {
      setErr(e?.message || "Failed to load audit logs");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return logs;
    return logs.filter((l) => {
      const extra = l.extra ? JSON.stringify(l.extra) : "";
      return (
        (l.action || "").toLowerCase().includes(q) ||
        (l.entity_type || "").toLowerCase().includes(q) ||
        (l.entity_id || "").toLowerCase().includes(q) ||
        (l.actor_id || "").toLowerCase().includes(q) ||
        extra.toLowerCase().includes(q)
      );
    });
  }, [logs, query]);

  return (
    <div style={{ padding: 16, maxWidth: 1200, margin: "0 auto" }}>
      <h1 style={{ marginBottom: 8 }}>Audit Logs (Admin)</h1>
      <p style={{ marginTop: 0, opacity: 0.8 }}>
        Latest entries from <code>/admin/audit_logs</code> (capped on backend).
      </p>

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

      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 12 }}>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search action/entity/actor/extra..."
          style={{ maxWidth: 420, width: "100%" }}
        />
        <button onClick={load} disabled={loading}>
          Refresh
        </button>
      </div>

      {loading ? (
        <div>Loading audit logs…</div>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ textAlign: "left" }}>
                <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Time</th>
                <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Actor</th>
                <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Action</th>
                <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Entity</th>
                <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Entity ID</th>
                <th style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.12)" }}>Extra</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((l) => (
                <tr key={l.id}>
                  <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)", whiteSpace: "nowrap" }}>
                    {formatTs(l.timestamp)}
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <code style={{ fontSize: 12 }}>{l.actor_id || "—"}</code>
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <span style={{ fontWeight: 600 }}>{l.action}</span>
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    {l.entity_type}
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <code style={{ fontSize: 12 }}>{l.entity_id || "—"}</code>
                  </td>
                  <td style={{ padding: 8, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                    <pre
                      style={{
                        margin: 0,
                        maxWidth: 520,
                        overflowX: "auto",
                        fontSize: 12,
                        opacity: 0.9,
                      }}
                    >
                      {l.extra ? JSON.stringify(l.extra, null, 2) : ""}
                    </pre>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 12, opacity: 0.8 }}>
                    No audit logs match this search.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
