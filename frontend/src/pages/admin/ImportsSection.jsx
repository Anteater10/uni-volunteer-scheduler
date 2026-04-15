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

function formatTs(ts) {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts || "");
  }
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
  const queryClient = useQueryClient();
  const fileInputRef = useRef(null);
  const [commitTarget, setCommitTarget] = useState(null);

  const importsQ = useQuery({
    queryKey: ["adminImports"],
    queryFn: () => api.admin.imports.list(),
    // Some backends return a list, some wrap in an object
    select: (data) => (Array.isArray(data) ? data : data?.items || []),
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
        >
          {/* TODO(copy) */}
          {uploadMut.isPending ? "Uploading..." : "Upload CSV"}
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
          {/* Desktop table */}
          <div className="hidden md:block overflow-x-auto">
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

          {/* Mobile cards */}
          <div className="md:hidden space-y-3">
            {imports.map((imp) => (
              <Card key={imp.id}>
                <div className="flex items-baseline gap-2">
                  <span className="font-medium">{imp.filename}</span>
                  <StatusChip status={imp.status} />
                </div>
                <p className="text-xs text-[var(--color-fg-muted)] mt-1">
                  {formatTs(imp.created_at)}
                </p>
                {imp.error_message && (
                  <p className="text-xs text-red-600 mt-1">{imp.error_message}</p>
                )}
                <div className="mt-2 flex gap-2">
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
                </div>
              </Card>
            ))}
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
          {/* TODO(copy) */}
          Commit import <strong>{commitTarget?.filename}</strong>? This will create events
          from the validated rows.
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
