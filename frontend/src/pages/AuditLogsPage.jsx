// src/pages/AuditLogsPage.jsx
import React, { useEffect, useState } from "react";
import api from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  Input,
  Label,
  FieldError,
  EmptyState,
  Skeleton,
} from "../components/ui";

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
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="Audit Logs" />

      <Card>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
          className="space-y-3"
        >
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-q">Search</Label>
              <Input
                id="al-q"
                value={filters.q}
                onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))}
                /* TODO(copy) */
                placeholder="Search text..."
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-action">Action</Label>
              <Input
                id="al-action"
                value={filters.action}
                onChange={(e) => setFilters((p) => ({ ...p, action: e.target.value }))}
                /* TODO(copy) */
                placeholder="Action"
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-etype">Entity type</Label>
              <Input
                id="al-etype"
                value={filters.entity_type}
                onChange={(e) => setFilters((p) => ({ ...p, entity_type: e.target.value }))}
                /* TODO(copy) */
                placeholder="Entity type"
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-eid">Entity ID</Label>
              <Input
                id="al-eid"
                value={filters.entity_id}
                onChange={(e) => setFilters((p) => ({ ...p, entity_id: e.target.value }))}
                /* TODO(copy) */
                placeholder="Entity ID"
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-start">Start time</Label>
              <Input
                id="al-start"
                type="datetime-local"
                value={filters.start}
                onChange={(e) => setFilters((p) => ({ ...p, start: e.target.value }))}
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-end">End time</Label>
              <Input
                id="al-end"
                type="datetime-local"
                value={filters.end}
                onChange={(e) => setFilters((p) => ({ ...p, end: e.target.value }))}
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={loading}>
              {/* TODO(copy) */}
              Apply
            </Button>
            <Button type="button" variant="ghost" onClick={() => load()} disabled={loading}>
              {/* TODO(copy) */}
              Refresh
            </Button>
          </div>
        </form>
      </Card>

      <FieldError>{err}</FieldError>

      {loading ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : logs.length === 0 ? (
        <EmptyState
          /* TODO(copy) */
          title="No audit logs"
          /* TODO(copy) */
          body="No logs match these filters."
        />
      ) : (
        <div className="space-y-3">
          {logs.map((l) => (
            <Card key={l.id}>
              <div className="flex flex-col gap-1">
                <div className="flex flex-wrap items-baseline gap-2">
                  <span className="font-semibold">{l.action}</span>
                  <span className="text-xs text-[var(--color-fg-muted)]">
                    {formatTs(l.timestamp)}
                  </span>
                </div>
                <p className="text-sm text-[var(--color-fg-muted)]">
                  {/* TODO(copy) */}
                  {l.entity_type} {l.entity_id ? `#${l.entity_id}` : ""}
                  {l.actor_id ? ` by actor ${l.actor_id}` : ""}
                </p>
                {l.extra && (
                  <pre className="text-xs mt-1 whitespace-pre-wrap text-[var(--color-fg-muted)]">
                    {JSON.stringify(l.extra, null, 2)}
                  </pre>
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
