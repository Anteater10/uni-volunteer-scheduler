import React from "react";
import {
  FLOWS,
  STATUS_LABELS,
  STATUS_COLORS,
} from "../../data/appArchitecture";

function StatusPill({ status }) {
  return (
    <span
      className="inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{
        backgroundColor: `${STATUS_COLORS[status]}22`,
        color: STATUS_COLORS[status],
        border: `1px solid ${STATUS_COLORS[status]}55`,
      }}
    >
      {STATUS_LABELS[status]}
    </span>
  );
}

export default function FlowSidebar({ selectedFlowId, onSelect }) {
  return (
    <aside className="flex h-full flex-col gap-2 overflow-y-auto rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="flex items-center justify-between px-1 pb-1">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Flows
        </h2>
        {selectedFlowId && (
          <button
            type="button"
            aria-label="Clear selected flow"
            className="text-xs text-slate-400 underline-offset-2 hover:text-slate-200 hover:underline focus:outline-none focus:ring-2 focus:ring-slate-500 focus:rounded"
            onClick={() => onSelect(null)}
          >
            Clear selection
          </button>
        )}
      </div>
      <ul className="flex flex-col gap-1.5">
        {FLOWS.map((flow) => {
          const active = flow.id === selectedFlowId;
          return (
            <li key={flow.id}>
              <button
                type="button"
                onClick={() => onSelect(active ? null : flow.id)}
                className={[
                  "block w-full rounded-md border px-3 py-2 text-left transition-colors",
                  active
                    ? "border-slate-500 bg-slate-800/80"
                    : "border-slate-800 bg-slate-900 hover:bg-slate-800/60",
                ].join(" ")}
                aria-pressed={active}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="text-sm font-semibold text-slate-100">
                    {flow.title}
                  </div>
                  <StatusPill status={flow.status} />
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {flow.description}
                </p>
              </button>
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
