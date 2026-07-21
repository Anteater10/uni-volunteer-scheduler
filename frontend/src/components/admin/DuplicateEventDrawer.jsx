// src/components/admin/DuplicateEventDrawer.jsx
//
// Phase 23 — Recurring event duplication drawer.
//
// Admin picks target weeks (1..11) within the current or next year, previews
// the batch, and submits. Conflicts are highlighted red; skip-conflicts is
// on by default. Backend enforces atomicity + audit.
//
// Props:
//  - open (bool)
//  - onClose ()
//  - sourceEvent — { id, title, quarter, year, week_number, quarter_id, module_slug }
//  - existingEvents — optional array of { id, week_number, year, quarter_id }
//      used to highlight conflict weeks without a round-trip. Parent passes
//      the events visible for the same quarter/module. Safe to omit; backend
//      does the authoritative check.
//  - quarters — admin-entered quarter rows (from useQuarters). Issue #24:
//      duplication targets a quarter ROW; weeks come from its real length.
//  - onSubmit (payload) → Promise<result>
//  - submitting (bool)

import React, { useMemo, useState } from "react";
import SideDrawer from "./SideDrawer";
import { Button, Chip, Label } from "../ui";
import { activeQuarters, findQuarterById } from "../../lib/weekUtils";

function isConflictWeek(week, targetRow, existingEvents, sourceEvent) {
  if (!Array.isArray(existingEvents) || !targetRow) return false;
  return existingEvents.some((e) => {
    if (!e || e.id === sourceEvent?.id) return false;
    if (
      sourceEvent?.module_slug != null &&
      e.module_slug != null &&
      e.module_slug !== sourceEvent.module_slug
    ) {
      return false;
    }
    if (Number(e.week_number) !== week) return false;
    if (e.quarter_id != null) return e.quarter_id === targetRow.id;
    // Legacy rows without quarter_id: fall back to the (season, year) cache.
    return (
      Number(e.year) === Number(targetRow.year) &&
      (e.quarter == null || e.quarter === targetRow.season)
    );
  });
}

export default function DuplicateEventDrawer({
  open,
  onClose,
  sourceEvent,
  existingEvents,
  quarters,
  onSubmit,
  submitting = false,
}) {
  const sourceWeek = sourceEvent?.week_number ?? null;
  const rows = activeQuarters(quarters || []);

  const [selectedWeeks, setSelectedWeeks] = useState([]);
  const [targetQuarterId, setTargetQuarterId] = useState(
    sourceEvent?.quarter_id ?? null,
  );
  const [skipConflicts, setSkipConflicts] = useState(true);
  const [submitError, setSubmitError] = useState("");

  // Reset state each time the drawer opens on a fresh source.
  React.useEffect(() => {
    if (!open) return;
    setSelectedWeeks([]);
    setTargetQuarterId(sourceEvent?.quarter_id ?? null);
    setSkipConflicts(true);
    setSubmitError("");
  }, [open, sourceEvent?.id, sourceEvent?.quarter_id]);

  const targetRow = findQuarterById(rows, targetQuarterId);
  const weeksCount = targetRow?.weeks_in_quarter ?? 0;
  const crossQuarter = !!(
    targetRow &&
    sourceEvent?.quarter_id &&
    targetRow.id !== sourceEvent.quarter_id
  );

  function selectTargetRow(id) {
    setTargetQuarterId(id);
    setSelectedWeeks([]);
  }

  const conflictSet = useMemo(() => {
    const set = new Set();
    for (let w = 1; w <= weeksCount; w += 1) {
      if (isConflictWeek(w, targetRow, existingEvents, sourceEvent)) {
        set.add(w);
      }
    }
    // Source's own week is effectively a conflict within its own row.
    if (!crossQuarter && sourceWeek && targetRow) {
      set.add(sourceWeek);
    }
    return set;
  }, [weeksCount, targetRow, existingEvents, sourceEvent, sourceWeek, crossQuarter]);

  function toggleWeek(w) {
    setSelectedWeeks((prev) =>
      prev.includes(w) ? prev.filter((x) => x !== w) : [...prev, w].sort((a, b) => a - b),
    );
  }

  const conflictingSelected = selectedWeeks.filter((w) => conflictSet.has(w));
  const creatingCount = selectedWeeks.length - conflictingSelected.length;
  const creatableWeeks = selectedWeeks.filter((w) => !conflictSet.has(w));

  const submitDisabled =
    submitting ||
    !targetRow ||
    selectedWeeks.length === 0 ||
    (conflictingSelected.length > 0 && !skipConflicts && creatingCount === 0);

  async function handleSubmit() {
    setSubmitError("");
    if (!sourceEvent || !targetRow) return;
    try {
      await onSubmit({
        target_weeks: selectedWeeks,
        target_year: Number(targetRow.year),
        target_quarter_id: targetRow.id,
        skip_conflicts: skipConflicts,
      });
    } catch (err) {
      const message =
        err?.response?.data?.detail?.error || err?.message || "Duplicate failed";
      setSubmitError(String(message));
    }
  }

  return (
    <SideDrawer open={open} onClose={onClose} title="Duplicate event">
      {!sourceEvent ? (
        <p className="text-sm text-gray-600">No event selected.</p>
      ) : (
        <div className="space-y-5">
          <div>
            <p className="text-sm">
              Duplicating <strong>{sourceEvent.title}</strong> (
              {sourceEvent.module_slug || "no module"}, quarter{" "}
              {sourceEvent.quarter || "?"}, year {sourceEvent.year ?? "?"}, week{" "}
              {sourceWeek ?? "?"}).
            </p>
          </div>

          <div>
            <Label>Target quarter</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              {rows.map((row) => (
                <Chip
                  key={row.id}
                  active={targetQuarterId === row.id}
                  onClick={() => selectTargetRow(row.id)}
                  data-testid={`quarter-chip-${row.id}`}
                >
                  {row.display_name}
                </Chip>
              ))}
            </div>
            {rows.length === 0 && (
              <p className="text-xs text-amber-700 mt-2">
                No quarters entered yet — add them in Admin → Quarters first.
              </p>
            )}
            {crossQuarter && (
              <p className="text-xs text-amber-700 mt-2">
                Cross-quarter copy: week dates will be shifted to the target
                quarter's calendar. Conflict highlighting uses the target
                quarter; the server re-checks before committing.
              </p>
            )}
          </div>

          <div>
            <Label>Target weeks</Label>
            <p className="text-xs text-[var(--color-fg-muted)] mb-2">
              Pick weeks from this quarter. Red chips already have an event
              for this module.
            </p>
            <div
              className="flex flex-wrap gap-2"
              role="group"
              aria-label="target weeks"
            >
              {Array.from({ length: weeksCount }, (_, i) => i + 1).map(
                (week) => {
                  const conflict = conflictSet.has(week);
                  const selected = selectedWeeks.includes(week);
                  return (
                    <Chip
                      key={week}
                      active={selected}
                      onClick={() => toggleWeek(week)}
                      className={
                        conflict
                          ? "ring-2 ring-red-500 border-red-400"
                          : undefined
                      }
                      aria-label={`Week ${week}${conflict ? " (conflict)" : ""}`}
                      data-testid={`week-chip-${week}`}
                      data-conflict={conflict ? "true" : "false"}
                    >
                      {week}
                      {conflict ? " ⚠" : ""}
                    </Chip>
                  );
                },
              )}
            </div>
          </div>

          <div className="rounded-md bg-gray-50 p-3 text-sm" data-testid="preview">
            {selectedWeeks.length === 0 ? (
              <p className="text-[var(--color-fg-muted)]">
                Select at least one target week.
              </p>
            ) : (
              <p>
                Creating <strong>{creatingCount}</strong> event
                {creatingCount === 1 ? "" : "s"} (weeks{" "}
                {creatableWeeks.join(", ") || "—"})
                {conflictingSelected.length > 0
                  ? `. ${conflictingSelected.length} conflict${
                      conflictingSelected.length === 1 ? "" : "s"
                    } on week${conflictingSelected.length === 1 ? "" : "s"} ${conflictingSelected.join(", ")}${
                      skipConflicts ? " — will be skipped." : " — will cancel the batch."
                    }`
                  : "."}
              </p>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={skipConflicts}
              onChange={(e) => setSkipConflicts(e.target.checked)}
              data-testid="skip-conflicts"
              className="h-5 w-5"
            />
            Skip conflicting weeks (leave existing events alone). Unchecking
            aborts the batch if any conflict is present.
          </label>

          {submitError && (
            <p className="text-sm text-red-600" data-testid="submit-error">
              {submitError}
            </p>
          )}

          <div className="flex gap-2 justify-end pt-2">
            <Button variant="ghost" onClick={onClose} type="button">
              Cancel
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={submitDisabled}
              data-testid="submit"
            >
              {submitting ? "Duplicating…" : "Duplicate"}
            </Button>
          </div>
        </div>
      )}
    </SideDrawer>
  );
}
