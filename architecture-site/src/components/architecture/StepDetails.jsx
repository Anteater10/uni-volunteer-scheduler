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
function repoFileHref(path) {
  return `vscode://file${REPO_ROOT}/${path}`;
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
        "inline-flex max-w-[9.5rem] shrink-0 items-center justify-center gap-1.5 rounded-full px-2 py-0.5 text-center font-semibold uppercase leading-tight tracking-wider whitespace-normal",
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

function stepsForNode(node) {
  return FLOWS.flatMap((flow) =>
    flow.steps
      .filter((step) => step.from === node.id || step.to === node.id)
      .map((step) => ({ flow, step })),
  );
}

function summarizeList(items, limit = 3) {
  if (items.length <= limit) return items;
  return [...items.slice(0, limit), `${items.length - limit} more`];
}

function categoryRole(node) {
  const roles = {
    actor:
      "This is a user role. It represents who starts actions in the system and what product surface they are allowed to reach.",
    client:
      "This is a React screen or UI surface. It gathers user intent, displays server state, and calls API endpoints when the user takes action.",
    api:
      "This is a FastAPI router. It exposes HTTP endpoints, validates request boundaries, applies auth/role dependencies, and hands work to services or database queries.",
    service:
      "This is backend domain logic. It coordinates business rules, transactions, side effects, and calls into data models or external systems.",
    data:
      "This is persistent state. It stores the records that other nodes read from or mutate while completing workflows.",
    external:
      "This is infrastructure or an outside provider. The app depends on it for storage, background jobs, email, AI calls, or deployment plumbing.",
  };

  return roles[node.category] || "This node is one part of the application graph.";
}

function NodePurpose({ node }) {
  const touchedSteps = stepsForNode(node);
  const inbound = touchedSteps.filter(({ step }) => step.to === node.id);
  const outbound = touchedSteps.filter(({ step }) => step.from === node.id);
  const inboundLabels = summarizeList(
    inbound.map(({ step }) => `${nodeLabel(step.from)}: ${step.label}`),
  );
  const outboundLabels = summarizeList(
    outbound.map(({ step }) => `${nodeLabel(step.to)}: ${step.label}`),
  );

  return (
    <div className="mt-3 rounded-md border border-slate-700 bg-slate-900/70 p-3">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        What this node does
      </div>
      <p className="mt-1.5 text-sm leading-5 text-slate-200">
        <span className="font-semibold text-slate-100">{node.label}</span>{" "}
        handles{" "}
        <span className="text-sky-200">{node.subtitle.toLowerCase()}</span>.
        {` ${categoryRole(node)}`}
      </p>
      {node.evidence && (
        <p className="mt-2 text-xs leading-5 text-slate-400">
          {node.evidence}
        </p>
      )}
      <div className="mt-3 grid gap-2">
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Receives
          </div>
          {inboundLabels.length > 0 ? (
            <ul className="mt-1 flex flex-col gap-1">
              {inboundLabels.map((label) => (
                <li key={label} className="text-xs text-slate-300">
                  {label}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-slate-500">
              This is a starting point in the mapped workflows.
            </p>
          )}
        </div>
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Sends / changes
          </div>
          {outboundLabels.length > 0 ? (
            <ul className="mt-1 flex flex-col gap-1">
              {outboundLabels.map((label) => (
                <li key={label} className="text-xs text-slate-300">
                  {label}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-1 text-xs text-slate-500">
              This is an endpoint or storage target in the mapped workflows.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function RelatedFiles({ files }) {
  if (!files || files.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        Implementation files
      </div>
      <ul className="mt-1.5 flex flex-col gap-1.5">
        {files.map((f) => (
          <li key={f}>
            <a
              href={repoFileHref(f)}
              className="block rounded border border-slate-800 bg-slate-900/60 px-2 py-1.5 font-mono text-[11px] text-sky-200 hover:border-slate-600 hover:bg-slate-800"
              title={`Open ${f} in VS Code`}
            >
              {f}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NodeFlowMap({ node }) {
  const matchingFlows = FLOWS.map((flow) => {
    const steps = flow.steps.filter(
      (step) => step.from === node.id || step.to === node.id,
    );
    return { flow, steps };
  }).filter(({ steps }) => steps.length > 0);

  if (matchingFlows.length === 0) return null;

  return (
    <div className="mt-3">
      <div className="text-[10px] font-semibold uppercase tracking-widest text-slate-500">
        How traffic moves through it
      </div>
      <ul className="mt-1.5 flex flex-col gap-2">
        {matchingFlows.map(({ flow, steps }) => (
          <li
            key={flow.id}
            className="rounded-md border border-slate-800 bg-slate-900/50 p-2"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="text-xs font-semibold text-slate-100">
                {flow.title}
              </div>
              <StatusBadge status={flow.status} />
            </div>
            <ol className="mt-2 flex flex-col gap-1.5">
              {steps.map((step) => {
                const direction = step.from === node.id ? "outbound" : "inbound";
                return (
                  <li key={step.number} className="text-[11px] text-slate-400">
                    <span className="font-mono text-slate-500">
                      {step.number}. {nodeLabel(step.from)} →{" "}
                      {nodeLabel(step.to)}
                    </span>
                    <span className="ml-1 rounded border border-slate-700 px-1 text-[10px] uppercase tracking-wide text-slate-500">
                      {direction}
                    </span>
                    <div className="mt-0.5 text-xs font-medium text-slate-200">
                      {step.label}
                    </div>
                    {step.description && (
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        {step.description}
                      </p>
                    )}
                  </li>
                );
              })}
            </ol>
          </li>
        ))}
      </ul>
    </div>
  );
}

function NodeInspector({ node }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Node
          </div>
          <div className="break-words text-sm font-semibold leading-5 text-slate-100">
            {node.label}
          </div>
          <div className="break-words text-xs leading-5 text-slate-400">
            {node.subtitle}
          </div>
        </div>
        <StatusBadge status={node.status} />
      </div>
      {node.statusReason && (
        <p className="mt-3 rounded border border-slate-800 bg-slate-900/60 p-2 text-xs text-slate-300">
          {node.statusReason}
        </p>
      )}
      <NodePurpose node={node} />
      <RelatedFiles files={node.relatedFiles} />
      <NodeFlowMap node={node} />
      <ConceptChips nodeId={node.id} />
    </div>
  );
}

export default function StepDetails({
  activeMode,
  selectedFlowId,
  selectedNode,
}) {
  const flow = FLOWS.find((f) => f.id === selectedFlowId);

  if (activeMode === "nodes") {
    if (!selectedNode) {
      return (
        <div className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
          Pick a node from the dropdown or click one on the map to inspect what
          it does.
        </div>
      );
    }

    return <NodeInspector node={selectedNode} />;
  }

  if (!flow) {
    return (
      <div className="rounded-lg border border-slate-800 bg-slate-950 p-4 text-sm text-slate-400">
        Pick a workflow to walk the path step-by-step.
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">
            Workflow
          </div>
          <div className="break-words text-sm font-semibold leading-5 text-slate-100">
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
              <div className="min-w-0 flex-1">
                <div className="break-words text-xs text-slate-300">
                  <span className="font-mono text-slate-500">
                    {nodeLabel(step.from)} → {nodeLabel(step.to)}
                  </span>
                </div>
                <div className="break-words text-sm font-medium text-slate-100">
                  {step.label}
                </div>
                {step.description && (
                  <p className="mt-1 break-words text-xs leading-5 text-slate-400">
                    {step.description}
                  </p>
                )}
                {step.statusReason && (
                  <p className="mt-1 break-words text-[11px] italic text-orange-300">
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
