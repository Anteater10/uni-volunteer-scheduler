// src/pages/admin/ExportsSection.jsx
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api, { downloadBlob } from "../../lib/api";
import {
  Card,
  Button,
  Input,
  Label,
  Skeleton,
  EmptyState,
} from "../../components/ui";

function SortableTable({ columns, data, emptyMessage }) {
  const [sortCol, setSortCol] = useState(null);
  const [sortDir, setSortDir] = useState("asc");

  function handleSort(key) {
    if (sortCol === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortCol(key);
      setSortDir("asc");
    }
  }

  const sorted = [...(data || [])].sort((a, b) => {
    if (!sortCol) return 0;
    const av = a[sortCol];
    const bv = b[sortCol];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === "number" ? av - bv : String(av).localeCompare(String(bv));
    return sortDir === "asc" ? cmp : -cmp;
  });

  if (!data || data.length === 0) {
    return (
      <EmptyState
        title={emptyMessage || "No data"}
        body="Try adjusting your date range."
      />
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] text-left">
            {columns.map((col) => (
              <th
                key={col.key}
                className="py-2 pr-3 font-medium cursor-pointer select-none hover:text-[var(--color-fg)]"
                onClick={() => handleSort(col.key)}
              >
                {col.label}
                {sortCol === col.key ? (sortDir === "asc" ? " ^" : " v") : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border)]">
          {sorted.map((row, i) => (
            <tr key={i}>
              {columns.map((col) => (
                <td key={col.key} className="py-2 pr-3 text-[var(--color-fg-muted)]">
                  {col.format ? col.format(row[col.key]) : String(row[col.key] ?? "--")}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalyticsPanel({ title, queryKey, queryFn, columns, csvFn, emptyMessage }) {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [enabled, setEnabled] = useState(false);

  function buildParams() {
    const p = {};
    if (from) {
      const d = new Date(from);
      if (!Number.isNaN(d.valueOf())) p.from_date = d.toISOString();
    }
    if (to) {
      const d = new Date(to);
      if (!Number.isNaN(d.valueOf())) p.to_date = d.toISOString();
    }
    return p;
  }

  const q = useQuery({
    queryKey: [queryKey, from, to],
    queryFn: () => queryFn(buildParams()),
    enabled,
  });

  return (
    <Card>
      <h3 className="font-semibold mb-3">{title}</h3>
      <div className="flex flex-wrap gap-3 items-end mb-3">
        <div>
          <Label htmlFor={`${queryKey}-from`}>From</Label>
          <Input
            id={`${queryKey}-from`}
            type="datetime-local"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </div>
        <div>
          <Label htmlFor={`${queryKey}-to`}>To</Label>
          <Input
            id={`${queryKey}-to`}
            type="datetime-local"
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </div>
        <Button
          onClick={() => {
            setEnabled(true);
            if (q.data !== undefined) q.refetch();
          }}
        >
          Load
        </Button>
        {csvFn && (
          <Button variant="secondary" onClick={() => csvFn(buildParams())}>
            Export CSV
          </Button>
        )}
      </div>

      {q.isPending && enabled ? (
        <div className="space-y-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-8" />
          ))}
        </div>
      ) : q.error ? (
        <EmptyState
          title="Error loading data"
          body={q.error.message}
          action={<Button onClick={() => q.refetch()}>Retry</Button>}
        />
      ) : q.data ? (
        <SortableTable columns={columns} data={q.data} emptyMessage={emptyMessage} />
      ) : null}
    </Card>
  );
}

const pct = (v) => `${(v * 100).toFixed(1)}%`;

export default function ExportsSection() {
  return (
    <div className="space-y-4">
      <AnalyticsPanel
        title="Volunteer Hours"
        queryKey="analyticsVolunteerHours"
        queryFn={(p) => api.admin.analytics.volunteerHours(p)}
        columns={[
          { key: "name", label: "Name" },
          { key: "hours", label: "Hours" },
          { key: "events", label: "Events" },
        ]}
        csvFn={(p) =>
          downloadBlob("/admin/analytics/volunteer-hours.csv", "volunteer-hours.csv", {
            params: p,
          })
        }
        emptyMessage="No volunteer hours recorded"
      />

      <AnalyticsPanel
        title="Attendance Rates"
        queryKey="analyticsAttendance"
        queryFn={(p) => api.admin.analytics.attendanceRates(p)}
        columns={[
          { key: "name", label: "Event" },
          { key: "confirmed", label: "Confirmed" },
          { key: "attended", label: "Attended" },
          { key: "no_show", label: "No-Show" },
          { key: "rate", label: "Rate (%)", format: pct },
        ]}
        emptyMessage="No attendance data"
      />

      <AnalyticsPanel
        title="No-Show Rates"
        queryKey="analyticsNoShow"
        queryFn={(p) => api.admin.analytics.noShowRates(p)}
        columns={[
          { key: "name", label: "Name" },
          { key: "rate", label: "Rate (%)", format: pct },
          { key: "count", label: "Count" },
        ]}
        emptyMessage="No no-show data"
      />
    </div>
  );
}
