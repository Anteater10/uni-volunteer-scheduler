import React, { useMemo } from "react";
import {
  NODES,
  FLOWS,
  STATUS,
  STATUS_COLORS,
  STATUS_LABELS,
  deriveEdges,
} from "../../data/appArchitecture";
import {
  curvedConnector,
  diagramSize,
  nodePosition,
  COL_GAP,
  NODE_W,
  PAD_X,
} from "./layout";

// ---------------------------------------------------------------------------
// SVG marker definitions (one arrow per status colour so paths don't share
// fills) and a tiny set of glyphs that supplement the colour-only status dot
// so the diagram remains legible for colour-blind users and screen readers.
// ---------------------------------------------------------------------------
function ArrowMarkers() {
  return (
    <defs>
      {Object.entries(STATUS_COLORS).map(([status, color]) => (
        <marker
          key={status}
          id={`arrow-${status}`}
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="6"
          markerHeight="6"
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
        </marker>
      ))}
    </defs>
  );
}

const STATUS_GLYPH = {
  [STATUS.WORKING]: "✓",
  [STATUS.PARTIAL]: "!",
  [STATUS.BROKEN]: "✕",
  [STATUS.UNKNOWN]: "?",
};

function ColumnHeaders({ columns, height }) {
  return columns.map((c) => {
    const x = PAD_X + (c.col - 1) * (NODE_W + COL_GAP);
    return (
      <g key={c.col}>
        <text
          x={x}
          y={18}
          fill="#64748b"
          fontSize="11"
          fontWeight="600"
          letterSpacing="2"
        >
          {c.label}
        </text>
        <line
          x1={x - 8}
          y1={24}
          x2={x - 8}
          y2={height - 8}
          stroke="#1e293b"
          strokeDasharray="2 4"
          strokeWidth="1"
        />
      </g>
    );
  });
}

function NodeRect({ node, dim, selected, onActivate, onHover, onLeave }) {
  const pos = nodePosition(node);
  const color = STATUS_COLORS[node.status];
  const opacity = dim ? 0.18 : 1;
  const glyph = STATUS_GLYPH[node.status];
  const ariaLabel = `${node.label}. ${node.subtitle}. Status: ${
    STATUS_LABELS[node.status]
  }.`;

  function handleKeyDown(e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onActivate?.(node);
    }
  }

  return (
    <g
      transform={`translate(${pos.x},${pos.y})`}
      opacity={opacity}
      tabIndex={dim ? -1 : 0}
      role="button"
      aria-label={ariaLabel}
      onMouseEnter={() => onHover?.(node)}
      onMouseLeave={() => onLeave?.()}
      onFocus={() => onHover?.(node)}
      onBlur={() => onLeave?.()}
      onClick={() => onActivate?.(node)}
      onKeyDown={handleKeyDown}
      style={{ cursor: onActivate ? "pointer" : "default" }}
      className="arch-node focus:outline-none focus-visible:[&>rect]:!stroke-white focus-visible:[&>rect]:!stroke-[3]"
    >
      <rect
        rx="8"
        ry="8"
        width={pos.w}
        height={pos.h}
        fill="#0f172a"
        stroke={color}
        strokeWidth={selected ? 2.5 : 1.5}
        style={
          selected
            ? { filter: `drop-shadow(0 0 6px ${color}aa)` }
            : undefined
        }
      />
      <text x="12" y="22" fill="#e2e8f0" fontSize="13" fontWeight="600">
        {node.label}
      </text>
      <text x="12" y="40" fill="#64748b" fontSize="11">
        {node.subtitle}
      </text>
      {/* status dot + glyph (so status survives colour blindness / mono) */}
      <g aria-hidden="true">
        <circle cx={pos.w - 14} cy={14} r={7} fill={color} />
        <text
          x={pos.w - 14}
          y={14}
          dy="4"
          textAnchor="middle"
          fill="#020617"
          fontSize="10"
          fontWeight="800"
        >
          {glyph}
        </text>
      </g>
    </g>
  );
}

function Edge({ edge, fromNode, toNode, dim, selected, stepNumber }) {
  if (!fromNode || !toNode) return null;
  const { path, midX, midY } = curvedConnector(fromNode, toNode);
  const color = STATUS_COLORS[edge.status];
  const opacity = dim ? 0.08 : selected ? 1 : 0.55;
  const strokeWidth = selected ? 2.4 : 1.4;

  return (
    <g opacity={opacity} aria-hidden="true">
      <path
        d={path}
        fill="none"
        stroke={color}
        strokeWidth={strokeWidth}
        markerEnd={`url(#arrow-${edge.status})`}
        style={
          selected ? { filter: `drop-shadow(0 0 4px ${color}aa)` } : undefined
        }
      />
      {selected && stepNumber != null && (
        <g transform={`translate(${midX},${midY})`}>
          <circle r="11" fill="#020617" stroke={color} strokeWidth="2" />
          <text
            textAnchor="middle"
            dy="4"
            fill={color}
            fontSize="11"
            fontWeight="700"
          >
            {stepNumber}
          </text>
        </g>
      )}
    </g>
  );
}

export default function FlowDiagram({
  selectedFlowId,
  statusFilter,
  onNodeHover,
  onNodeActivate,
}) {
  const edges = useMemo(() => deriveEdges(FLOWS), []);
  const nodeIndex = useMemo(() => {
    const m = new Map();
    for (const n of NODES) m.set(n.id, n);
    return m;
  }, []);
  const { width, height } = useMemo(() => diagramSize(NODES), []);

  const selectedFlow = FLOWS.find((f) => f.id === selectedFlowId) || null;

  const { selectedNodes, selectedEdges, stepNumberByEdge } = useMemo(() => {
    if (!selectedFlow) {
      return {
        selectedNodes: null,
        selectedEdges: null,
        stepNumberByEdge: new Map(),
      };
    }
    const nodeSet = new Set();
    const edgeSet = new Set();
    const numberMap = new Map();
    for (const step of selectedFlow.steps) {
      nodeSet.add(step.from);
      nodeSet.add(step.to);
      const key = `${step.from}→${step.to}`;
      edgeSet.add(key);
      if (!numberMap.has(key)) numberMap.set(key, step.number);
    }
    return {
      selectedNodes: nodeSet,
      selectedEdges: edgeSet,
      stepNumberByEdge: numberMap,
    };
  }, [selectedFlow]);

  function nodeMatchesFilter(n) {
    if (!statusFilter || statusFilter.size === 0) return true;
    return statusFilter.has(n.status);
  }
  function edgeMatchesFilter(e) {
    if (!statusFilter || statusFilter.size === 0) return true;
    return statusFilter.has(e.status);
  }
  function isNodeDim(n) {
    if (selectedNodes && !selectedNodes.has(n.id)) return true;
    if (!nodeMatchesFilter(n)) return true;
    return false;
  }
  function isEdgeDim(e) {
    if (selectedEdges && !selectedEdges.has(e.id)) return true;
    if (!edgeMatchesFilter(e)) return true;
    return false;
  }

  return (
    <div className="overflow-auto rounded-lg border border-slate-800 bg-slate-950">
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label="App architecture diagram — focus a node with Tab and press Enter to open its lesson."
      >
        <ArrowMarkers />
        <ColumnHeaders
          columns={[
            { col: 1, label: "ACTORS" },
            { col: 2, label: "CLIENT" },
            { col: 3, label: "API" },
            { col: 4, label: "SERVICES" },
            { col: 5, label: "DATA" },
            { col: 6, label: "INFRA / EXT" },
          ]}
          height={height}
        />

        {edges.map((e) => (
          <Edge
            key={e.id}
            edge={e}
            fromNode={nodeIndex.get(e.from)}
            toNode={nodeIndex.get(e.to)}
            dim={isEdgeDim(e)}
            selected={selectedEdges?.has(e.id) || false}
            stepNumber={stepNumberByEdge.get(e.id)}
          />
        ))}

        {NODES.map((n) => (
          <NodeRect
            key={n.id}
            node={n}
            dim={isNodeDim(n)}
            selected={selectedNodes?.has(n.id) || false}
            onHover={onNodeHover}
            onLeave={() => onNodeHover?.(null)}
            onActivate={onNodeActivate}
          />
        ))}
      </svg>
    </div>
  );
}
