// CitationPanel — side-panel modal showing the full source chunk.
//
// Opened when a CitationChip is clicked. Fetches
// GET /api/v1/copilot/citations/{chunk_id} (Plan 32-05 endpoint) and renders:
//   - "Source consulted" header (RESEARCH §Pitfall 7 — honest copy)
//   - source_path, char range, full content (scrollable)
//   - "Open source" link ONLY when document_url is non-empty
//
// Plan 32-06 — REQ-32-07. The "side panel vs nav-away" choice is documented
// in RESEARCH §Pattern 6 + Open Q #1 (keeps chat context visible on mobile).
import React, { useEffect, useState } from "react";
import { X, ExternalLink, Loader2 } from "lucide-react";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";

export default function CitationPanel({ chunkId, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!chunkId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    setData(null);
    (async () => {
      try {
        const tok = authStorage.getToken();
        const res = await fetch(`${COPILOT_BASE}/citations/${chunkId}`, {
          method: "GET",
          headers: {
            Accept: "application/json",
            ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
          },
        });
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const body = await res.json();
        if (!cancelled) setData(body);
      } catch (err) {
        if (!cancelled) setError(err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [chunkId]);

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-50"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-label="Source consulted"
        className="fixed right-0 top-0 bottom-0 w-full sm:w-[32rem] bg-white shadow-xl z-50 flex flex-col"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b">
          <div className="min-w-0">
            <h3 className="font-semibold">Source consulted</h3>
            {data?.source_path && (
              <p className="text-xs text-gray-500 truncate" title={data.source_path}>
                {data.source_path}
                {Number.isFinite(data.char_start) && Number.isFinite(data.char_end) && (
                  <span className="ml-1 font-mono">
                    {data.char_start} – {data.char_end}
                  </span>
                )}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close source panel"
            className="p-2 rounded hover:bg-gray-100"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto px-4 py-3 text-sm">
          {loading && (
            <p className="text-gray-500 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading source…
            </p>
          )}
          {error && !loading && (
            <p className="text-red-600">Could not load source: {error.message}</p>
          )}
          {data && !loading && !error && (
            <pre className="whitespace-pre-wrap font-sans text-sm text-gray-900">
              {data.content}
            </pre>
          )}
        </div>

        {data && data.document_url && (
          <footer className="border-t p-3">
            <a
              href={data.document_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-sm text-indigo-700 hover:underline"
            >
              <ExternalLink className="w-4 h-4" />
              Open source
            </a>
          </footer>
        )}
      </aside>
    </>
  );
}
