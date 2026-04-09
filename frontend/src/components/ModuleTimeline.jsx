import React from "react";
import { Link } from "react-router-dom";

// TODO(brand): finalize icons and colors with Sci Trek
const STATUS_CONFIG = {
  locked: {
    icon: "\u{1F512}",  // lock
    label: "Locked",
    className: "opacity-50",
    badgeClass: "bg-gray-200 text-gray-600",
  },
  unlocked: {
    icon: "\u{1F513}",  // unlock
    label: "Unlocked",
    className: "",
    badgeClass: "bg-blue-100 text-blue-700",
  },
  completed: {
    icon: "\u2705",     // checkmark
    label: "Completed",
    className: "",
    badgeClass: "bg-green-100 text-green-700",
  },
};

function formatRelativeDate(dateStr) {
  if (!dateStr) return null;
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 30) return `${diffDays} days ago`;
  return date.toLocaleDateString();
}

export default function ModuleTimeline({ modules }) {
  if (!modules || modules.length === 0) {
    return null;
  }

  return (
    <ul className="space-y-2" role="list">
      {modules.map((mod) => {
        const config = STATUS_CONFIG[mod.status] || STATUS_CONFIG.locked;
        return (
          <li
            key={mod.slug}
            className={`rounded-xl border border-[var(--color-border)] p-3 flex items-center gap-3 ${config.className}`}
          >
            <span className="text-xl" aria-hidden="true">
              {config.icon}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {mod.status === "locked" ? (
                  <Link
                    to="/events?module=orientation"
                    className="text-sm font-medium underline"
                  >
                    {mod.name}
                  </Link>
                ) : (
                  <span className="text-sm font-medium">{mod.name}</span>
                )}
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${config.badgeClass}`}
                >
                  {config.label}
                </span>
                {mod.override_active && (
                  <span className="text-xs px-2 py-0.5 rounded-full font-medium bg-amber-100 text-amber-700">
                    Override active
                  </span>
                )}
              </div>
              {mod.last_activity && (
                <p className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                  Last activity: {formatRelativeDate(mod.last_activity)}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
