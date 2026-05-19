import React from "react";
import {
  FLOWS,
  NODES,
  STATUS_COLORS,
  STATUS_LABELS,
  conceptsForNode,
} from "../../data/appArchitecture";

// vscode://file/<abs path> opens the file in VS Code. The repo root is fixed
// for local dev (this page is admin-only and runs against a developer
// checkout); VITE_REPO_ROOT lets a different machine override it.
const REPO_ROOT =
  import.meta.env.VITE_REPO_ROOT || "/Users/andysubramanian/uni-volunteer-scheduler";

function lectureHref(conceptId) {
  return `vscode://file${REPO_ROOT}/docs/learning/concepts/${conceptId}.md`;
}
function docsHref(conceptId) {
  return `vscode://file${REPO_ROOT}/docs/documentation/concepts/${conceptId}.md`;
}

function ConceptChips({ nodeId }) {
  const concepts = conceptsForNode(nodeId);
  if (!concepts || concepts.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Concepts to study
      </div>
      <ul className="mt-1.5 flex flex-col gap-1.5">
        {concepts.map((c) => (
          <li
            key={c.id}
            className="rounded-md border border-slate-800 bg-slate-900/60 p-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-xs font-semibold text-slate-100">
                {c.title}
              </div>
              <div className="flex shrink-0 gap-2 text-[10px] font-mono">
                <a
                  href={lectureHref(c.id)}
                  className="rounded border border-slate-700 px-1.5 py-0.5 text-sky-300 hover:bg-slate-800"
                  title={`Open docs/learning/${c.id}.md in VS Code`}
                >
                  lecture
                </a>
                <a
                  href={docsHref(c.id)}
                  className="rounded border border-slate-700 px-1.5 py-0.5 text-emerald-300 hover:bg-slate-800"
                  title={`Open docs/documentation/${c.id}.md in VS Code`}
                >
                  docs
                </a>
              </div>
            </div>
            <p className="mt-1 text-[11px] text-slate-400">{c.summary}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatusBadge({ status, size = "sm" }) {
  return (
    <span
      className={[
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-semibold uppercase tracking-wider",
        size === "sm" ? "text-[10px]" : "text-xs",
      ].join(" ")}
      style={{
        backgroundColor: `${STATUS_COLORS[status]}22`,
        color: STATUS_COLORS[status],
        border: `1px solid ${STATUS_COLORS[status]}55`,
      }}
    >
      <span
        className="inline-block h-1.5 w-1.5 rounded-full"
        style={{ backgroundColor: STATUS_COLORS[status] }}
      />
      {STATUS_LABELS[status]}
    </span>
  );
}

function nodeLabel(id) {
  return NODES.find((n) => n.id === id)?.label || id;
}

export default function StepDetails({ selectedFlowId, hoveredNode }) {
  const flow = FLOWS.find((f) => f.id === selectedFlowId);

  if (!flow && !hoveredNode) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
        Hover a node to see its evidence, or pick a flow on the left to walk
        the path step-by-step.
      </div>
    );
  }

  if (!flow && hoveredNode) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="text-sm font-semibold text-slate-100">
              {hoveredNode.label}
            </div>
            <div className="text-xs text-slate-400">{hoveredNode.subtitle}</div>
          </div>
          <StatusBadge status={hoveredNode.status} />
        </div>
        {hoveredNode.statusReason && (
          <p className="mt-3 rounded border border-slate-800 bg-slate-900/60 p-2 text-xs text-slate-300">
            {hoveredNode.statusReason}
          </p>
        )}
        {hoveredNode.evidence && (
          <p className="mt-2 text-xs text-slate-500">
            <span className="font-semibold uppercase tracking-wider">
              Evidence ·{" "}
            </span>
            {hoveredNode.evidence}
          </p>
        )}
        {hoveredNode.relatedFiles && hoveredNode.relatedFiles.length > 0 && (
          <ul className="mt-2 flex flex-col gap-0.5">
            {hoveredNode.relatedFiles.map((f) => (
              <li key={f} className="font-mono text-[11px] text-slate-500">
                {f}
              </li>
            ))}
          </ul>
        )}
        <ConceptChips nodeId={hoveredNode.id} />
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Steps
          </div>
          <div className="text-sm font-semibold text-slate-100">
            {flow.title}
          </div>
        </div>
        <StatusBadge status={flow.status} />
      </div>
      {flow.statusReason && (
        <p className="mt-3 rounded border border-slate-800 bg-slate-900/60 p-2 text-xs text-slate-300">
          {flow.statusReason}
        </p>
      )}
      <ol className="mt-3 flex flex-col gap-2">
        {flow.steps.map((step) => {
          const status = step.status || flow.status;
          return (
            <li
              key={step.number}
              className="flex gap-3 rounded-md border border-slate-800 bg-slate-900/40 p-2"
            >
              <span
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-[11px] font-bold"
                style={{
                  border: `1.5px solid ${STATUS_COLORS[status]}`,
                  color: STATUS_COLORS[status],
                }}
              >
                {step.number}
              </span>
              <div className="flex-1">
                <div className="text-xs text-slate-300">
                  <span className="font-mono text-slate-500">
                    {nodeLabel(step.from)} → {nodeLabel(step.to)}
                  </span>
                </div>
                <div className="text-sm font-medium text-slate-100">
                  {step.label}
                </div>
                {step.description && (
                  <p className="mt-1 text-xs text-slate-400">
                    {step.description}
                  </p>
                )}
                {step.statusReason && (
                  <p className="mt-1 text-[11px] italic text-orange-300">
                    {step.statusReason}
                  </p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
