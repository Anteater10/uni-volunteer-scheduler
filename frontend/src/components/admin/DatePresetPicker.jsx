import React, { useMemo } from "react";
import { currentQuarter } from "../../lib/quarter";

const LABELS = {
  "24h": "Last 24h",
  "7d": "Last 7d",
  "30d": "Last 30d",
  quarter: "This quarter",
  custom: "Custom range",
};

function isoDaysAgo(days, now = new Date()) {
  return new Date(now.getTime() - days * 24 * 3600 * 1000).toISOString();
}

/**
 * Compute {from, to} ISO strings for a given preset.
 * Exported for tests and reuse.
 */
export function rangeForPreset(preset, now = new Date()) {
  if (preset === "24h") return { from: isoDaysAgo(1, now), to: now.toISOString() };
  if (preset === "7d") return { from: isoDaysAgo(7, now), to: now.toISOString() };
  if (preset === "30d") return { from: isoDaysAgo(30, now), to: now.toISOString() };
  if (preset === "quarter") {
    const { start, end } = currentQuarter(now);
    return { from: start.toISOString(), to: end.toISOString() };
  }
  return { from: null, to: null };
}

/**
 * DatePresetPicker
 * Props:
 *  - value: { preset, from?, to? }
 *  - onChange: ({ preset, from, to }) => void
 *  - presets: Array<"24h"|"7d"|"30d"|"quarter"|"custom">
 */
export default function DatePresetPicker({
  value = { preset: "7d" },
  onChange,
  presets = ["24h", "7d", "30d", "quarter", "custom"],
}) {
  const current = value?.preset || presets[0];

  function selectPreset(p) {
    if (!onChange) return;
    if (p === "custom") {
      onChange({ preset: "custom", from: value?.from || "", to: value?.to || "" });
      return;
    }
    const { from, to } = rangeForPreset(p);
    onChange({ preset: p, from, to });
  }

  function onCustomChange(field, v) {
    if (!onChange) return;
    const next = {
      preset: "custom",
      from: value?.from || "",
      to: value?.to || "",
      [field]: v ? new Date(v).toISOString() : "",
    };
    onChange(next);
  }

  const customFromValue = useMemo(
    () => (value?.from ? value.from.slice(0, 10) : ""),
    [value?.from],
  );
  const customToValue = useMemo(
    () => (value?.to ? value.to.slice(0, 10) : ""),
    [value?.to],
  );

  return (
    <div className="flex flex-col gap-2">
      <div
        role="group"
        aria-label="Date range presets"
        className="inline-flex rounded-lg border border-gray-200 bg-white p-1"
      >
        {presets.map((p) => {
          const active = current === p;
          return (
            <button
              key={p}
              type="button"
              onClick={() => selectPreset(p)}
              aria-pressed={active}
              className={`px-3 py-1 text-sm rounded-md transition-colors ${
                active
                  ? "bg-gray-900 text-white"
                  : "text-gray-700 hover:bg-gray-100"
              }`}
            >
              {LABELS[p] || p}
            </button>
          );
        })}
      </div>
      {current === "custom" ? (
        <div className="flex items-center gap-2 text-sm">
          <label className="flex items-center gap-1">
            From
            <input
              type="date"
              value={customFromValue}
              onChange={(e) => onCustomChange("from", e.target.value)}
              className="rounded-md border border-gray-300 px-2 py-1"
            />
          </label>
          <label className="flex items-center gap-1">
            To
            <input
              type="date"
              value={customToValue}
              onChange={(e) => onCustomChange("to", e.target.value)}
              className="rounded-md border border-gray-300 px-2 py-1"
            />
          </label>
        </div>
      ) : null}
    </div>
  );
}
