// src/pages/AuditLogsPage.jsx
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api, { downloadBlob } from "../lib/api";
import {
  PageHeader,
  Card,
  Button,
  Input,
  Label,
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

const PAGE_SIZE_OPTIONS = [25, 50, 100];

export default function AuditLogsPage() {
  const [filters, setFilters] = useState({
    q: "",
    kind: "",
    user_id: "",
    start: "",
    end: "",
  });
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  // Build query params from filters
  function buildParams() {
    const params = { page, page_size: pageSize };
    if (filters.q) params.q = filters.q;
    if (filters.kind) params.kind = filters.kind;
    if (filters.user_id) params.user_id = filters.user_id;
    if (filters.start) {
      const d = new Date(filters.start);
      if (!Number.isNaN(d.valueOf())) params.from_date = d.toISOString();
    }
    if (filters.end) {
      const d = new Date(filters.end);
      if (!Number.isNaN(d.valueOf())) params.to_date = d.toISOString();
    }
    return params;
  }

  const q = useQuery({
    queryKey: ["adminAuditLogs", filters, page, pageSize],
    queryFn: () => api.admin.auditLogs(buildParams()),
  });

  const data = q.data || {};
  const logs = data.items || [];
  const total = data.total || 0;
  const totalPages = data.pages || 0;

  function handleFilter(e) {
    e.preventDefault();
    setPage(1);
    q.refetch();
  }

  function handleExportCsv() {
    const params = {};
    if (filters.q) params.q = filters.q;
    if (filters.kind) params.kind = filters.kind;
    if (filters.user_id) params.user_id = filters.user_id;
    if (filters.start) {
      const d = new Date(filters.start);
      if (!Number.isNaN(d.valueOf())) params.from_date = d.toISOString();
    }
    if (filters.end) {
      const d = new Date(filters.end);
      if (!Number.isNaN(d.valueOf())) params.to_date = d.toISOString();
    }
    downloadBlob("/admin/audit-logs.csv", "audit-logs.csv", { params });
  }

  return (
    <div className="space-y-4">
      {/* Filters */}
      <Card>
        <form onSubmit={handleFilter} className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-q">Keyword Search</Label>
              <Input
                id="al-q"
                value={filters.q}
                onChange={(e) => setFilters((p) => ({ ...p, q: e.target.value }))}
                placeholder="Search text..."
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-kind">Action Kind</Label>
              <Input
                id="al-kind"
                value={filters.kind}
                onChange={(e) => setFilters((p) => ({ ...p, kind: e.target.value }))}
                placeholder="Comma-separated actions"
              />
            </div>
            <div>
              {/* TODO(copy) */}
              <Label htmlFor="al-user">User ID</Label>
              <Input
                id="al-user"
                value={filters.user_id}
                onChange={(e) => setFilters((p) => ({ ...p, user_id: e.target.value }))}
                placeholder="User ID"
              />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="al-start">From</Label>
                <Input
                  id="al-start"
                  type="datetime-local"
                  value={filters.start}
                  onChange={(e) => setFilters((p) => ({ ...p, start: e.target.value }))}
                />
              </div>
              <div>
                {/* TODO(copy) */}
                <Label htmlFor="al-end">To</Label>
                <Input
                  id="al-end"
                  type="datetime-local"
                  value={filters.end}
                  onChange={(e) => setFilters((p) => ({ ...p, end: e.target.value }))}
                />
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={q.isFetching}>
              {/* TODO(copy) */}
              Apply
            </Button>
            <Button type="button" variant="ghost" onClick={() => q.refetch()} disabled={q.isFetching}>
              {/* TODO(copy) */}
              Refresh
            </Button>
            <Button type="button" variant="secondary" onClick={handleExportCsv}>
              {/* TODO(copy) */}
              Export CSV
            </Button>
          </div>
        </form>
      </Card>

      {/* Total count */}
      {!q.isPending && (
        <p className="text-sm text-[var(--color-fg-muted)]">
          {/* TODO(copy) */}
          {total} log{total !== 1 ? "s" : ""} found
        </p>
      )}

      {/* Results */}
      {q.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : q.error ? (
        <EmptyState
          title="Couldn't load audit logs"
          body={q.error.message}
          action={<Button onClick={() => q.refetch()}>Retry</Button>}
        />
      ) : logs.length === 0 ? (
        <EmptyState
          title="No audit logs"
          body="No logs match these filters."
        />
      ) : (
        <>
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left">
                  <th className="py-2 pr-3 font-medium">Timestamp</th>
                  <th className="py-2 pr-3 font-medium">Action</th>
                  <th className="py-2 pr-3 font-medium">Entity</th>
                  <th className="py-2 pr-3 font-medium">Actor</th>
                  <th className="py-2 font-medium">Extra</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {logs.map((l) => (
                  <tr key={l.id}>
                    <td className="py-2 pr-3 whitespace-nowrap text-[var(--color-fg-muted)]">
                      {formatTs(l.timestamp)}
                    </td>
                    <td className="py-2 pr-3 font-medium">{l.action}</td>
                    <td className="py-2 pr-3 text-[var(--color-fg-muted)]">
                      {l.entity_type}{l.entity_id ? ` #${l.entity_id}` : ""}
                    </td>
                    <td className="py-2 pr-3 text-[var(--color-fg-muted)] text-xs font-mono">
                      {l.actor_id ? String(l.actor_id).slice(0, 8) : "--"}
                    </td>
                    <td className="py-2 text-xs text-[var(--color-fg-muted)] max-w-xs truncate">
                      {l.extra ? JSON.stringify(l.extra) : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
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
                    {l.entity_type} {l.entity_id ? `#${l.entity_id}` : ""}
                    {l.actor_id ? ` by ${String(l.actor_id).slice(0, 8)}` : ""}
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
        </>
      )}

      {/* Pagination controls */}
      {totalPages > 0 && (
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <span className="text-sm text-[var(--color-fg-muted)]">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="al-ps" className="text-xs">Per page</Label>
            <select
              id="al-ps"
              value={pageSize}
              onChange={(e) => {
                setPageSize(Number(e.target.value));
                setPage(1);
              }}
              className="min-h-9 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-2 text-sm"
            >
              {PAGE_SIZE_OPTIONS.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
