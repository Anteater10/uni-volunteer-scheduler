import React, { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import RoleBadge from "./RoleBadge";

/**
 * AdminTopBar — breadcrumbs left, optional center slot, account dropdown right.
 *
 * Props:
 *  - crumbs: Array<{ label: string, to?: string }>
 *  - user:   { name?: string, email?: string, role?: string }
 *  - onSignOut: () => void
 *  - centerSlot: optional React node rendered between crumbs and account menu
 */
export default function AdminTopBar({ crumbs = [], user, onSignOut, centerSlot = null }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(e) {
      if (e.key === "Escape") setOpen(false);
    }
    function onClick(e) {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onClick);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onClick);
    };
  }, [open]);

  const displayName = user?.name || user?.email || "Admin";

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

      <div className="flex items-center gap-4">
        <Link to="/admin/help" className="text-sm text-gray-600 hover:text-gray-900">
          Help
        </Link>

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={open}
            onClick={() => setOpen((o) => !o)}
            className="flex items-center gap-2 rounded-lg px-2 py-1 hover:bg-gray-100"
          >
            <span className="text-sm font-medium text-gray-900">{displayName}</span>
            {user?.role ? <RoleBadge role={user.role} /> : null}
          </button>
          {open ? (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-56 rounded-lg border border-gray-200 bg-white p-2 shadow-lg z-50"
            >
              <div className="px-2 py-1.5 text-xs text-gray-500">
                {user?.email || displayName}
              </div>
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onSignOut && onSignOut();
                }}
                className="w-full rounded-md px-2 py-1.5 text-left text-sm text-gray-700 hover:bg-gray-100"
              >
                Sign out
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
}
