import React from "react";
import {
  FLOWS,
  NODES,
  STATUS_COLORS,
  STATUS_LABELS,
} from "../../data/appArchitecture";

function StatusPill({ status }) {
  return (
    <span
      className="inline-flex max-w-full shrink-0 items-center justify-center rounded-full px-2 py-0.5 text-center text-[10px] font-semibold uppercase leading-tight tracking-wide whitespace-normal"
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

function ModeButton({ active, children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={[
        "min-w-0 flex-1 rounded-md px-3 py-2 text-sm font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-slate-500",
        active
          ? "bg-slate-100 text-slate-950"
          : "bg-slate-900 text-slate-300 hover:bg-slate-800",
      ].join(" ")}
    >
      {children}
    </button>
  );
}

export default function FlowSidebar({
  activeMode,
  onModeChange,
  selectedFlowId,
  onSelectFlow,
  selectedNodeId,
  onSelectNode,
}) {
  const selectedFlow = FLOWS.find((flow) => flow.id === selectedFlowId);
  const selectedNode = NODES.find((node) => node.id === selectedNodeId);
  const showingWorkflows = activeMode === "workflows";
  const selectedStatus = showingWorkflows
    ? selectedFlow?.status
    : selectedNode?.status;

  return (
    <aside className="rounded-lg border border-slate-800 bg-slate-950 p-3">
      <div className="grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-900/50 p-1">
        <ModeButton
          active={showingWorkflows}
          onClick={() => onModeChange("workflows")}
        >
          Workflows
        </ModeButton>
        <ModeButton
          active={activeMode === "nodes"}
          onClick={() => onModeChange("nodes")}
        >
          Nodes
        </ModeButton>
      </div>

      <label
        htmlFor="architecture-inspector-picker"
        className="mt-3 block text-[10px] font-semibold uppercase tracking-widest text-slate-500"
      >
        {showingWorkflows ? "Choose workflow" : "Choose node"}
      </label>
      <select
        id="architecture-inspector-picker"
        value={showingWorkflows ? selectedFlowId || "" : selectedNodeId || ""}
        onChange={(event) => {
          if (showingWorkflows) onSelectFlow(event.target.value);
          else onSelectNode(event.target.value);
        }}
        className="mt-1.5 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-700"
      >
        {!showingWorkflows && <option value="">Pick a node</option>}
        {(showingWorkflows ? FLOWS : NODES).map((item) => (
          <option key={item.id} value={item.id}>
            {item.label || item.title}
          </option>
        ))}
      </select>

      {(selectedFlow || selectedNode) && (
        <div className="mt-3 rounded-md border border-slate-800 bg-slate-900/50 p-3">
          <div className="flex min-w-0 items-start justify-between gap-2">
            <div className="min-w-0">
              <div className="break-words text-sm font-semibold leading-5 text-slate-100">
                {showingWorkflows ? selectedFlow.title : selectedNode.label}
              </div>
              <p className="mt-1 break-words text-xs leading-5 text-slate-400">
                {showingWorkflows
                  ? selectedFlow.description
                  : selectedNode.subtitle}
              </p>
            </div>
            {selectedStatus && <StatusPill status={selectedStatus} />}
          </div>
        </div>
      )}
    </aside>
  );
}
