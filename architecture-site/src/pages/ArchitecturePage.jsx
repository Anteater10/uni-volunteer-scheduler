// Standalone architecture page.
//
// Renders the audited graph from src/data/appArchitecture.js as an interactive
// SVG diagram with selectable flows, dimming, step details, status filters,
// and per-node concept chips that link out to lecture/docs markdown files.
//
// Dark theme is intentional and baked in — this site is meant to stand on
// its own (e.g. on a personal portfolio) and does not depend on any
// surrounding app shell.

import React, { useCallback, useEffect, useState } from "react";
import { architecture } from "../data/appArchitecture";
import FlowDiagram from "../components/architecture/FlowDiagram";
import FlowSidebar from "../components/architecture/FlowSidebar";
import StepDetails from "../components/architecture/StepDetails";
import Legend from "../components/architecture/Legend";
import SummaryBar from "../components/architecture/SummaryBar";

export default function ArchitecturePage() {
  useEffect(() => {
    document.title = `${architecture.title} · uni-volunteer-scheduler`;
  }, []);

  const [selectedFlowId, setSelectedFlowId] = useState(
    () => architecture.flows[0]?.id ?? null,
  );
  const [hoveredNode, setHoveredNode] = useState(null);
  const [statusFilter, setStatusFilter] = useState(() => new Set());

  const toggleStatus = useCallback((status) => {
    setStatusFilter((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  }, []);

  const handleNodeActivate = useCallback((node) => {
    setHoveredNode(node);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 px-4 py-6 text-slate-100 md:px-8 md:py-8">
      <header className="mb-4 flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight md:text-3xl">
          {architecture.title}
        </h1>
        <p className="max-w-3xl text-sm text-slate-400">
          {architecture.subtitle}
        </p>
        <div className="mt-2 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <Legend />
          <SummaryBar
            statusFilter={statusFilter}
            onToggleStatus={toggleStatus}
          />
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <FlowDiagram
          selectedFlowId={selectedFlowId}
          statusFilter={statusFilter}
          onNodeHover={setHoveredNode}
          onNodeActivate={handleNodeActivate}
        />
        <div className="flex flex-col gap-4">
          <FlowSidebar
            selectedFlowId={selectedFlowId}
            onSelect={setSelectedFlowId}
          />
          <StepDetails
            selectedFlowId={selectedFlowId}
            hoveredNode={hoveredNode}
          />
        </div>
      </div>

      <footer className="mt-6 text-xs text-slate-500">
        Status derived from the project's planning notes + direct repo audit.
        Concept chips link to long-form lectures in{" "}
        <span className="font-mono">docs/learning/concepts/</span> and
        reference docs in{" "}
        <span className="font-mono">docs/documentation/concepts/</span>.
      </footer>
    </div>
  );
}
