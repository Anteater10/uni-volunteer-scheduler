// src/pages/AuditLogsPage.jsx
//
// Phase 16 Plan 04 Task 2 — polished audit log page.
//
// Implements D-03..D-07 and D-30..D-34:
//  - 5-column table (When / Who / What / Target / Details) of humanized rows
//  - Inline filter bar: kind dropdown (ACTION_LABELS mirror), actor dropdown
//    (from /users/), DatePresetPicker, free-text search (debounced)
//  - All filter state + page mirrored via useSearchParams (deep-linkable)
//  - Row click / Details button → SideDrawer with raw JSON + Copy button
//  - Numbered Pagination primitive (25 per page)
//  - "Export filtered view (CSV)" button → downloadBlob with current params
//  - One-sentence explainer at the top; zero UUIDs in rendered UI (D-19)
//
// File location debt (file belongs under src/pages/admin/) is intentionally
// deferred to the Plan 07 audit doc — see 16-CONTEXT.md.

import React, { useState, useMemo, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { downloadBlob } from "../lib/api";
import { Button, Input, EmptyState, Skeleton } from "../components/ui";
import SideDrawer from "../components/admin/SideDrawer";
import DatePresetPicker from "../components/admin/DatePresetPicker";
import Pagination from "../components/admin/Pagination";
import RoleBadge from "../components/admin/RoleBadge";
import { useAdminPageTitle } from "./admin/AdminLayout";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PAGE_SIZE = 25;

// Mirror of backend ACTION_LABELS (backend/app/services/audit_log_humanize.py).
// Kept in sync manually — if you add a new audit action, add it here too.
const ACTION_LABEL_OPTIONS = [
  { value: "signup_cancelled", label: "Cancelled a signup" },
  { value: "signup_promote", label: "Promoted from waitlist" },
  { value: "signup_move", label: "Moved a signup to a different slot" },
  { value: "signup_resend", label: "Resent a confirmation email" },
  { value: "signup_ics_export", label: "Exported a signup calendar file" },
  { value: "admin_signup_cancel", label: "Admin cancelled a signup" },
  { value: "user_invite", label: "Invited a new user" },
  { value: "user_deactivate", label: "Deactivated a user" },
  { value: "user_reactivate", label: "Reactivated a user" },
  { value: "user_update", label: "Updated a user" },
  { value: "user_login", label: "Logged in" },
  { value: "ccpa_export", label: "Exported a user's personal data (CCPA)" },
  { value: "ccpa_delete", label: "Deleted a user's personal data (CCPA)" },
  { value: "event_create", label: "Created an event" },
  { value: "event_update", label: "Updated an event" },
  { value: "event_notify", label: "Sent a notification to event attendees" },
  { value: "template_create", label: "Created a module template" },
  { value: "template_update", label: "Updated a module template" },
  { value: "template_delete", label: "Archived a module template" },
  { value: "import_upload", label: "Uploaded a CSV import" },
  { value: "import_commit", label: "Committed a CSV import" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RTF = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function relativeTime(isoString) {
  if (!isoString) return "";
  const then = new Date(isoString);
  if (Number.isNaN(then.valueOf())) return "";
  const diff = (then.getTime() - Date.now()) / 1000;
  const abs = Math.abs(diff);
  if (abs < 60) return RTF.format(Math.round(diff), "second");
  if (abs < 3600) return RTF.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return RTF.format(Math.round(diff / 3600), "hour");
  if (abs < 86400 * 7) return RTF.format(Math.round(diff / 86400), "day");
  return then.toLocaleDateString();
}

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AuditLogsPage() {
  useAdminPageTitle("Audit Logs");

  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);
  const q = searchParams.get("q") || "";
  const kind = searchParams.get("kind") || "";
  const actorId = searchParams.get("actor_id") || "";
  const fromDate = searchParams.get("from_date") || "";
  const toDate = searchParams.get("to_date") || "";
  const preset = searchParams.get("preset") || "30d";

  // Local echo of the search input so typing feels instant; debounced value
  // goes into the URL / query params.
  const [searchDraft, setSearchDraft] = useState(q);
  const debouncedSearch = useDebounced(searchDraft, 300);

  const [selected, setSelected] = useState(null);

  // ---- URL helpers ----
  function updateParam(name, value) {
    const next = new URLSearchParams(searchParams);
    if (value === "" || value === null || value === undefined) next.delete(name);
    else next.set(name, value);
    next.set("page", "1");
    setSearchParams(next, { replace: true });
  }

  function setPage(p) {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(p));
    setSearchParams(next);
  }

  function onPresetChange({ preset: nextPreset, from, to }) {
    const next = new URLSearchParams(searchParams);
    next.set("preset", nextPreset);
    if (from) next.set("from_date", from);
    else next.delete("from_date");
    if (to) next.set("to_date", to);
    else next.delete("to_date");
    next.set("page", "1");
    setSearchParams(next, { replace: true });
  }

  // Push debounced search text into the URL. Guarded so it only fires when
  // the debounced value actually differs from the URL value.
  useEffect(() => {
    if (debouncedSearch === q) return;
    updateParam("q", debouncedSearch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch]);

  // Build query params for the backend. Only non-empty values flow through.
  const params = useMemo(() => {
    const p = { page, page_size: PAGE_SIZE };
    if (q) p.q = q;
    if (kind) p.kind = kind;
    if (actorId) p.actor_id = actorId;
    if (fromDate) p.from_date = fromDate;
    if (toDate) p.to_date = toDate;
    return p;
  }, [page, q, kind, actorId, fromDate, toDate]);

  const logsQ = useQuery({
    queryKey: ["auditLogs", params],
    queryFn: () => api.admin.auditLogs(params),
    keepPreviousData: true,
  });

  const actorsQ = useQuery({
    queryKey: ["adminUsersForAuditFilter"],
    queryFn: () => api.admin.users.list({ include_inactive: true }),
  });

  function handleExport() {
    downloadBlob("/admin/audit-logs.csv", "audit-logs.csv", { params });
  }

  function handleCopyPayload() {
    if (!selected) return;
    try {
      navigator.clipboard?.writeText(JSON.stringify(selected, null, 2));
    } catch {
      // Best effort — older browsers / test envs may lack clipboard.
    }
  }

  const rows = logsQ.data?.items || [];
  const total = logsQ.data?.total || 0;
  const totalPages = Math.max(
    1,
    logsQ.data?.pages || Math.ceil(total / PAGE_SIZE) || 1,
  );

  const actors = actorsQ.data?.items || actorsQ.data || [];

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-gray-900">Audit logs</h1>
      <p className="text-gray-600">
        This page shows a history of every important change to the system —
        who did what, when, and to what. Use the filters to narrow down what
        you're looking for.
      </p>

      {/* ---------------- Filter bar ---------------- */}
      <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 p-3">
        <div className="min-w-[16rem]">
          <label
            htmlFor="al-search"
            className="block text-xs font-medium text-gray-600"
          >
            Search
          </label>
          <Input
            id="al-search"
            placeholder="Search audit log text..."
            value={searchDraft}
            onChange={(e) => setSearchDraft(e.target.value)}
          />
        </div>

        <div>
          <label
            htmlFor="al-kind"
            className="block text-xs font-medium text-gray-600"
          >
            Action
          </label>
          <select
            id="al-kind"
            value={kind}
            onChange={(e) => updateParam("kind", e.target.value)}
            className="min-h-9 rounded-md border border-gray-300 bg-white px-2 text-sm"
          >
            <option value="">All actions</option>
            {ACTION_LABEL_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label
            htmlFor="al-actor"
            className="block text-xs font-medium text-gray-600"
          >
            Actor
          </label>
          <select
            id="al-actor"
            value={actorId}
            onChange={(e) => updateParam("actor_id", e.target.value)}
            className="min-h-9 rounded-md border border-gray-300 bg-white px-2 text-sm"
          >
            <option value="">All actors</option>
            {actors.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name || u.email || "Unnamed user"}
              </option>
            ))}
          </select>
        </div>

        <div>
          <div className="mb-1 block text-xs font-medium text-gray-600">
            Date range
          </div>
          <DatePresetPicker
            value={{ preset, from: fromDate, to: toDate }}
            onChange={onPresetChange}
            presets={["24h", "7d", "30d", "quarter", "custom"]}
          />
        </div>

        <div className="ml-auto">
          <Button type="button" onClick={handleExport}>
            Export filtered view (CSV)
          </Button>
        </div>
      </div>

      {/* ---------------- Results ---------------- */}
      {logsQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : logsQ.error ? (
        <EmptyState
          title="Couldn't load audit logs"
          body={logsQ.error.message || "Something went wrong. Try again."}
          action={<Button onClick={() => logsQ.refetch()}>Retry</Button>}
        />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No audit logs match these filters"
          body="Try widening the date range or clearing the search box."
        />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left">
                <th className="py-2 pr-3 font-medium text-gray-700">When</th>
                <th className="py-2 pr-3 font-medium text-gray-700">Who</th>
                <th className="py-2 pr-3 font-medium text-gray-700">What</th>
                <th className="py-2 pr-3 font-medium text-gray-700">Target</th>
                <th className="py-2 font-medium text-gray-700">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {rows.map((log) => (
                <tr
                  key={log.id}
                  className="cursor-pointer hover:bg-gray-50"
                  onClick={() => setSelected(log)}
                >
                  <td
                    className="py-2 pr-3 whitespace-nowrap text-gray-500"
                    title={log.timestamp}
                  >
                    {relativeTime(log.timestamp)}
                  </td>
                  <td className="py-2 pr-3">
                    <span className="font-medium text-gray-900">
                      {log.actor_label}
                    </span>{" "}
                    {log.actor_role ? <RoleBadge role={log.actor_role} /> : null}
                  </td>
                  <td className="py-2 pr-3 text-gray-800">{log.action_label}</td>
                  <td className="py-2 pr-3 text-gray-700">
                    {log.entity_label}
                  </td>
                  <td className="py-2">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelected(log);
                      }}
                    >
                      View
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ---------------- Pagination ---------------- */}
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600">
          {total} entr{total === 1 ? "y" : "ies"}
        </p>
        <Pagination page={page} totalPages={totalPages} onChange={setPage} />
      </div>

      {/* ---------------- SideDrawer (raw payload) ---------------- */}
      <SideDrawer
        open={!!selected}
        onClose={() => setSelected(null)}
        title="Audit log entry"
      >
        {selected ? (
          <div className="space-y-3 text-sm">
            <div>
              <strong className="text-gray-700">When:</strong>{" "}
              <span className="text-gray-900">{selected.timestamp}</span>
            </div>
            <div>
              <strong className="text-gray-700">Who:</strong>{" "}
              <span className="text-gray-900">
                {selected.actor_label}
                {selected.actor_role ? ` (${selected.actor_role})` : ""}
              </span>
            </div>
            <div>
              <strong className="text-gray-700">What:</strong>{" "}
              <span className="text-gray-900">{selected.action_label}</span>
            </div>
            <div>
              <strong className="text-gray-700">Target:</strong>{" "}
              <span className="text-gray-900">{selected.entity_label}</span>
            </div>
            <div>
              <strong className="text-gray-700">Raw payload:</strong>
              <pre className="mt-1 max-h-96 overflow-auto rounded bg-gray-50 p-3 text-xs text-gray-800">
                {JSON.stringify(selected, null, 2)}
              </pre>
              <Button
                type="button"
                variant="secondary"
                onClick={handleCopyPayload}
              >
                Copy to clipboard
              </Button>
            </div>
          </div>
        ) : null}
      </SideDrawer>
    </div>
  );
}
