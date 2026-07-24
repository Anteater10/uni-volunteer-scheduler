import React from "react";

/**
 * Standard header for every admin page: a text-3xl bold title with an
 * optional text-sm muted subtitle, plus an optional right-aligned action
 * slot (e.g. a "+ New event" button) passed as children.
 *
 * Use this instead of hand-rolling <h1>/<p> so page titles stay a single,
 * consistent size across all tabs.
 */
export default function AdminPageHeader({ title, subtitle, children }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold tracking-tight text-gray-900">
          {title}
        </h1>
        {subtitle ? (
          <p className="text-sm text-gray-600 mt-1">{subtitle}</p>
        ) : null}
      </div>
      {children ? <div className="flex-shrink-0">{children}</div> : null}
    </div>
  );
}
