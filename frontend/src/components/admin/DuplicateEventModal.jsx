import React, { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { api } from "../../lib/api";
import { toast } from "../../state/toast";
import FormModal from "./FormModal";
import { EventForm, slotFormToApiPayload } from "../../pages/admin/EventsSection";
import { activeQuarters, findQuarterById } from "../../lib/weekUtils";
import {
  buildDuplicateInitial,
  computeShiftDays,
  defaultTargetQuarterId,
  defaultTargetWeek,
  weekRangeLabel,
} from "../../lib/duplicateEvent";

const FIELD =
  "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white";
const LABEL =
  "block text-sm font-medium text-[var(--color-fg)] mb-1.5";

/**
 * DuplicateEventModal — duplicate is a prefilled create form.
 *
 * The old drawer batch-cloned an event into week chips with a mechanical
 * date shift: rooms, days, and times were copied blind, which is exactly
 * what changes between quarters. Here the admin picks where the copy lands
 * (target quarter + week), gets the whole event form prefilled with the
 * shifted values as suggestions, edits anything — dates per slot, rooms,
 * capacity — and creates through the ordinary POST /events/ path. The
 * server copies what the form can't carry (signup-form override, reminder
 * toggle, shifted signup window) via source_event_id.
 *
 * Props:
 *  - open, onClose
 *  - sourceEvent: full event (api.events.get / list row — includes slots)
 *  - quarters: admin-entered quarter rows (useQuarters), archived included
 */
export default function DuplicateEventModal({ open, onClose, sourceEvent, quarters }) {
  const qc = useQueryClient();
  const navigate = useNavigate();

  const rows = activeQuarters(quarters || []);
  const sourceRow = findQuarterById(quarters || [], sourceEvent?.quarter_id);

  const [targetQuarterId, setTargetQuarterId] = useState(null);
  const [targetWeek, setTargetWeek] = useState(1);

  // Re-derive the default target each time the modal opens on a source.
  React.useEffect(() => {
    if (!open || !sourceEvent) return;
    const pad = (n) => String(n).padStart(2, "0");
    const now = new Date();
    const todayIso = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
    const qid = defaultTargetQuarterId(quarters || [], todayIso);
    setTargetQuarterId(qid);
    const row = findQuarterById(quarters || [], qid);
    setTargetWeek(
      row ? defaultTargetWeek({ sourceEvent, sourceRow, targetRow: row }) : 1,
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, sourceEvent?.id, quarters]);

  const targetRow = findQuarterById(rows, targetQuarterId);

  function selectTargetRow(id) {
    setTargetQuarterId(id);
    const row = findQuarterById(rows, id);
    if (row) {
      setTargetWeek(defaultTargetWeek({ sourceEvent, sourceRow, targetRow: row }));
    }
  }

  const initial = useMemo(() => {
    if (!sourceEvent || !targetRow) return null;
    const shiftDays = computeShiftDays({
      sourceEvent,
      sourceRow,
      targetRow,
      targetWeek,
    });
    return buildDuplicateInitial(sourceEvent, shiftDays);
  }, [sourceEvent, sourceRow, targetRow, targetWeek]);

  // Advisory only: the same module in the same target week is usually a
  // sign the copy already happened, but a second run can be legitimate —
  // the admin is looking at the full form and decides.
  const conflictsQ = useQuery({
    queryKey: [
      "duplicateConflicts",
      targetRow?.id,
      targetWeek,
      sourceEvent?.module_slug,
    ],
    enabled: Boolean(open && targetRow && targetWeek),
    queryFn: () =>
      api.public.listEvents({ quarter_id: targetRow.id, week_number: targetWeek }),
  });
  const conflicts = (conflictsQ.data || []).filter(
    (e) =>
      e.id !== sourceEvent?.id &&
      (!sourceEvent?.module_slug || e.module_slug === sourceEvent.module_slug),
  );

  const createM = useMutation({
    mutationFn: ({ metadata, slots }) =>
      api.events.create({
        ...metadata,
        source_event_id: sourceEvent.id,
        slots: slots.map(slotFormToApiPayload),
      }),
    onSuccess: (created) => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      toast.success(
        `Event created in ${targetRow?.display_name || "the target quarter"}, week ${targetWeek}.`,
      );
      onClose();
      if (created?.id) navigate(`/admin/events/${created.id}`);
    },
    onError: (e) => toast.error(e?.message || "Duplicate failed"),
  });

  if (!open || !sourceEvent) return null;

  return (
    <FormModal
      open={open}
      title={`Duplicate "${sourceEvent.title}"`}
      subtitle="Pick where the copy lands. Everything below is prefilled from the original — adjust dates, rooms, and slots before creating."
      onClose={onClose}
    >
      <div className="space-y-6">
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className={LABEL} htmlFor="duplicate-target-quarter">
                Target quarter
              </label>
              <select
                id="duplicate-target-quarter"
                aria-label="Target quarter"
                value={targetQuarterId || ""}
                onChange={(e) => selectTargetRow(e.target.value)}
                className={FIELD}
              >
                {rows.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.display_name || `${row.season} ${row.year}`}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className={LABEL} htmlFor="duplicate-target-week">
                Target week
              </label>
              <select
                id="duplicate-target-week"
                aria-label="Target week"
                value={String(targetWeek)}
                onChange={(e) => setTargetWeek(Number(e.target.value))}
                className={FIELD}
                disabled={!targetRow}
              >
                {Array.from(
                  { length: targetRow?.weeks_in_quarter || 0 },
                  (_, i) => i + 1,
                ).map((week) => (
                  <option key={week} value={String(week)}>
                    Week {week} ({weekRangeLabel(targetRow, week)})
                  </option>
                ))}
              </select>
            </div>
          </div>
          <p className="mt-3 text-xs text-[var(--color-fg-muted)]">
            Changing the target re-applies the suggested dates below (and
            discards edits to them).
          </p>
          {conflicts.length > 0 ? (
            <p
              className="mt-2 rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-xs text-amber-900"
              data-testid="duplicate-conflict-note"
            >
              Heads up: week {targetWeek} already has a{" "}
              {sourceEvent.module_slug || "same-module"} event (
              {conflicts[0].title || "untitled"}
              {conflicts.length > 1 ? ` and ${conflicts.length - 1} more` : ""}
              ). Creating this copy adds a second one.
            </p>
          ) : null}
        </div>

        {rows.length === 0 ? (
          <p className="text-sm text-amber-700">
            No active quarters entered yet — add the target quarter in Admin →
            Quarters first.
          </p>
        ) : initial ? (
          <EventForm
            key={`${targetRow?.id}:${targetWeek}`}
            mode="create"
            initial={initial}
            submitLabel="Create event"
            onSubmit={(payload) => createM.mutateAsync(payload)}
            onCancel={onClose}
            submitting={createM.isPending}
          />
        ) : null}
      </div>
    </FormModal>
  );
}
