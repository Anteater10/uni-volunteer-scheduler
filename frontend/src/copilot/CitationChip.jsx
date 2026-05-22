// CitationChip — small inline chip rendered below an assistant message.
//
// Displays `[N] <filename>` where filename is the basename of `source_path`.
// The full path + quote are exposed via the `title` attribute so hover and
// keyboard-focus reveal the supporting evidence (RESEARCH §Pattern 5).
//
// Plan 32-06 — REQ-32-07. Strictly visual + click handler; the fetch for
// full content lives in CitationPanel.
import React from "react";

function basename(path) {
  if (!path) return "source";
  const idx = path.lastIndexOf("/");
  return idx === -1 ? path : path.slice(idx + 1);
}

function truncateQuote(quote, max = 200) {
  if (!quote) return "";
  if (quote.length <= max) return quote;
  return quote.slice(0, max).trimEnd() + "…";
}

export default function CitationChip({ index, citation, onClick }) {
  const filename = basename(citation?.source_path);
  const tooltip = [
    citation?.source_path,
    truncateQuote(citation?.quote),
  ]
    .filter(Boolean)
    .join("\n\n");

  function activate() {
    onClick?.(citation?.chunk_id);
  }

  function onKeyDown(e) {
    if (e.key === "Enter" || e.key === " " || e.key === "Spacebar") {
      e.preventDefault();
      activate();
    }
  }

  return (
    <span
      role="button"
      tabIndex={0}
      aria-label={`Citation ${index}: ${filename}`}
      title={tooltip}
      onClick={activate}
      onKeyDown={onKeyDown}
      className="inline-flex shrink-0 items-center gap-1 rounded-full border border-indigo-200 bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700 hover:bg-indigo-100 focus:outline-none focus:ring-2 focus:ring-indigo-300 cursor-pointer select-none"
    >
      <span className="font-mono">[{index}]</span>
      <span className="truncate max-w-[10rem]">{filename}</span>
    </span>
  );
}
