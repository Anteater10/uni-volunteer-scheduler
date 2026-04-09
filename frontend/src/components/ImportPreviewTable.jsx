// ImportPreviewTable.jsx -- TODO(brand) TODO(copy)
import React, { useState } from "react";
import { Button } from "./ui";

const STATUS_STYLES = {
  ok: "border-l-4 border-green-500 bg-green-50",
  low_confidence: "border-l-4 border-amber-500 bg-amber-50",
  conflict: "border-l-4 border-red-500 bg-red-50",
};

function EditableRow({ row, onSaveRow }) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState({ ...row.normalized });

  const handleSave = () => {
    onSaveRow(row.index, fields);
    setEditing(false);
  };

  if (editing) {
    return (
      <tr className={STATUS_STYLES[row.status] || ""}>
        <td className="px-3 py-2">{row.index + 1}</td>
        <td className="px-3 py-2">
          <input
            className="w-full rounded border px-1 py-0.5 text-sm"
            value={fields.module_slug || ""}
            onChange={(e) => setFields({ ...fields, module_slug: e.target.value })}
          />
        </td>
        <td className="px-3 py-2">
          <input
            className="w-full rounded border px-1 py-0.5 text-sm"
            value={fields.location || ""}
            onChange={(e) => setFields({ ...fields, location: e.target.value })}
          />
        </td>
        <td className="px-3 py-2 text-sm">{fields.start_at}</td>
        <td className="px-3 py-2 text-sm">{fields.end_at}</td>
        <td className="px-3 py-2">
          <input
            type="number"
            className="w-16 rounded border px-1 py-0.5 text-sm"
            value={fields.capacity || ""}
            onChange={(e) => setFields({ ...fields, capacity: Number(e.target.value) || null })}
          />
        </td>
        <td className="px-3 py-2">
          <input
            className="w-full rounded border px-1 py-0.5 text-sm"
            value={fields.instructor_name || ""}
            onChange={(e) => setFields({ ...fields, instructor_name: e.target.value })}
          />
        </td>
        <td className="px-3 py-2 text-sm">{row.status}</td>
        <td className="px-3 py-2 space-x-1">
          <Button size="sm" onClick={handleSave}>Save</Button>
          <Button size="sm" variant="outline" onClick={() => setEditing(false)}>Cancel</Button>
        </td>
      </tr>
    );
  }

  return (
    <tr className={STATUS_STYLES[row.status] || ""}>
      <td className="px-3 py-2">{row.index + 1}</td>
      <td className="px-3 py-2 font-mono text-sm">{row.normalized.module_slug}</td>
      <td className="px-3 py-2 text-sm">{row.normalized.location}</td>
      <td className="px-3 py-2 text-sm">{row.normalized.start_at}</td>
      <td className="px-3 py-2 text-sm">{row.normalized.end_at}</td>
      <td className="px-3 py-2 text-center">{row.normalized.capacity}</td>
      <td className="px-3 py-2 text-sm">{row.normalized.instructor_name}</td>
      <td className="px-3 py-2">
        <span
          className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
            row.status === "ok"
              ? "bg-green-100 text-green-800"
              : row.status === "low_confidence"
              ? "bg-amber-100 text-amber-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {row.status}
        </span>
      </td>
      <td className="px-3 py-2">
        <Button size="sm" variant="outline" onClick={() => setEditing(true)}>
          Edit
        </Button>
      </td>
    </tr>
  );
}

export default function ImportPreviewTable({ preview, onSaveRow, onCommit }) {
  const { summary, rows } = preview;

  return (
    <div className="space-y-3">
      {/* Summary bar */}
      <div className="flex items-center gap-4 text-sm">
        <span className="font-medium text-green-700">{summary.to_create} to create</span>
        <span className="text-[var(--color-fg-muted)]">|</span>
        <span className="font-medium text-amber-700">{summary.to_review} to review</span>
        <span className="text-[var(--color-fg-muted)]">|</span>
        <span className="font-medium text-red-700">{summary.conflicts} conflicts</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded border border-[var(--color-border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--color-bg-muted)] border-b border-[var(--color-border)]">
              <th className="px-3 py-2 text-left">#</th>
              <th className="px-3 py-2 text-left">Module</th>
              <th className="px-3 py-2 text-left">Location</th>
              <th className="px-3 py-2 text-left">Start</th>
              <th className="px-3 py-2 text-left">End</th>
              <th className="px-3 py-2 text-center">Capacity</th>
              <th className="px-3 py-2 text-left">Instructor</th>
              <th className="px-3 py-2 text-left">Status</th>
              <th className="px-3 py-2 text-left">Actions</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <EditableRow key={row.index} row={row} onSaveRow={onSaveRow} />
            ))}
          </tbody>
        </table>
      </div>

      {/* Warnings */}
      {rows.some((r) => r.warnings?.length > 0) && (
        <div className="text-xs text-[var(--color-fg-muted)] space-y-1">
          {rows
            .filter((r) => r.warnings?.length > 0)
            .map((r) => (
              <p key={r.index}>
                Row {r.index + 1}: {r.warnings.join("; ")}
              </p>
            ))}
        </div>
      )}

      {/* Commit button */}
      <div className="flex justify-end">
        <Button
          disabled={summary.to_review > 0}
          onClick={onCommit}
          className={
            summary.to_review > 0
              ? "opacity-50 cursor-not-allowed"
              : "bg-green-600 text-white hover:bg-green-700"
          }
          title={
            summary.to_review > 0
              ? "Resolve all flagged rows first"
              : "Commit all validated rows"
          }
        >
          Commit All ({summary.to_create} events)
        </Button>
      </div>
    </div>
  );
}
