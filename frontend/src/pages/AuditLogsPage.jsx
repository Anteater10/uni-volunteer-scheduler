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
  const [filters, setFilters] = useState({
    q: "",
    action: "",
    entity_type: "",
    entity_id: "",
    actor_id: "",
    start: "",
    end: "",
    limit: "200",
  });

  async function load(paramsOverride) {
    setErr("");
    setLoading(true);
    try {
      const params = paramsOverride || filters;
      const payload = {
        q: params.q || undefined,
        action: params.action || undefined,
        entity_type: params.entity_type || undefined,
        entity_id: params.entity_id || undefined,
        actor_id: params.actor_id || undefined,
        limit: params.limit ? Number(params.limit) : undefined,
      };
      if (params.start) {
        const d = new Date(params.start);
        if (!Number.isNaN(d.valueOf())) payload.start = d.toISOString();
      }
      if (params.end) {
        const d = new Date(params.end);
        if (!Number.isNaN(d.valueOf())) payload.end = d.toISOString();
      }

      const data = await api.adminAuditLogs(payload);
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

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load();
        }}
        style={{
          display: "grid",
          gap: 10,
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          marginBottom: 12,
        }}
      >
        <input
          value={filters.q}
          onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))}
          placeholder="Search text…"
        />
        <input
          value={filters.action}
          onChange={(e) => setFilters((p) => ({ ...p, action: e.target.value }))}
          placeholder="Action"
        />
        <input
          value={filters.entity_type}
          onChange={(e) => setFilters((p) => ({ ...p, entity_type: e.target.value }))}
          placeholder="Entity type"
        />
        <input
          value={filters.entity_id}
          onChange={(e) => setFilters((p) => ({ ...p, entity_id: e.target.value }))}
          placeholder="Entity ID"
        />
        <input
          value={filters.actor_id}
          onChange={(e) => setFilters((p) => ({ ...p, actor_id: e.target.value }))}
          placeholder="Actor ID"
        />
        <input
          type="datetime-local"
          value={filters.start}
          onChange={(e) => setFilters((p) => ({ ...p, start: e.target.value }))}
          placeholder="Start time"
        />
        <input
          type="datetime-local"
          value={filters.end}
          onChange={(e) => setFilters((p) => ({ ...p, end: e.target.value }))}
          placeholder="End time"
        />
        <input
          type="number"
          min="1"
          max="2000"
          value={filters.limit}
          onChange={(e) => setFilters((p) => ({ ...p, limit: e.target.value }))}
          placeholder="Limit"
        />
        <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
          <button type="submit" disabled={loading}>
            Apply
          </button>
          <button type="button" onClick={() => load()} disabled={loading}>
            Refresh
          </button>
        </div>
      </form>

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
              {logs.map((l) => (
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
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 12, opacity: 0.8 }}>
                    No audit logs match these filters.
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
