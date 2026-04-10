// AdminImportPage.jsx -- TODO(brand) TODO(copy)
import React, { useState, useEffect, useCallback, useRef } from "react";
import { api } from "../lib/api";
import { PageHeader, Card, Button, Skeleton } from "../components/ui";
import ImportUploadForm from "../components/ImportUploadForm";
import ImportPreviewTable from "../components/ImportPreviewTable";

export default function AdminImportPage() {
  const [importId, setImportId] = useState(null);
  const [importData, setImportData] = useState(null);
  const [isPolling, setIsPolling] = useState(false);
  const [commitResult, setCommitResult] = useState(null);
  const [error, setError] = useState(null);
  const [uploading, setUploading] = useState(false);
  const intervalRef = useRef(null);

  // Cleanup polling on unmount
  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  const startPolling = useCallback((id) => {
    setIsPolling(true);
    intervalRef.current = setInterval(async () => {
      try {
        const data = await api.getCsvImport(id);
        setImportData(data);
        if (data.status === "ready" || data.status === "failed") {
          clearInterval(intervalRef.current);
          intervalRef.current = null;
          setIsPolling(false);
          if (data.status === "failed") {
            setError(data.error_message || "Import processing failed");
          }
        }
      } catch (err) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
        setIsPolling(false);
        setError(err.message);
      }
    }, 2000);
  }, []);

  const handleUpload = async (file) => {
    try {
      setError(null);
      setUploading(true);
      setCommitResult(null);
      const result = await api.uploadCsvImport(file);
      setImportId(result.id);
      setImportData(result);
      setUploading(false);
      // If status is already ready (eager mode), skip polling
      if (result.status === "ready" || result.status === "failed") {
        if (result.status === "failed") {
          setError(result.error_message || "Processing failed");
        }
      } else {
        startPolling(result.id);
      }
    } catch (err) {
      setUploading(false);
      setError(err.message);
    }
  };

  const handleSaveRow = async (index, updatedFields) => {
    try {
      setError(null);
      const updated = await api.updateImportRow(importId, index, updatedFields);
      setImportData((prev) => ({ ...prev, result_payload: updated }));
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCommit = async () => {
    try {
      setError(null);
      const result = await api.commitCsvImport(importId);
      setCommitResult(result);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleReset = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    setImportId(null);
    setImportData(null);
    setIsPolling(false);
    setCommitResult(null);
    setError(null);
    setUploading(false);
  };

  const preview = importData?.result_payload;

  return (
    <div className="space-y-4">
      {/* TODO(copy) */}
      <PageHeader title="CSV Import" />

      {error && (
        <div className="rounded bg-red-50 p-3 text-sm text-red-700">{error}</div>
      )}

      {commitResult && (
        <div className="rounded bg-green-50 p-4 text-sm text-green-800">
          <p className="font-semibold">
            Created {commitResult.created_count} events successfully
          </p>
          {commitResult.events?.map((ev) => (
            <p key={ev.event_id} className="mt-1 text-xs">
              {ev.title} at {ev.location} ({ev.start_date})
            </p>
          ))}
          <Button className="mt-3" variant="outline" onClick={handleReset}>
            Upload Another
          </Button>
        </div>
      )}

      {!importId && !commitResult && (
        <ImportUploadForm onUpload={handleUpload} uploading={uploading} />
      )}

      {isPolling && (
        <Card className="text-center">
          <Skeleton className="h-4 mb-2" />
          <p className="text-sm text-[var(--color-fg-muted)]">
            Processing CSV... {/* TODO(copy) */}
          </p>
        </Card>
      )}

      {importData?.status === "ready" && preview && !commitResult && (
        <ImportPreviewTable
          preview={preview}
          onSaveRow={handleSaveRow}
          onCommit={handleCommit}
        />
      )}

      {importId && !isPolling && !commitResult && (
        <div className="flex justify-end">
          <Button variant="outline" onClick={handleReset}>
            Upload Another
          </Button>
        </div>
      )}
    </div>
  );
}
