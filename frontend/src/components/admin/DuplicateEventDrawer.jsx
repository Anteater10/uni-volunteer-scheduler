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
//  - sourceEvent — { id, title, quarter, year, week_number, module_slug }
//  - existingEvents — optional array of { id, week_number, year } used to
//      highlight conflict weeks without a round-trip. Parent passes the
//      events visible for the same quarter/module. Safe to omit; backend
//      does the authoritative check.
//  - onSubmit (payload) → Promise<result>
//  - submitting (bool)

import React, { useMemo, useState } from "react";
import SideDrawer from "./SideDrawer";
import { Button, Chip, Label } from "../ui";

const WEEKS_PER_QUARTER = 11;
const QUARTERS = ["winter", "spring", "summer", "fall"];

function isConflictWeek(
  week,
  targetYear,
  targetQuarter,
  existingEvents,
  sourceEvent,
) {
  if (!Array.isArray(existingEvents)) return false;
  return existingEvents.some(
    (e) =>
      e &&
      e.id !== sourceEvent?.id &&
      Number(e.week_number) === week &&
      Number(e.year) === Number(targetYear) &&
      (targetQuarter == null || e.quarter == null || e.quarter === targetQuarter) &&
      (sourceEvent?.module_slug == null ||
        e.module_slug === sourceEvent.module_slug),
  );
}

export default function DuplicateEventDrawer({
  open,
  onClose,
  sourceEvent,
  existingEvents,
  onSubmit,
  submitting = false,
}) {
  const sourceYear = sourceEvent?.year ?? new Date().getFullYear();
  const sourceWeek = sourceEvent?.week_number ?? null;
  const sourceQuarter = sourceEvent?.quarter ?? null;

  const [selectedWeeks, setSelectedWeeks] = useState([]);
  const [targetYear, setTargetYear] = useState(sourceYear);
  const [targetQuarter, setTargetQuarter] = useState(sourceQuarter);
  const [skipConflicts, setSkipConflicts] = useState(true);
  const [submitError, setSubmitError] = useState("");

  // Reset state each time the drawer opens on a fresh source.
  React.useEffect(() => {
    if (!open) return;
    setSelectedWeeks([]);
    setTargetYear(sourceYear);
    setTargetQuarter(sourceQuarter);
    setSkipConflicts(true);
    setSubmitError("");
  }, [open, sourceEvent?.id, sourceYear, sourceQuarter]);

  const crossQuarter =
    targetQuarter != null && sourceQuarter != null && targetQuarter !== sourceQuarter;

  const conflictSet = useMemo(() => {
    const set = new Set();
    for (let w = 1; w <= WEEKS_PER_QUARTER; w += 1) {
      if (
        isConflictWeek(w, targetYear, targetQuarter, existingEvents, sourceEvent)
      ) {
        set.add(w);
      }
    }
    // Source's own week is effectively a conflict when year + quarter match.
    if (
      !crossQuarter &&
      Number(targetYear) === Number(sourceYear) &&
      sourceWeek
    ) {
      set.add(sourceWeek);
    }
    return set;
  }, [
    targetYear,
    targetQuarter,
    existingEvents,
    sourceEvent,
    sourceYear,
    sourceWeek,
    crossQuarter,
  ]);

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
    selectedWeeks.length === 0 ||
    (conflictingSelected.length > 0 && !skipConflicts && creatingCount === 0);

  async function handleSubmit() {
    setSubmitError("");
    if (!sourceEvent) return;
    try {
      await onSubmit({
        target_weeks: selectedWeeks,
        target_year: Number(targetYear),
        target_quarter: targetQuarter || undefined,
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
              {sourceEvent.quarter || "?"}, year {sourceYear}, week{" "}
              {sourceWeek ?? "?"}).
            </p>
          </div>

          <div>
            <Label>Target quarter</Label>
            <div className="flex flex-wrap gap-2 mt-1">
              {QUARTERS.map((q) => (
                <Chip
                  key={q}
                  active={targetQuarter === q}
                  onClick={() => setTargetQuarter(q)}
                  data-testid={`quarter-chip-${q}`}
                >
                  {q.charAt(0).toUpperCase() + q.slice(1)}
                </Chip>
              ))}
            </div>
            {crossQuarter && (
              <p className="text-xs text-amber-700 mt-2">
                Cross-quarter copy: week dates will be shifted to the target
                quarter's calendar. Conflict highlighting uses the target
                quarter; the server re-checks before committing.
              </p>
            )}
          </div>

          <div>
            <Label>Target year</Label>
            <div className="flex gap-2 mt-1">
              {[sourceYear, sourceYear + 1].map((y) => (
                <Chip
                  key={y}
                  active={Number(targetYear) === y}
                  onClick={() => setTargetYear(y)}
                  data-testid={`year-chip-${y}`}
                >
                  {y}
                </Chip>
              ))}
            </div>
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
              {Array.from({ length: WEEKS_PER_QUARTER }, (_, i) => i + 1).map(
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
