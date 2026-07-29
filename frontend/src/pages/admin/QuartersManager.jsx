// src/pages/admin/QuartersManager.jsx
//
// Issue #24 — admin-entered quarters. The admin transcribes each quarter's
// "Quarter Begins" / "Quarter Ends" dates from the UCSB academic calendar
// (summer Session A/B dates come from the summer-sessions calendar); weeks
// and week numbers self-populate from the range — no other input. Saving a
// create/update surfaces the relink summary so event recategorization is
// visible, never silent.
//
// This is the reusable body: the standalone /admin/quarters page wraps it,
// and the Overview page hosts it in a slide-over drawer (embedded mode).
// Quarters are the scheduling backbone but only edited ~once per quarter, so
// they no longer take a permanent top-level nav slot.

import React, { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import api from "../../lib/api";
import { Button, Card, EmptyState, Input, Label, Modal, Skeleton } from "../../components/ui";
import SideDrawer from "../../components/admin/SideDrawer";
import AdminPageHeader from "../../components/admin/AdminPageHeader";
import { toast } from "../../state/toast";
import { useSelectedQuarter } from "../../state/QuarterSelectionContext";

const SEASONS = ["winter", "spring", "summer", "fall"];
const UCSB_CALENDAR_URL = "https://registrar.ucsb.edu/calendars/academic-calendars";

const EMPTY_FORM = {
  season: "fall",
  year: new Date().getFullYear(),
  label: "",
  start_date: "",
  end_date: "",
};

// The end date is inclusive, so a range is only a whole number of weeks when
// (span + 1) divides by 7. A short final week is legitimate — a 40-day summer
// session really does have a 6th week of programming — but a 1-day week 3 is
// almost always an off-by-one on the end date, so name the tail explicitly
// rather than reporting a bare week count the admin has to verify by hand.
function weeksPreview(startDate, endDate) {
  if (!startDate || !endDate) return null;
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
    return null;
  }
  const span = Math.floor((end.getTime() - start.getTime()) / (24 * 3600 * 1000));
  const days = span + 1;
  const weeks = Math.floor(span / 7) + 1;
  const tailDays = days - (weeks - 1) * 7;
  const evenEnd = new Date(end.getTime() - tailDays * 24 * 3600 * 1000);
  return {
    weeks,
    days,
    tailDays,
    // Suggested end date that would drop the stub and leave whole weeks.
    evenEndDate: evenEnd.toISOString().slice(0, 10),
    evenWeeks: weeks - 1,
  };
}

function relinkToast(prefix, summary) {
  if (!summary) return prefix;
  const bits = [`${summary.linked} event${summary.linked === 1 ? "" : "s"} linked`];
  if (summary.weeks_changed) bits.push(`${summary.weeks_changed} week number${summary.weeks_changed === 1 ? "" : "s"} corrected`);
  if (summary.unlinked) bits.push(`${summary.unlinked} unlinked`);
  return `${prefix} — ${bits.join(", ")}`;
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  });
}

export default function QuartersManager({ embedded = false }) {
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const setupMode = searchParams.get("setup") === "1";
  // fix/ux-quarter-batch: picking a quarter here re-scopes Overview + Events.
  const { selectedQuarter, viewingAll, setSelectedQuarterId } =
    useSelectedQuarter();

  const listQ = useQuery({
    queryKey: ["adminQuarters"],
    queryFn: () => api.admin.quarters.list(),
  });
  const rows = listQ.data || [];

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [editing, setEditing] = useState(null); // row being edited, or null
  const [form, setForm] = useState(EMPTY_FORM);
  const [confirmSave, setConfirmSave] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [archiving, setArchiving] = useState(null);

  function invalidate() {
    qc.invalidateQueries({ queryKey: ["adminQuarters"] });
    qc.invalidateQueries({ queryKey: ["publicQuarters"] });
    qc.invalidateQueries({ queryKey: ["publicCurrentWeek"] });
    qc.invalidateQueries({ queryKey: ["publicEvents"] });
  }

  const createMut = useMutation({
    mutationFn: (payload) => api.admin.quarters.create(payload),
    onSuccess: (res) => {
      invalidate();
      toast.success(relinkToast(`${res.quarter.display_name} added`, res.relink_summary));
      closeDrawer();
    },
    onError: (e) => toast.error(e?.message || "Couldn't add the quarter"),
  });
  const updateMut = useMutation({
    mutationFn: ({ id, payload }) => api.admin.quarters.update(id, payload),
    onSuccess: (res) => {
      invalidate();
      toast.success(relinkToast(`${res.quarter.display_name} updated`, res.relink_summary));
      closeDrawer();
    },
    onError: (e) => toast.error(e?.message || "Couldn't update the quarter"),
  });
  const deleteMut = useMutation({
    mutationFn: (id) => api.admin.quarters.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success("Quarter deleted");
      setDeleting(null);
    },
    onError: (e) => toast.error(e?.message || "Couldn't delete the quarter"),
  });
  // Issue #33 — archive past quarters (declutters navigation; events stay
  // browsable via the archived-quarters list on the public page).
  const archiveMut = useMutation({
    mutationFn: (id) => api.admin.quarters.archive(id),
    onSuccess: (row) => {
      invalidate();
      toast.success(`${row.display_name} archived`);
      setArchiving(null);
    },
    onError: (e) => toast.error(e?.message || "Couldn't archive the quarter"),
  });
  const restoreMut = useMutation({
    mutationFn: (id) => api.admin.quarters.restore(id),
    onSuccess: (row) => {
      invalidate();
      toast.success(`${row.display_name} restored`);
    },
    onError: (e) => toast.error(e?.message || "Couldn't restore the quarter"),
  });

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDrawerOpen(true);
  }

  function openEdit(row) {
    setEditing(row);
    setForm({
      season: row.season,
      year: row.year,
      label: row.label || "",
      start_date: row.start_date,
      end_date: row.end_date,
    });
    setDrawerOpen(true);
  }

  function closeDrawer() {
    setDrawerOpen(false);
    setEditing(null);
    setConfirmSave(false);
  }

  const previewWeeks = weeksPreview(form.start_date, form.end_date);
  const formValid = form.season && form.year && previewWeeks !== null;
  const datesChanged =
    editing && (form.start_date !== editing.start_date || form.end_date !== editing.end_date);

  function submit() {
    const payload = {
      season: form.season,
      year: Number(form.year),
      label: form.label.trim(),
      start_date: form.start_date,
      end_date: form.end_date,
    };
    if (editing) {
      updateMut.mutate({ id: editing.id, payload });
    } else {
      createMut.mutate(payload);
    }
  }

  function handleSave() {
    // Date edits recategorize existing events — confirm first.
    if (datesChanged) {
      setConfirmSave(true);
      return;
    }
    submit();
  }

  const saving = createMut.isPending || updateMut.isPending;
  const sortedRows = useMemo(
    () => [...rows].sort((a, b) => (a.start_date < b.start_date ? -1 : 1)),
    [rows],
  );
  const todayIso = new Date().toISOString().slice(0, 10);

  return (
    <div className="space-y-6">
      {(setupMode || (!listQ.isPending && rows.length === 0)) && (
        <Card>
          <h2 className="text-lg font-semibold">Enter your quarters</h2>
          <p className="mt-1 text-sm text-[var(--color-fg-muted)]">
            Scheduling is paused until a quarter covers today's date. Copy each
            quarter's <strong>Quarter Begins</strong> and{" "}
            <strong>Quarter Ends</strong> dates from the{" "}
            <a
              href={UCSB_CALENDAR_URL}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-[var(--color-brand)] underline"
            >
              UCSB academic calendar
            </a>
            {" "}(summer Session A/B dates come from the summer-sessions
            calendar). Weeks fill in automatically from the two dates.
          </p>
        </Card>
      )}

      {embedded ? (
        <div className="flex items-start justify-between gap-4">
          <p className="text-sm text-gray-600">
            Admin-entered quarters and summer sessions — weeks derive from the
            dates.
          </p>
          <Button onClick={openCreate} data-testid="add-quarter">
            Add quarter
          </Button>
        </div>
      ) : (
        <AdminPageHeader
          title="Quarters"
          subtitle="Admin-entered quarters and summer sessions — weeks derive from the dates."
        >
          <Button onClick={openCreate} data-testid="add-quarter">
            Add quarter
          </Button>
        </AdminPageHeader>
      )}

      {listQ.isPending ? (
        <Skeleton className="h-40 rounded-xl" />
      ) : sortedRows.length === 0 ? (
        <EmptyState
          title="No quarters yet"
          body="Add the current quarter to unlock scheduling."
        />
      ) : (
        <Card>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[var(--color-fg-muted)]">
                <th className="py-2 pr-4">Quarter</th>
                <th className="py-2 pr-4">Begins</th>
                <th className="py-2 pr-4">Ends</th>
                <th className="py-2 pr-4">Weeks</th>
                <th className="py-2" />
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((row) => (
                <tr key={row.id} className="border-t border-[var(--color-border)]">
                  <td className="py-3 pr-4 font-medium">
                    {row.display_name}
                    {row.start_date <= todayIso && row.end_date >= todayIso && (
                      <span className="ml-2 inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800">
                        Current
                      </span>
                    )}
                    {!viewingAll && selectedQuarter?.id === row.id && (
                      <span
                        data-testid={`viewing-${row.id}`}
                        className="ml-2 inline-flex items-center rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800"
                      >
                        Viewing
                      </span>
                    )}
                    {row.archived_at && (
                      <span className="ml-2 inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                        Archived
                      </span>
                    )}
                  </td>
                  <td className="py-3 pr-4">{formatDate(row.start_date)}</td>
                  <td className="py-3 pr-4">{formatDate(row.end_date)}</td>
                  <td className="py-3 pr-4">{row.weeks_in_quarter}</td>
                  <td className="py-3 text-right space-x-2">
                    {/* Re-scope Overview + Events to this quarter. */}
                    {!viewingAll && selectedQuarter?.id === row.id ? null : (
                      <Button
                        variant="secondary"
                        onClick={() => setSelectedQuarterId(row.id)}
                        data-testid={`select-${row.id}`}
                      >
                        View this quarter
                      </Button>
                    )}
                    {/* Issue #38 — ended quarters get a retrospective view */}
                    {(row.archived_at || row.end_date < todayIso) && (
                      <Button
                        variant="secondary"
                        as={Link}
                        to={`/admin/quarters/${row.id}`}
                        data-testid={`retro-${row.id}`}
                      >
                        View events
                      </Button>
                    )}
                    <Button
                      variant="secondary"
                      onClick={() => openEdit(row)}
                      data-testid={`edit-${row.id}`}
                    >
                      Edit
                    </Button>
                    {row.archived_at ? (
                      <Button
                        variant="secondary"
                        onClick={() => restoreMut.mutate(row.id)}
                        disabled={restoreMut.isPending}
                        data-testid={`restore-${row.id}`}
                      >
                        Restore
                      </Button>
                    ) : (
                      // Only ended quarters can be archived — the live
                      // schedule stays navigable.
                      row.end_date < todayIso && (
                        <Button
                          variant="secondary"
                          onClick={() => setArchiving(row)}
                          data-testid={`archive-${row.id}`}
                        >
                          Archive
                        </Button>
                      )
                    )}
                    <Button
                      variant="secondary"
                      onClick={() => setDeleting(row)}
                      data-testid={`delete-${row.id}`}
                    >
                      Delete
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      <SideDrawer
        open={drawerOpen}
        onClose={closeDrawer}
        title={editing ? `Edit ${editing.display_name}` : "Add quarter"}
      >
        <div className="space-y-4">
          <div>
            <Label htmlFor="q-season">Season</Label>
            <select
              id="q-season"
              value={form.season}
              onChange={(e) => setForm({ ...form, season: e.target.value })}
              className="mt-1 w-full rounded-md border border-gray-300 px-2 py-2 text-sm"
            >
              {SEASONS.map((s) => (
                <option key={s} value={s}>
                  {s.charAt(0).toUpperCase() + s.slice(1)}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label htmlFor="q-year">Year</Label>
            <Input
              id="q-year"
              type="number"
              value={form.year}
              onChange={(e) => setForm({ ...form, year: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="q-label">Session label (summer only)</Label>
            <Input
              id="q-label"
              placeholder='e.g. "Session A" — leave blank for regular quarters'
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="q-start">Quarter begins</Label>
            <Input
              id="q-start"
              type="date"
              value={form.start_date}
              onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            />
          </div>
          <div>
            <Label htmlFor="q-end">Quarter ends</Label>
            <Input
              id="q-end"
              type="date"
              value={form.end_date}
              onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            />
          </div>

          <div
            className="rounded-md bg-gray-50 p-3 text-sm text-[var(--color-fg-muted)]"
            data-testid="weeks-preview"
          >
            {previewWeeks !== null ? (
              <>
                → <strong>{previewWeeks.weeks} weeks</strong> ·{" "}
                {previewWeeks.days} days · Week 1 starts{" "}
                {formatDate(form.start_date)}. Week numbers fill in
                automatically — dates are the only input.
                {previewWeeks.tailDays < 7 && previewWeeks.evenWeeks >= 1 ? (
                  <div
                    className="mt-2 text-amber-700"
                    data-testid="weeks-preview-stub"
                  >
                    ⚠ Week {previewWeeks.weeks} is only{" "}
                    {previewWeeks.tailDays} day
                    {previewWeeks.tailDays === 1 ? "" : "s"} long. End on{" "}
                    {formatDate(previewWeeks.evenEndDate)} instead for{" "}
                    {previewWeeks.evenWeeks} even week
                    {previewWeeks.evenWeeks === 1 ? "" : "s"}.{" "}
                    <button
                      type="button"
                      className="underline"
                      onClick={() =>
                        setForm({ ...form, end_date: previewWeeks.evenEndDate })
                      }
                    >
                      Use {formatDate(previewWeeks.evenEndDate)}
                    </button>
                  </div>
                ) : null}
              </>
            ) : (
              <>Enter both dates to see the week count.</>
            )}
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="secondary" onClick={closeDrawer}>
              Cancel
            </Button>
            <Button
              onClick={handleSave}
              disabled={!formValid || saving}
              data-testid="save-quarter"
            >
              {saving ? "Saving…" : editing ? "Save changes" : "Add quarter"}
            </Button>
          </div>
        </div>
      </SideDrawer>

      <Modal
        open={confirmSave}
        onClose={() => setConfirmSave(false)}
        title="Change quarter dates?"
      >
        <p className="text-sm">
          Changing the dates recategorizes existing events: week numbers are
          recomputed and events falling outside the new range are unlinked.
          You'll see a summary after saving.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setConfirmSave(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              setConfirmSave(false);
              submit();
            }}
            data-testid="confirm-save"
          >
            Save and recategorize
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!archiving}
        onClose={() => setArchiving(null)}
        title={archiving ? `Archive ${archiving.display_name}?` : ""}
      >
        <p className="text-sm">
          Archiving tidies the week navigation — the quarter moves under
          "Archived quarters" on the public page, where its events stay
          viewable. You can restore it any time.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setArchiving(null)}>
            Cancel
          </Button>
          <Button
            onClick={() => archiveMut.mutate(archiving.id)}
            disabled={archiveMut.isPending}
            data-testid="confirm-archive"
          >
            Archive
          </Button>
        </div>
      </Modal>

      <Modal
        open={!!deleting}
        onClose={() => setDeleting(null)}
        title={deleting ? `Delete ${deleting.display_name}?` : ""}
      >
        <p className="text-sm">
          Quarters with linked events can't be deleted. This can't be undone.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={() => setDeleting(null)}>
            Cancel
          </Button>
          <Button
            onClick={() => deleteMut.mutate(deleting.id)}
            disabled={deleteMut.isPending}
            data-testid="confirm-delete"
          >
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}
