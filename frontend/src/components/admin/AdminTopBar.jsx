import React from "react";
import { Link } from "react-router-dom";

/**
 * AdminTopBar — breadcrumbs left, optional center slot.
 * Account menu + Help now live in the outer Layout header.
 *
 * Props:
 *  - crumbs: Array<{ label: string, to?: string }>
 *  - centerSlot: optional React node rendered between crumbs and the right edge
 */
export default function AdminTopBar({ crumbs = [], centerSlot = null }) {
  return (
    <header className="flex items-center justify-between gap-4 border-b border-gray-200 bg-white px-6 py-3">
      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex items-center gap-2 text-sm text-gray-600">
          {crumbs.map((c, i) => {
            const isLast = i === crumbs.length - 1;
            return (
              <li key={`${c.label}-${i}`} className="flex items-center gap-2">
                {i > 0 && <span className="text-gray-400">/</span>}
                {c.to && !isLast ? (
                  <Link to={c.to} className="hover:text-gray-900">
                    {c.label}
                  </Link>
                ) : (
                  <span
                    className={isLast ? "font-semibold text-gray-900" : ""}
                    aria-current={isLast ? "page" : undefined}
                  >
                    {c.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </nav>

      {centerSlot ? <div className="flex-1 flex justify-center">{centerSlot}</div> : null}
    </header>
  );
}
