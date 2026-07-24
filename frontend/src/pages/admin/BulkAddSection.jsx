// src/pages/admin/BulkAddSection.jsx
//
// In-app bulk event builder — the module-first, file-free replacement for the
// retired CSV import workflow. Pick one module, add a row per school/date/time,
// and create them all at once. Reusable all quarter: add a few now, come back
// and add more as dates confirm.

import React, { useMemo, useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import api from "../../lib/api";
import {
  Button,
  Card,
  Input,
  Label,
  FieldError,
  EmptyState,
  Skeleton,
} from "../../components/ui";
import { toast } from "../../state/toast";
import { useAdminPageTitle } from "./AdminLayout";

// Known SciTrek partner high schools — offered as suggestions, not enforced.
const KNOWN_SCHOOLS = [
  "San Marcos High School",
  "Dos Pueblos High School",
  "Santa Barbara High School",
  "Goleta Valley Junior High School",
  "Carpinteria High School",
];

function blankRow() {
  return { school: "", date: "", start_time: "", capacity: "", kind: "module" };
}

export default function BulkAddSection() {
  useAdminPageTitle("Add events");

  const [templateSlug, setTemplateSlug] = useState("");
  const [rows, setRows] = useState([blankRow()]);
  // Map of rowIndex -> error message from the last failed submit.
  const [rowErrors, setRowErrors] = useState({});

  const templatesQ = useQuery({
    queryKey: ["adminModuleTemplates"],
    queryFn: () => api.admin.templates.list(),
  });

  // Only active, module-type templates are addable.
  const modules = useMemo(
    () =>
      (templatesQ.data || []).filter(
        (t) => !t.deleted_at && t.type === "module",
      ),
    [templatesQ.data],
  );

  const selected = modules.find((t) => t.slug === templateSlug) || null;
  const capacityPlaceholder = selected ? String(selected.default_capacity) : "";

  const createMut = useMutation({
    mutationFn: () =>
      api.admin.events.bulkCreate(
        templateSlug,
        rows.map((r) => ({
          school: r.school.trim(),
          date: r.date,
          start_time: r.start_time,
          capacity: r.capacity === "" ? null : Number(r.capacity),
          kind: r.kind,
        })),
      ),
    onSuccess: (data) => {
      // Validation problems come back in the body (nothing was created).
      if (Array.isArray(data?.errors) && data.errors.length) {
        const map = {};
        data.errors.forEach((e) => {
          map[e.row] = e.message;
        });
        setRowErrors(map);
        toast.error("Some rows need fixing — see the highlighted rows.");
        return;
      }
      const created = data?.created_count ?? 0;
      const merged = data?.merged_count ?? 0;
      const parts = [];
      if (created) parts.push(`${created} new event${created === 1 ? "" : "s"}`);
      if (merged)
        parts.push(`${merged} added to existing event${merged === 1 ? "" : "s"}`);
      toast.success(
        parts.length ? `Created ${parts.join(" · ")}.` : "Events created.",
      );
      // Clear for the next batch, keeping the chosen module selected.
      setRows([blankRow()]);
      setRowErrors({});
    },
    onError: (err) => {
      // Reserved for hard failures (unknown module 404, server error).
      toast.error(err?.message || "Couldn't create events.");
    },
  });

  function updateRow(i, patch) {
    setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, ...patch } : r)));
    setRowErrors((prev) => {
      if (!(i in prev)) return prev;
      const next = { ...prev };
      delete next[i];
      return next;
    });
  }

  function addRow() {
    setRows((prev) => [...prev, blankRow()]);
  }

  function duplicateRow(i) {
    setRows((prev) => {
      const copy = { ...prev[i] };
      const next = [...prev];
      next.splice(i + 1, 0, copy);
      return next;
    });
  }

  function removeRow(i) {
    setRows((prev) => (prev.length === 1 ? [blankRow()] : prev.filter((_, idx) => idx !== i)));
    setRowErrors({});
  }

  const hasAnyRowData = rows.some(
    (r) => r.school.trim() || r.date || r.start_time,
  );
  const canSubmit =
    !!templateSlug && hasAnyRowData && !createMut.isPending;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-4xl font-bold tracking-tight">Add events</h1>
        <p className="text-lg text-[var(--color-fg-muted)] mt-2 max-w-3xl">
          Pick a module, then add a row for each session — mark it a{" "}
          <strong>module session</strong> or an <strong>orientation</strong>.
          Sessions at the same school in the same week become one event; a
          different week is its own event. Click <strong>Create events</strong>{" "}
          and they're scheduled instantly — no file, no upload. Come back any
          time to add more as dates confirm.
        </p>
      </div>

      {/* Step 1 — pick a module */}
      <Card className="p-5 space-y-3">
        <Label htmlFor="module-picker">1. Which module?</Label>
        {templatesQ.isPending ? (
          <Skeleton className="h-11 w-full max-w-md" />
        ) : modules.length === 0 ? (
          <EmptyState
            title="No modules yet"
            body="Create a module in Templates first, then come back to schedule it."
          />
        ) : (
          <select
            id="module-picker"
            value={templateSlug}
            onChange={(e) => setTemplateSlug(e.target.value)}
            className="w-full max-w-md rounded-lg border border-gray-300 px-3 py-2.5 text-base bg-white"
          >
            <option value="">Select a module…</option>
            {modules.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.name}
              </option>
            ))}
          </select>
        )}
        {selected && (
          <p className="text-sm text-gray-500">
            {selected.duration_minutes} min per session · default capacity{" "}
            {selected.default_capacity} students. Adjust capacity per row below.
          </p>
        )}
      </Card>

      {/* Step 2 — rows */}
      <Card className="p-5 space-y-4">
        <Label>2. Where and when?</Label>

        <datalist id="known-schools">
          {KNOWN_SCHOOLS.map((s) => (
            <option key={s} value={s} />
          ))}
        </datalist>

        <div className="space-y-3">
          {rows.map((row, i) => (
            <div
              key={i}
              className={`rounded-lg border p-3 ${
                rowErrors[i] ? "border-red-300 bg-red-50" : "border-gray-200"
              }`}
            >
              <div className="grid grid-cols-1 sm:grid-cols-12 gap-3 items-end">
                <div className="sm:col-span-4">
                  <Label htmlFor={`school-${i}`}>School</Label>
                  <Input
                    id={`school-${i}`}
                    list="known-schools"
                    value={row.school}
                    onChange={(e) => updateRow(i, { school: e.target.value })}
                    placeholder="e.g. San Marcos High School"
                  />
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor={`kind-${i}`}>Type</Label>
                  <select
                    id={`kind-${i}`}
                    value={row.kind}
                    onChange={(e) => updateRow(i, { kind: e.target.value })}
                    className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-base bg-white"
                  >
                    <option value="module">Module session</option>
                    <option value="orientation">Orientation</option>
                  </select>
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor={`date-${i}`}>Date</Label>
                  <Input
                    id={`date-${i}`}
                    type="date"
                    value={row.date}
                    onChange={(e) => updateRow(i, { date: e.target.value })}
                  />
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor={`time-${i}`}>Start time</Label>
                  <Input
                    id={`time-${i}`}
                    type="time"
                    value={row.start_time}
                    onChange={(e) => updateRow(i, { start_time: e.target.value })}
                  />
                </div>
                <div className="sm:col-span-2">
                  <Label htmlFor={`cap-${i}`}>Capacity</Label>
                  <Input
                    id={`cap-${i}`}
                    type="number"
                    min="1"
                    value={row.capacity}
                    onChange={(e) => updateRow(i, { capacity: e.target.value })}
                    placeholder={capacityPlaceholder}
                  />
                </div>
              </div>
              <div className="flex items-center gap-4 mt-2">
                <button
                  type="button"
                  onClick={() => duplicateRow(i)}
                  className="text-sm text-blue-600 hover:underline"
                >
                  Duplicate
                </button>
                <button
                  type="button"
                  onClick={() => removeRow(i)}
                  className="text-sm text-gray-500 hover:text-red-600 hover:underline"
                >
                  Remove
                </button>
              </div>
              {rowErrors[i] && <FieldError>{rowErrors[i]}</FieldError>}
            </div>
          ))}
        </div>

        <Button variant="ghost" onClick={addRow} className="text-sm">
          + Add another row
        </Button>
      </Card>

      {/* Step 3 — create */}
      <div className="flex items-center gap-3">
        <Button disabled={!canSubmit} onClick={() => createMut.mutate()}>
          {createMut.isPending ? "Creating…" : "Create events"}
        </Button>
        {!templateSlug && (
          <span className="text-sm text-gray-500">Pick a module first.</span>
        )}
      </div>
    </div>
  );
}
