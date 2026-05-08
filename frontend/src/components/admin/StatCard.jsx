import React from "react";

/**
 * StatCard — big headline metric tile.
 *
 * Props:
 *  - label: string
 *  - value: string | number
 *  - explainer: optional string (one plain-English sentence)
 *  - subline: optional string (e.g. "This quarter: 12")
 *  - trend: optional { delta: number | string, direction: "up" | "down" | "flat" }
 */
export default function StatCard({ label, value, explainer, subline, trend }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="text-4xl font-bold text-gray-900">{value}</div>
        {trend && trend.delta !== undefined && trend.delta !== null ? (
          <TrendChip delta={trend.delta} direction={trend.direction} />
        ) : null}
      </div>
      <div className="mt-1 text-sm font-medium text-gray-700">{label}</div>
      {explainer ? (
        <p className="mt-2 text-sm text-gray-600">{explainer}</p>
      ) : null}
      {subline ? (
        <div className="mt-2 text-xs text-gray-500">{subline}</div>
      ) : null}
    </div>
  );
}

function TrendChip({ delta, direction }) {
  const dir = direction || (typeof delta === "number" ? (delta > 0 ? "up" : delta < 0 ? "down" : "flat") : "flat");
  const arrow = dir === "up" ? "↑" : dir === "down" ? "↓" : "→";
  const cls =
    dir === "up"
      ? "bg-green-100 text-green-800"
      : dir === "down"
      ? "bg-red-100 text-red-800"
      : "bg-gray-100 text-gray-700";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${cls}`}>
      {arrow} {typeof delta === "number" ? Math.abs(delta) : delta}
    </span>
  );
}
