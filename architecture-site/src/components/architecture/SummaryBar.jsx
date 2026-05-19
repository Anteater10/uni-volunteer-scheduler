import React, { useMemo } from "react";
import {
  STATUS_COLORS,
  STATUS_LABELS,
  summaryCounts,
  NODES,
  FLOWS,
} from "../../data/appArchitecture";

export default function SummaryBar({ statusFilter, onToggleStatus }) {
  // Inputs are module-level constants — memoise once per mount.
  const counts = useMemo(() => summaryCounts(NODES, FLOWS), []);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      {(["working", "partial", "broken", "unknown"]).map((s) => {
        const active = !statusFilter || statusFilter.size === 0 || statusFilter.has(s);
        return (
          <button
            key={s}
            type="button"
            onClick={() => onToggleStatus(s)}
            className={[
              "flex items-center gap-2 rounded-md border px-2.5 py-1 transition-colors",
              active
                ? "border-slate-700 bg-slate-900 text-slate-200"
                : "border-slate-800 bg-slate-950 text-slate-600",
            ].join(" ")}
            aria-pressed={active}
          >
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: STATUS_COLORS[s] }}
            />
            <span className="font-medium">{STATUS_LABELS[s]}</span>
            <span className="font-mono text-slate-500">
              {counts.nodes[s]}n · {counts.flows[s]}f · {counts.edges[s]}e
            </span>
          </button>
        );
      })}
      <div className="ml-2 text-slate-500">
        Total · <span className="font-mono">{counts.nodes.total}</span> nodes ·{" "}
        <span className="font-mono">{counts.flows.total}</span> flows ·{" "}
        <span className="font-mono">{counts.edges.total}</span> edges
      </div>
    </div>
  );
}
