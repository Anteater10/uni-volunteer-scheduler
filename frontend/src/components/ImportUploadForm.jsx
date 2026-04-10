// ImportUploadForm.jsx -- TODO(brand) TODO(copy)
import React, { useState, useRef, useCallback } from "react";
import { Button } from "./ui";

export default function ImportUploadForm({ onUpload, uploading }) {
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef(null);

  const handleFile = useCallback(
    (file) => {
      if (!file) return;
      if (!file.name.endsWith(".csv")) {
        alert("Only .csv files are accepted");
        return;
      }
      onUpload(file);
    },
    [onUpload]
  );

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files?.[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const handleChange = (e) => {
    if (e.target.files?.[0]) {
      handleFile(e.target.files[0]);
    }
  };

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
        dragActive
          ? "border-blue-500 bg-blue-50"
          : "border-gray-300 hover:border-gray-400"
      }`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      {uploading ? (
        <p className="text-sm text-[var(--color-fg-muted)]">Uploading...</p>
      ) : (
        <>
          {/* TODO(copy) */}
          <p className="mb-3 text-sm text-[var(--color-fg-muted)]">
            Drag and drop a CSV file here, or click to select
          </p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={handleChange}
          />
          <Button onClick={() => inputRef.current?.click()}>
            Select CSV File
          </Button>
        </>
      )}
    </div>
  );
}
