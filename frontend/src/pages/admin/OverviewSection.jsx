// src/pages/admin/OverviewSection.jsx
//
// Phase 16 Plan 04 Task 1 — D-14..D-29 overview page.
// Consumes the expanded /admin/summary shape and the humanized /admin/audit-logs
// feed. Every string on this page is final admin-facing copy (D-18) and every
// identifier shown is humanized (D-19): zero UUIDs should ever reach the DOM.

import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../../lib/api";
import { Card, Button, Skeleton, EmptyState } from "../../components/ui";
import StatCard from "../../components/admin/StatCard";
import RoleBadge from "../../components/admin/RoleBadge";
import SiteSettingsCard from "../../components/admin/SiteSettingsCard";
import { useAdminPageTitle } from "./AdminLayout";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RTF = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function relativeTime(isoString) {
  if (!isoString) return "";
  const then = new Date(isoString);
  if (Number.isNaN(then.valueOf())) return "";
  const diff = (then.getTime() - Date.now()) / 1000; // seconds
  const abs = Math.abs(diff);
  if (abs < 60) return RTF.format(Math.round(diff), "second");
  if (abs < 3600) return RTF.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return RTF.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 7) return RTF.format(Math.round(diff / 86400), "day");
  return then.toLocaleDateString();
}

function formatClock(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  if (Number.isNaN(d.valueOf())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function trendFrom(delta) {
  if (delta === undefined || delta === null) return null;
  if (delta === 0) return { delta: 0, direction: "flat" };
  return { delta, direction: delta > 0 ? "up" : "down" };
}

const STATUS_BADGE = {
  red: "bg-red-100 text-red-800",
  amber: "bg-amber-100 text-amber-800",
  green: "bg-green-100 text-green-800",
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function OverviewSection() {
  useAdminPageTitle("Overview");

  const summaryQ = useQuery({
    queryKey: ["adminSummary"],
    queryFn: api.admin.summary,
  });

  const activityQ = useQuery({
    queryKey: ["adminRecentActivity", 20],
    queryFn: () => api.admin.auditLogs({ limit: 20 }),
  });

  if (summaryQ.isPending) {
    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
        <Skeleton className="h-20" />
        <Skeleton className="h-40" />
      </div>
    );
  }

  if (summaryQ.error) {
    return (
      <EmptyState
        title="Couldn't load the overview"
        body={summaryQ.error.message || "Something went wrong. Try again."}
        action={<Button onClick={() => summaryQ.refetch()}>Retry</Button>}
      />
    );
  }

  const s = summaryQ.data || {};
  const wow = s.week_over_week || {};
  const qp = s.quarter_progress || { week: 0, of: 11, pct: 0 };
  const attention = Array.isArray(s.fill_rate_attention)
    ? s.fill_rate_attention.slice(0, 20)
    : [];
  const attendancePct = Math.round((s.attendance_rate_quarter || 0) * 100);
  const quarterPct = Math.round((qp.pct || 0) * 100);
  const activityRows = Array.isArray(activityQ.data)
    ? activityQ.data
    : activityQ.data?.items || [];

  return (
    <div className="space-y-6">
      {/* ---------------- 5 headline StatCards ---------------- */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <StatCard
          label="Users"
          value={s.users_total ?? 0}
          explainer={`${s.users_total ?? 0} people can sign into this admin panel.`}
          subline={`This quarter: ${s.users_quarter ?? 0}`}
          trend={trendFrom(wow.users)}
        />
        <StatCard
          label="Events"
          value={s.events_total ?? 0}
          explainer={`${s.events_total ?? 0} scheduled activities students can sign up for.`}
          subline={`This quarter: ${s.events_quarter ?? 0}`}
          trend={trendFrom(wow.events)}
        />
        <StatCard
          label="Slots"
          value={s.slots_total ?? 0}
          explainer={`${s.slots_total ?? 0} time slots available across all events.`}
          subline={`This quarter: ${s.slots_quarter ?? 0}`}
        />
        <StatCard
          label="Signups"
          value={s.signups_total ?? 0}
          explainer={`${s.signups_total ?? 0} students have signed up (all time).`}
          subline={`This quarter: ${s.signups_quarter ?? 0}`}
          trend={trendFrom(wow.signups)}
        />
        <StatCard
          label="Confirmed signups"
          value={s.signups_confirmed_total ?? 0}
          explainer={`${s.signups_confirmed_total ?? 0} confirmed (ready to check in or done).`}
          subline={`This quarter: ${s.signups_confirmed_quarter ?? 0}`}
        />
      </div>

      {/* ---------------- Quarter progress bar ---------------- */}
      <Card>
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium">
            Week {qp.week} of {qp.of}
          </span>
          <span className="text-gray-600">
            {quarterPct}% through the quarter
          </span>
        </div>
        <div className="mt-2 h-2 w-full rounded bg-gray-200">
          <div
            className="h-2 rounded bg-blue-500"
            style={{ width: `${quarterPct}%` }}
          />
        </div>
      </Card>

      {/* ---------------- Hours + attendance headlines ---------------- */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <h3 className="text-sm font-medium text-gray-700">
            Hours this quarter
          </h3>
          <p className="mt-1 text-4xl font-bold text-gray-900">
            {s.volunteer_hours_quarter ?? 0}
          </p>
          <p className="mt-1 text-sm text-gray-600">
            Total volunteer hours logged this quarter.
          </p>
        </Card>
        <Card>
          <h3 className="text-sm font-medium text-gray-700">
            Attendance rate this quarter
          </h3>
          <p className="mt-1 text-4xl font-bold text-gray-900">
            {attendancePct}%
          </p>
          <p className="mt-1 text-sm text-gray-600">
            Share of signups that actually showed up.
          </p>
        </Card>
      </div>

      {/* ---------------- This week ---------------- */}
      <Card>
        <h3 className="text-sm font-medium text-gray-700">This week</h3>
        <p className="mt-1 text-gray-900">
          {s.this_week_events ?? 0} events in the next 7 days,{" "}
          {s.this_week_open_slots ?? 0} open slots total.
        </p>
        <Link
          to="/admin/events"
          className="mt-1 inline-block text-sm text-blue-700 hover:underline"
        >
          View all events →
        </Link>
      </Card>

      {/* ---------------- Fill-rate attention list ---------------- */}
      <Card>
        <h3 className="text-base font-semibold text-gray-900">
          Needs attention
        </h3>
        <p className="mt-1 text-sm text-gray-600">
          Upcoming events and how full they are. Red means nearly empty with
          less than three days to go.
        </p>
        {attention.length === 0 ? (
          <p className="mt-3 text-sm text-gray-500">
            No upcoming events need attention right now.
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-gray-200">
            {attention.map((ev) => (
              <li
                key={ev.event_id}
                className="flex items-center justify-between py-2"
              >
                <Link
                  to={`/admin/events/${ev.event_id}`}
                  className="hover:underline"
                >
                  <span className="font-medium text-gray-900">{ev.title}</span>
                  <span className="ml-2 text-sm text-gray-500">
                    {ev.start_at
                      ? new Date(ev.start_at).toLocaleDateString()
                      : ""}
                  </span>
                </Link>
                <span
                  className={`rounded-full px-2 py-1 text-xs font-medium ${
                    STATUS_BADGE[ev.status] || STATUS_BADGE.green
                  }`}
                >
                  {ev.filled}/{ev.capacity}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* ---------------- Recent Activity (20 humanized rows) ---------------- */}
      <Card>
        <h3 className="text-base font-semibold text-gray-900">
          Recent activity
        </h3>
        <p className="mt-1 text-sm text-gray-600">
          The last 20 important changes to the system.
        </p>
        {activityQ.isPending ? (
          <div className="mt-3 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} className="h-8" />
            ))}
          </div>
        ) : activityQ.error ? (
          <p className="mt-3 text-sm text-gray-500">
            Could not load recent activity.
          </p>
        ) : activityRows.length === 0 ? (
          <p className="mt-3 text-sm text-gray-500">Nothing yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-gray-200">
            {activityRows.slice(0, 20).map((log) => (
              <li
                key={log.id}
                className="flex items-start justify-between gap-3 py-2"
              >
                <div className="min-w-0">
                  <span className="font-medium text-gray-900">
                    {log.actor_label}
                  </span>{" "}
                  <RoleBadge role={log.actor_role} />{" "}
                  <span className="text-gray-700">{log.action_label}</span>
                  {log.entity_label ? (
                    <span className="text-gray-500"> — {log.entity_label}</span>
                  ) : null}
                </div>
                <span
                  className="whitespace-nowrap text-xs text-gray-500"
                  title={log.timestamp}
                >
                  {relativeTime(log.timestamp)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {/* Phase 29 (HIDE-01) — Site settings toggle (admin-only; card handles role gating implicitly via the endpoint's admin require_role). */}
      <SiteSettingsCard />

      {/* ---------------- Last updated footer ---------------- */}
      <p className="text-right text-xs text-gray-500">
        Last updated: {formatClock(s.last_updated)}
      </p>
    </div>
  );
}
