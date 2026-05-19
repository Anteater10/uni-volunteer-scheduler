import React from "react";
import {
  STATUS_LABELS,
  STATUS_COLORS,
  CATEGORIES,
} from "../../data/appArchitecture";

export default function Legend() {
  const statuses = Object.keys(STATUS_LABELS);
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-300">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {statuses.map((s) => (
          <span key={s} className="inline-flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[s] }}
              aria-hidden
            />
            <span>{STATUS_LABELS[s]}</span>
          </span>
        ))}
      </div>
      <div className="text-slate-500">·</div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        {CATEGORIES.map((c) => (
          <span
            key={c.id}
            className="inline-flex items-center gap-1.5 text-slate-400"
          >
            <span className="rounded border border-slate-700 bg-slate-800/60 px-1.5 py-0.5 text-[10px] uppercase tracking-wider">
              {c.label}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}
