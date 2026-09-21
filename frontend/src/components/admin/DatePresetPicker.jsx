import React, { useMemo } from "react";
import { activeOrRecentQuarter, previousQuarter } from "../../lib/weekUtils";

// L4 #41/C: "last-quarter" and "last-12-months" were offered by the Exports
// screen but had no entry here, so their buttons rendered their raw keys as
// labels — "last-quarter" — and rangeForPreset fell through to {null, null},
// which the export reads as "no filter". Two buttons that looked like date
// filters silently downloaded every record ever, PII included.
const LABELS = {
  "24h": "Last 24h",
  "7d": "Last 7d",
  "30d": "Last 30d",
  quarter: "This quarter",
  "last-quarter": "Last quarter",
  "last-12-months": "Last 12 months",
  custom: "Custom range",
};

function isoDaysAgo(days, now = new Date()) {
  return new Date(now.getTime() - days * 24 * 3600 * 1000).toISOString();
}

/**
 * Compute {from, to} ISO strings for a given preset.
 * Exported for tests and reuse.
 *
 * Issue #24: the "quarter" preset derives from the admin-entered quarter
 * rows (pass them as the third argument) — the row covering `now`, else the
 * most recently ended one. Empty range when no quarters are entered.
 */
export function rangeForPreset(preset, now = new Date(), quarters = []) {
  if (preset === "24h") return { from: isoDaysAgo(1, now), to: now.toISOString() };
  if (preset === "7d") return { from: isoDaysAgo(7, now), to: now.toISOString() };
  if (preset === "30d") return { from: isoDaysAgo(30, now), to: now.toISOString() };
  if (preset === "last-12-months") {
    return { from: isoDaysAgo(365, now), to: now.toISOString() };
  }
  if (preset === "quarter" || preset === "last-quarter") {
    const row =
      preset === "quarter"
        ? activeOrRecentQuarter(quarters, now)
        : previousQuarter(quarters, now);
    if (!row) return { from: null, to: null };
    const from = new Date(`${row.start_date}T00:00:00Z`);
    // end_date is inclusive; the exclusive filter bound is the next midnight.
    const to = new Date(new Date(`${row.end_date}T00:00:00Z`).getTime() + 24 * 3600 * 1000);
    return { from: from.toISOString(), to: to.toISOString() };
  }
  return { from: null, to: null };
}

/**
 * DatePresetPicker
 * Props:
 *  - value: { preset, from?, to? }
 *  - onChange: ({ preset, from, to }) => void
 *  - presets: Array<"24h"|"7d"|"30d"|"quarter"|"last-quarter"|"last-12-months"|"custom">
 *  - quarters: admin-entered quarter rows (from useQuarters). The quarter-derived
 *      presets are hidden when they cannot resolve to a real range.
 */
export default function DatePresetPicker({
  value = { preset: "7d" },
  onChange,
  presets = ["24h", "7d", "30d", "quarter", "custom"],
  quarters = null,
}) {
  // A quarter preset that cannot resolve a range returns {null, null}, which
  // the exports read as "no filter" — the whole point of L4 #41 is that a
  // button labelled with a date range must never quietly mean "everything".
  // "quarter" was already hidden without quarter rows; "last-quarter" needs
  // the stronger test, since rows can exist with none of them yet ended.
  const hasQuarters = Array.isArray(quarters) && quarters.length > 0;
  const hasPreviousQuarter =
    hasQuarters && previousQuarter(quarters, new Date()) !== null;
  const visiblePresets = presets.filter((p) => {
    if (p === "quarter") return hasQuarters;
    if (p === "last-quarter") return hasPreviousQuarter;
    return true;
  });
  const current = value?.preset || visiblePresets[0];

  function selectPreset(p) {
    if (!onChange) return;
    if (p === "custom") {
      onChange({ preset: "custom", from: value?.from || "", to: value?.to || "" });
      return;
    }
    const { from, to } = rangeForPreset(p, new Date(), quarters || []);
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
        {visiblePresets.map((p) => {
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
