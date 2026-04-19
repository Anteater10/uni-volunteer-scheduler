// src/pages/admin/ImportsSection.jsx
import React, { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "../../lib/api";
import {
  Card,
  Button,
  Modal,
  Chip,
  EmptyState,
  Skeleton,
  Input,
  Label,
} from "../../components/ui";
import { toast } from "../../state/toast";
import { useAdminPageTitle } from "./AdminLayout";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RTF = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
function formatTs(iso) {
  if (!iso) return "—";
  const diff = (new Date(iso) - new Date()) / 1000;
  if (Number.isNaN(diff)) return "—";
  const abs = Math.abs(diff);
  if (abs < 60) return RTF.format(Math.round(diff), "second");
  if (abs < 3600) return RTF.format(Math.round(diff / 60), "minute");
  if (abs < 86400) return RTF.format(Math.round(diff / 3600), "hour");
  return RTF.format(Math.round(diff / 86400), "day");
}

function formatDate(isoDate) {
  if (!isoDate) return "—";
  try {
    return new Date(isoDate).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return isoDate;
  }
}

function humanizeError(msg) {
  if (!msg) return null;
  if (msg.includes("AuthenticationError") || msg.includes("API key"))
    return "The AI service could not authenticate. Ask your admin to check the API key.";
  if (msg.includes("cost") && msg.includes("ceiling"))
    return "This CSV is too large to process. Try splitting it into smaller files.";
  if (msg.includes("timeout") || msg.includes("Timeout"))
    return "Processing took too long. Try again or use a smaller file.";
  return "Something went wrong during processing. Click Re-run to try again.";
}

const IMPORT_STATUS_COLORS = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  ready: "bg-green-100 text-green-800",
  committed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

function StatusChip({ status }) {
  const colorClass = IMPORT_STATUS_COLORS[status] || "bg-gray-100 text-gray-800";
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${colorClass}`}>
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Row status chip for preview table
// ---------------------------------------------------------------------------

function RowStatusChip({ status }) {
  if (status === "ok") {
    return (
      <span className="text-xs px-2 py-0.5 rounded font-medium bg-green-100 text-green-800">
        Ready
      </span>
    );
  }
  if (status === "low_confidence") {
    return (
      <span className="text-xs px-2 py-0.5 rounded font-medium bg-yellow-100 text-yellow-800">
        Needs Review
      </span>
    );
  }
  if (status === "conflict") {
    return (
      <span className="text-xs px-2 py-0.5 rounded font-medium bg-red-100 text-red-800">
        Conflict
      </span>
    );
  }
  return (
    <span className="text-xs px-2 py-0.5 rounded font-medium bg-gray-100 text-gray-800">
      {status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Inline row edit form for low_confidence rows
// ---------------------------------------------------------------------------

function RowEditForm({ row, importId, onSave, onCancel }) {
  const queryClient = useQueryClient();
  const [moduleSlug, setModuleSlug] = useState(row.normalized?.module_slug || "");
  const [location, setLocation] = useState(row.normalized?.location || "");
  const [capacity, setCapacity] = useState(row.normalized?.capacity ?? "");

  const updateRowMut = useMutation({
    mutationFn: (data) => api.admin.imports.updateRow(importId, row.index, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      toast.success("Row updated.");
      onSave();
    },
    onError: (err) => toast.error(err?.message || "Update failed"),
  });

  function handleSave() {
    updateRowMut.mutate({
      module_slug: moduleSlug,
      location,
      capacity: capacity !== "" ? Number(capacity) : undefined,
    });
  }

  return (
    <tr className="bg-yellow-50">
      <td colSpan={7} className="px-4 py-3">
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <Label htmlFor={`slug-${row.index}`}>Module slug</Label>
            <Input
              id={`slug-${row.index}`}
              value={moduleSlug}
              onChange={(e) => setModuleSlug(e.target.value)}
              placeholder="e.g. dna-extraction"
            />
          </div>
          <div>
            <Label htmlFor={`loc-${row.index}`}>Location</Label>
            <Input
              id={`loc-${row.index}`}
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. Broida 1015"
            />
          </div>
          <div>
            <Label htmlFor={`cap-${row.index}`}>Capacity</Label>
            <Input
              id={`cap-${row.index}`}
              type="number"
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
              placeholder="e.g. 30"
            />
          </div>
        </div>
        <div className="flex gap-2">
          <Button
            className="text-xs !px-2 !py-1"
            disabled={updateRowMut.isPending}
            onClick={handleSave}
          >
            {updateRowMut.isPending ? "Saving..." : "Save"}
          </Button>
          <Button variant="ghost" className="text-xs !px-2 !py-1" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Preview detail panel
// ---------------------------------------------------------------------------

function ImportDetail({ imp }) {
  const [editingRowIndex, setEditingRowIndex] = useState(null);
  const queryClient = useQueryClient();
  const revalidateMut = useMutation({
    mutationFn: () => api.admin.imports.revalidate(imp.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      toast.success("Conflicts re-checked.");
    },
    onError: (err) => toast.error(err?.message || "Re-check failed"),
  });

  const status = imp.status;
  const payload = imp.result_payload || {};
  const rows = payload.rows || [];
  const summary = payload.summary || {};

  // Show processing indicator for pending/processing
  if (status === "pending" || status === "processing") {
    return (
      <div className="mt-4 border rounded-lg p-4 space-y-3">
        <p className="text-sm font-medium animate-pulse text-blue-700">
          Processing your CSV...
        </p>
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
      </div>
    );
  }

  if (status === "failed") {
    return (
      <div className="mt-4 border border-red-200 rounded-lg p-4 bg-red-50">
        <p className="text-sm font-medium text-red-800">Processing failed</p>
        <p className="text-sm text-red-700 mt-1">{humanizeError(imp.error_message)}</p>
      </div>
    );
  }

  if (status !== "ready" || rows.length === 0) {
    return null;
  }

  const toCreate = summary.to_create ?? 0;
  const toReview = summary.to_review ?? 0;
  const conflicts = summary.conflicts ?? 0;
  const canCommit = toReview === 0;

  return (
    <div className="mt-4 border rounded-lg overflow-hidden">
      {/* Summary banner */}
      <div className="px-4 py-3 bg-gray-50 border-b flex flex-wrap gap-3 items-center">
        <span className="text-sm font-medium">Preview:</span>
        <span className="inline-flex items-center gap-1 text-xs">
          <span className="px-2 py-0.5 rounded font-medium bg-green-100 text-green-800">
            {toCreate} ready to create
          </span>
        </span>
        {toReview > 0 && (
          <span className="inline-flex items-center gap-1 text-xs">
            <span className="px-2 py-0.5 rounded font-medium bg-yellow-100 text-yellow-800">
              {toReview} need{toReview === 1 ? "s" : ""} your review
            </span>
          </span>
        )}
        {conflicts > 0 && (
          <span className="inline-flex items-center gap-1 text-xs">
            <span className="px-2 py-0.5 rounded font-medium bg-red-100 text-red-800">
              {conflicts} scheduling conflict{conflicts === 1 ? "" : "s"}
            </span>
          </span>
        )}
      </div>

      {/* Preview table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left">
              <th className="py-2 px-3 font-medium">#</th>
              <th className="py-2 px-3 font-medium">Module</th>
              <th className="py-2 px-3 font-medium">Date</th>
              <th className="py-2 px-3 font-medium">Location</th>
              <th className="py-2 px-3 font-medium">Status</th>
              <th className="py-2 px-3 font-medium">Warnings</th>
              <th className="py-2 px-3 font-medium"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {rows.map((row) => {
              const rowBg =
                row.status === "low_confidence"
                  ? "bg-yellow-50 border-l-4 border-yellow-400"
                  : row.status === "conflict"
                  ? "bg-red-50 border-l-4 border-red-400"
                  : "";

              const isEditing = editingRowIndex === row.index;

              return (
                <React.Fragment key={row.index}>
                  <tr className={rowBg}>
                    <td className="py-2 px-3 text-gray-500">{row.index + 1}</td>
                    <td className="py-2 px-3">{row.normalized?.module_slug || "—"}</td>
                    <td className="py-2 px-3 whitespace-nowrap">
                      {formatDate(row.normalized?.start_at)}
                    </td>
                    <td className="py-2 px-3">{row.normalized?.location || "—"}</td>
                    <td className="py-2 px-3">
                      <RowStatusChip status={row.status} />
                    </td>
                    <td className="py-2 px-3 text-xs text-gray-600 max-w-xs">
                      {(row.warnings || []).join("; ") || "—"}
                    </td>
                    <td className="py-2 px-3">
                      {row.status === "low_confidence" && !isEditing && (
                        <Button
                          variant="ghost"
                          className="text-xs !px-2 !py-1"
                          onClick={() => setEditingRowIndex(row.index)}
                        >
                          Edit
                        </Button>
                      )}
                    </td>
                  </tr>
                  {isEditing && (
                    <RowEditForm
                      key={`edit-${row.index}`}
                      row={row}
                      importId={imp.id}
                      onSave={() => setEditingRowIndex(null)}
                      onCancel={() => setEditingRowIndex(null)}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Commit footer */}
      <div className="px-4 py-3 bg-gray-50 border-t flex flex-wrap items-center gap-3">
        <Button
          variant="ghost"
          className="text-xs"
          disabled={revalidateMut.isPending}
          onClick={() => revalidateMut.mutate()}
          title="Re-check conflicts against the current events list."
        >
          {revalidateMut.isPending ? "Re-checking…" : "Re-check conflicts"}
        </Button>
        <Button
          disabled={!canCommit}
          title={
            !canCommit
              ? "Resolve all flagged rows before committing."
              : `Commit ${toCreate} events`
          }
          onClick={() => {
            // Trigger modal via prop — parent handles this via commitTarget state
            // We emit a custom event to signal the parent. Actually, we use
            // a callback pattern instead: pass imp up to the parent commit handler.
            // Since the detail panel is rendered inside the parent, we use the
            // onCommit prop.
            if (typeof window !== "undefined") {
              window.dispatchEvent(
                new CustomEvent("imports:commit-requested", { detail: { imp } })
              );
            }
          }}
        >
          {canCommit ? `Commit ${toCreate} events` : "Resolve all flagged rows first"}
        </Button>
        {!canCommit && (
          <span className="text-xs text-yellow-700">
            Resolve all flagged rows before committing.
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main section
// ---------------------------------------------------------------------------

export default function ImportsSection() {
  useAdminPageTitle("Imports");
  const queryClient = useQueryClient();
  const fileInputRef = useRef(null);
  const [commitTarget, setCommitTarget] = useState(null);
  const [selectedImportId, setSelectedImportId] = useState(null);
  const [commitTemplateSlug, setCommitTemplateSlug] = useState("");

  // Module templates — needed to populate the "apply to template" dropdown
  // shown in the Commit modal (Option A workflow: admin picks the module
  // when committing, not when uploading).
  const templatesQ = useQuery({
    queryKey: ["adminModuleTemplates"],
    queryFn: () => api.getModuleTemplates(),
  });
  const templates = templatesQ.data || [];

  // Listen for commit requests from the detail panel
  React.useEffect(() => {
    function handleCommitRequest(e) {
      setCommitTarget(e.detail.imp);
    }
    window.addEventListener("imports:commit-requested", handleCommitRequest);
    return () => window.removeEventListener("imports:commit-requested", handleCommitRequest);
  }, []);

  // Poll every 2s while any import is pending/processing
  const importsQ = useQuery({
    queryKey: ["adminImports"],
    queryFn: () => api.admin.imports.list(),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const hasActive = data.some(
        (imp) => imp.status === "pending" || imp.status === "processing"
      );
      return hasActive ? 2000 : false;
    },
  });

  const uploadMut = useMutation({
    mutationFn: (file) => api.admin.imports.upload(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      toast.success("CSV uploaded. Processing...");
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    onError: (err) => toast.error(err?.message || "Upload failed"),
  });

  const commitMut = useMutation({
    mutationFn: ({ id, slug }) => api.admin.imports.commit(id, slug),
    onSuccess: (data) => {
      const n = data?.created_count ?? 0;
      setCommitTarget(null);
      setCommitTemplateSlug("");
      setSelectedImportId(null);
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      toast.success(`Created ${n} event${n === 1 ? "" : "s"}.`);
    },
    onError: (err) => toast.error(err?.message || "Commit failed"),
  });

  const retryMut = useMutation({
    mutationFn: (id) => api.admin.imports.retry(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      toast.success("Import re-submitted for processing.");
    },
    onError: (err) => toast.error(err?.message || "Retry failed"),
  });

  const deleteMut = useMutation({
    mutationFn: (id) => api.admin.imports.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      setSelectedImportId(null);
      toast.success("Import deleted. Events already committed are untouched.");
    },
    onError: (err) => toast.error(err?.message || "Delete failed"),
  });

  function handleDeleteImport(id) {
    if (
      !window.confirm(
        "Delete this import record? Events already committed will NOT be removed.",
      )
    )
      return;
    deleteMut.mutate(id);
  }

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (file) uploadMut.mutate(file);
  }

  const imports = importsQ.data || [];
  const selectedImport = imports.find((imp) => imp.id === selectedImportId) || null;

  // Auto re-check conflicts whenever the admin opens a ready import — keeps
  // the preview honest after they delete conflicting events elsewhere.
  React.useEffect(() => {
    if (!selectedImport || selectedImport.status !== "ready") return;
    api.admin.imports
      .revalidate(selectedImport.id)
      .then(() =>
        queryClient.invalidateQueries({ queryKey: ["adminImports"] }),
      )
      .catch(() => {});
  }, [selectedImportId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Build commit modal copy from payload summary
  const commitSummary = commitTarget?.result_payload?.summary;
  const commitModalBody = commitSummary
    ? `This will create ${commitSummary.to_create ?? 0} events. ${
        (commitSummary.conflicts ?? 0) > 0
          ? `${commitSummary.conflicts} conflicting rows will be skipped. `
          : ""
      }This cannot be undone.`
    : "Commit this import? This creates all events in the preview and cannot be undone.";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-5xl font-bold tracking-tight">Imports</h1>
        <p className="text-xl text-[var(--color-fg-muted)] mt-3">
          Upload a quarterly SciTrek CSV. The system reads the file, extracts
          events, and shows you a preview before anything is saved.
        </p>
      </div>

      {/* Upload bar */}
      <div className="flex flex-wrap gap-3 items-center">
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMut.isPending}
          title="Upload a Sci Trek quarterly CSV to preview and commit events."
          className="px-8 py-4 text-xl font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-xl shadow disabled:opacity-50"
        >
          {uploadMut.isPending ? "Uploading..." : "Upload quarterly CSV"}
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv"
          className="hidden"
          onChange={handleFileSelect}
        />
      </div>

      {/* Import History */}
      {importsQ.isPending ? (
        <div className="space-y-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : importsQ.error ? (
        <EmptyState
          title="Couldn't load imports"
          body={importsQ.error.message}
          action={<Button onClick={() => importsQ.refetch()}>Retry</Button>}
        />
      ) : imports.length === 0 ? (
        <EmptyState
          title="No imports"
          body="Upload a CSV file to get started."
        />
      ) : (
        <>
          {/* Admin-only, desktop-first (D-08): single table, no mobile fallback. */}
          <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
            <table className="min-w-full text-2xl">
              <thead className="bg-gray-50 text-left text-xl uppercase tracking-wide text-gray-600">
                <tr>
                  <th className="py-5 px-6">Filename</th>
                  <th className="py-5 px-6">Status</th>
                  <th className="py-5 px-6">Created</th>
                  <th className="py-5 px-6 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {imports.map((imp) => (
                  <tr
                    key={imp.id}
                    className={`cursor-pointer hover:bg-gray-50 ${
                      selectedImportId === imp.id ? "bg-blue-50" : ""
                    }`}
                    onClick={() =>
                      setSelectedImportId(
                        selectedImportId === imp.id ? null : imp.id
                      )
                    }
                  >
                    <td className="py-6 px-6 font-semibold">{imp.filename}</td>
                    <td className="py-6 px-6">
                      <span
                        className={`inline-flex items-center rounded-full px-3 py-1 text-base font-medium ${
                          IMPORT_STATUS_COLORS[imp.status] ||
                          "bg-gray-100 text-gray-800"
                        }`}
                      >
                        {imp.status}
                      </span>
                    </td>
                    <td className="py-6 px-6 text-gray-600 whitespace-nowrap">
                      {formatTs(imp.created_at)}
                    </td>
                    <td
                      className="py-6 px-6 text-right space-x-5 whitespace-nowrap"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {imp.status === "failed" && (
                        <button
                          type="button"
                          disabled={retryMut.isPending}
                          onClick={() => retryMut.mutate(imp.id)}
                          className="text-blue-600 hover:underline font-medium disabled:opacity-50"
                        >
                          Re-run
                        </button>
                      )}
                      <button
                        type="button"
                        disabled={deleteMut.isPending}
                        onClick={() => handleDeleteImport(imp.id)}
                        className="text-red-600 hover:underline font-medium disabled:opacity-50"
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Detail panel for selected import */}
          {selectedImport && <ImportDetail imp={selectedImport} />}
        </>
      )}

      {/* Commit confirm modal */}
      <Modal
        open={!!commitTarget}
        onClose={() => {
          setCommitTarget(null);
          setCommitTemplateSlug("");
        }}
        title="Commit import"
      >
        <p className="text-sm">{commitModalBody}</p>

        <div className="mt-4">
          <Label htmlFor="commit-template">
            Apply this schedule to module template
          </Label>
          <select
            id="commit-template"
            value={commitTemplateSlug}
            onChange={(e) => setCommitTemplateSlug(e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white"
          >
            <option value="">Select a module…</option>
            {templates.map((t) => (
              <option key={t.slug} value={t.slug}>
                {t.name}
              </option>
            ))}
          </select>
          <p className="text-xs text-gray-500 mt-1">
            Each row in the preview becomes one event titled with this module
            and using its description.
          </p>
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button
            variant="ghost"
            onClick={() => {
              setCommitTarget(null);
              setCommitTemplateSlug("");
            }}
          >
            Cancel
          </Button>
          <Button
            disabled={commitMut.isPending || !commitTemplateSlug}
            onClick={() =>
              commitTarget &&
              commitMut.mutate({
                id: commitTarget.id,
                slug: commitTemplateSlug,
              })
            }
          >
            {commitMut.isPending ? "Committing…" : "Create events"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
