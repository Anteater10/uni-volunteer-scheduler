import React from "react";

/**
 * Build a compact numbered pagination with ellipses.
 * Example: page=5, totalPages=47 → [1, "…", 3, 4, 5, 6, 7, "…", 47]
 */
export function buildPageList(page, totalPages) {
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const pages = new Set([1, totalPages, page, page - 1, page + 1, page - 2, page + 2]);
  const sorted = [...pages].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
  const out = [];
  for (let i = 0; i < sorted.length; i++) {
    if (i > 0 && sorted[i] - sorted[i - 1] > 1) out.push("…");
    out.push(sorted[i]);
  }
  return out;
}

/**
 * Pagination
 * Props:
 *  - page: number (1-based)
 *  - totalPages: number
 *  - onChange: (page: number) => void
 */
export default function Pagination({ page, totalPages, onChange }) {
  if (!totalPages || totalPages <= 1) return null;
  const pages = buildPageList(page, totalPages);

  function go(p) {
    if (p < 1 || p > totalPages || p === page) return;
    onChange && onChange(p);
  }

  return (
    <nav aria-label="Pagination" className="flex items-center gap-1">
      <button
        type="button"
        onClick={() => go(page - 1)}
        disabled={page <= 1}
        aria-label="Previous page"
        className="rounded-md px-2 py-1 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-40"
      >
        ‹
      </button>
      {pages.map((p, i) =>
        p === "…" ? (
          <span
            key={`ellipsis-${i}`}
            aria-hidden="true"
            className="px-2 text-sm text-gray-400"
          >
            …
          </span>
        ) : (
          <button
            key={p}
            type="button"
            onClick={() => go(p)}
            aria-current={p === page ? "page" : undefined}
            className={`rounded-md px-3 py-1 text-sm ${
              p === page
                ? "bg-gray-900 text-white"
                : "text-gray-700 hover:bg-gray-100"
            }`}
          >
            {p}
          </button>
        ),
      )}
      <button
        type="button"
        onClick={() => go(page + 1)}
        disabled={page >= totalPages}
        aria-label="Next page"
        className="rounded-md px-2 py-1 text-sm text-gray-700 hover:bg-gray-100 disabled:opacity-40"
      >
        ›
      </button>
    </nav>
  );
}
