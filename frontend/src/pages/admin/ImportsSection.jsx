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
} from "../../components/ui";
import { toast } from "../../state/toast";
import { useAdminPageTitle } from "./AdminLayout";

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

const STATUS_COLORS = {
  pending: "bg-yellow-100 text-yellow-800",
  processing: "bg-blue-100 text-blue-800",
  ready: "bg-blue-100 text-blue-800",
  committed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

function StatusChip({ status }) {
  const colorClass = STATUS_COLORS[status] || "bg-gray-100 text-gray-800";
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-medium ${colorClass}`}>
      {status}
    </span>
  );
}

export default function ImportsSection() {
  useAdminPageTitle("Imports");
  const queryClient = useQueryClient();
  const fileInputRef = useRef(null);
  const [commitTarget, setCommitTarget] = useState(null);

  const importsQ = useQuery({
    queryKey: ["adminImports"],
    queryFn: () => api.admin.imports.list(),
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
    mutationFn: (id) => api.admin.imports.commit(id),
    onSuccess: () => {
      setCommitTarget(null);
      queryClient.invalidateQueries({ queryKey: ["adminImports"] });
      toast.success("Import committed.");
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

  function handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (file) uploadMut.mutate(file);
  }

  const imports = importsQ.data || [];

  return (
    <div className="space-y-4">
      {/* Upload bar */}
      <div className="flex flex-wrap gap-3 items-center">
        <Button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadMut.isPending}
          title="Upload a Sci Trek quarterly CSV to preview and commit events."
        >
          {uploadMut.isPending ? "Uploading…" : "Upload quarterly CSV"}
        </Button>
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
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left">
                  <th className="py-2 pr-3 font-medium">Filename</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Created</th>
                  <th className="py-2 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--color-border)]">
                {imports.map((imp) => (
                  <tr key={imp.id}>
                    <td className="py-2 pr-3">{imp.filename}</td>
                    <td className="py-2 pr-3">
                      <StatusChip status={imp.status} />
                    </td>
                    <td className="py-2 pr-3 text-[var(--color-fg-muted)] whitespace-nowrap">
                      {formatTs(imp.created_at)}
                    </td>
                    <td className="py-2 flex gap-2">
                      {(imp.status === "ready" || imp.status === "previewing") && (
                        <Button
                          className="text-xs !px-2 !py-1"
                          onClick={() => setCommitTarget(imp)}
                        >
                          Commit
                        </Button>
                      )}
                      {imp.status === "failed" && (
                        <Button
                          variant="secondary"
                          className="text-xs !px-2 !py-1"
                          disabled={retryMut.isPending}
                          onClick={() => retryMut.mutate(imp.id)}
                        >
                          Re-run
                        </Button>
                      )}
                      {imp.error_message && (
                        <span className="text-xs text-red-600 truncate max-w-xs">
                          {imp.error_message}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* Commit confirm modal */}
      <Modal
        open={!!commitTarget}
        onClose={() => setCommitTarget(null)}
        title="Commit Import"
      >
        <p className="text-sm">
          Commit this import? This creates all events in the preview and
          cannot be undone. Click Commit to proceed or Cancel to go back.
        </p>
        <div className="flex justify-end gap-2 mt-4">
          <Button variant="ghost" onClick={() => setCommitTarget(null)}>Cancel</Button>
          <Button
            disabled={commitMut.isPending}
            onClick={() => commitMut.mutate(commitTarget.id)}
          >
            {commitMut.isPending ? "Committing..." : "Commit"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
