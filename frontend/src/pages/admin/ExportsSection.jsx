// src/pages/admin/ExportsSection.jsx
import React, { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import api from "../../lib/api";
import { Card, Button, Skeleton, EmptyState } from "../../components/ui";
import DatePresetPicker from "../../components/admin/DatePresetPicker";
import { currentQuarter } from "../../lib/quarter";
import { useAdminPageTitle } from "./AdminLayout";

function toParams(dateState) {
  const params = {};
  if (dateState?.from) params.from_date = dateState.from;
  if (dateState?.to) params.to_date = dateState.to;
  return params;
}

function AnalyticsPanel({
  title,
  explainer,
  fetchFn,
  csvFn,
  queryKey,
  columns,
  renderRow,
}) {
  const { start: qStart, end: qEnd } = currentQuarter();
  const [dateState, setDateState] = useState({
    preset: "quarter",
    from: qStart.toISOString(),
    to: qEnd.toISOString(),
  });
  const params = toParams(dateState);
  const q = useQuery({
    queryKey: [queryKey, params],
    queryFn: () => fetchFn(params),
  });

  const rows = Array.isArray(q.data) ? q.data : q.data?.rows || [];

  return (
    <Card>
      <h2 className="text-xl font-semibold">{title}</h2>
      <p className="text-[var(--color-fg-muted)] mt-1">{explainer}</p>
      <div className="mt-3">
        <DatePresetPicker
          value={dateState}
          onChange={setDateState}
          presets={["quarter", "last-quarter", "last-12-months", "custom"]}
        />
      </div>
      <div className="mt-3 flex justify-end">
        <Button
          aria-label={`Download CSV for ${title}`}
          onClick={() => csvFn(params)}
        >
          Download CSV
        </Button>
      </div>
      <div className="mt-4 overflow-x-auto">
        {q.isPending ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-8" />
            ))}
          </div>
        ) : q.error ? (
          <EmptyState title="Couldn't load data" body={q.error.message} />
        ) : rows.length === 0 ? (
          <p className="text-[var(--color-fg-muted)]">No data in this range.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--color-border)] text-left">
                {columns.map((c) => (
                  <th key={c} className="py-2 pr-3 font-medium">
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {rows.map((r, i) => (
                <tr key={i}>{renderRow(r)}</tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  );
}

export default function ExportsSection() {
  useAdminPageTitle("Exports");
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Exports</h1>
        <p className="text-[var(--color-fg-muted)]">
          Download CSV reports for volunteer hours and attendance. All exports
          are generated live — no stale data.
        </p>
      </div>

      <AnalyticsPanel
        title="Volunteer hours"
        explainer="Shows how many hours each volunteer has put in. Download the CSV for UCSB grant reports."
        fetchFn={(p) => api.admin.analytics.volunteerHours(p)}
        csvFn={(p) => api.admin.analytics.volunteerHoursCsv(p)}
        queryKey="volunteerHours"
        columns={["Volunteer", "Hours"]}
        renderRow={(r) => (
          <>
            <td className="py-2 pr-3">{r.name || r.email}</td>
            <td className="py-2 pr-3">{r.hours}</td>
          </>
        )}
      />

      <AnalyticsPanel
        title="Attendance rates"
        explainer="Shows what share of people who signed up actually showed up. Low rates may mean we need better reminders."
        fetchFn={(p) => api.admin.analytics.attendanceRates(p)}
        csvFn={(p) => api.admin.analytics.attendanceRatesCsv(p)}
        queryKey="attendanceRates"
        columns={["Event", "Registered", "Attended", "Rate"]}
        renderRow={(r) => (
          <>
            <td className="py-2 pr-3">{r.event_title || r.name}</td>
            <td className="py-2 pr-3">{r.registered ?? r.confirmed}</td>
            <td className="py-2 pr-3">{r.attended}</td>
            <td className="py-2 pr-3">
              {typeof r.rate === "number" ? `${Math.round(r.rate * 100)}%` : "--"}
            </td>
          </>
        )}
      />

      <AnalyticsPanel
        title="No-show rates"
        explainer="Shows how often people sign up but don't show up. Track this over quarters to spot trends."
        fetchFn={(p) => api.admin.analytics.noShowRates(p)}
        csvFn={(p) => api.admin.analytics.noShowRatesCsv(p)}
        queryKey="noShowRates"
        columns={["Event", "Registered", "No Shows", "Rate"]}
        renderRow={(r) => (
          <>
            <td className="py-2 pr-3">{r.event_title || r.name}</td>
            <td className="py-2 pr-3">{r.registered ?? r.confirmed}</td>
            <td className="py-2 pr-3">{r.no_shows ?? r.count}</td>
            <td className="py-2 pr-3">
              {typeof r.rate === "number" ? `${Math.round(r.rate * 100)}%` : "--"}
            </td>
          </>
        )}
      />
    </div>
  );
}
