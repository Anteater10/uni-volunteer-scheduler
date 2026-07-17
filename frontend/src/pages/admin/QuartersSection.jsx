// src/pages/admin/QuartersSection.jsx
//
// Issue #24 — admin-entered quarters. The admin transcribes each quarter's
// "Quarter Begins" / "Quarter Ends" dates from the UCSB academic calendar
// (summer Session A/B dates come from the summer-sessions calendar); weeks
// and week numbers self-populate from the range — no other input. Saving a
// create/update surfaces the relink summary so event recategorization is
// visible, never silent.

import React, { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import api from "../../lib/api";
import { Button, Card, EmptyState, Input, Label, Modal, Skeleton } from "../../components/ui";
import SideDrawer from "../../components/admin/SideDrawer";
import { toast } from "../../state/toast";
import { useAdminPageTitle } from "./AdminLayout";

const SEASONS = ["winter", "spring", "summer", "fall"];
const UCSB_CALENDAR_URL = "https://registrar.ucsb.edu/calendars/academic-calendars";

const EMPTY_FORM = {
  season: "fall",
  year: new Date().getFullYear(),
  label: "",
  start_date: "",
  end_date: "",
};

function weeksPreview(startDate, endDate) {
  if (!startDate || !endDate) return null;
  const start = new Date(`${startDate}T00:00:00Z`);
  const end = new Date(`${endDate}T00:00:00Z`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end <= start) {
    return null;
  }
  const days = Math.floor((end.getTime() - start.getTime()) / (24 * 3600 * 1000));
  return Math.floor(days / 7) + 1;
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

export default function QuartersSection() {
  useAdminPageTitle("Quarters");
  const qc = useQueryClient();
  const [searchParams] = useSearchParams();
  const setupMode = searchParams.get("setup") === "1";

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

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Quarters</h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            Admin-entered quarters and summer sessions — weeks derive from the
            dates.
          </p>
        </div>
        <Button onClick={openCreate} data-testid="add-quarter">
          Add quarter
        </Button>
      </div>

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
                  <td className="py-3 pr-4 font-medium">{row.display_name}</td>
                  <td className="py-3 pr-4">{formatDate(row.start_date)}</td>
                  <td className="py-3 pr-4">{formatDate(row.end_date)}</td>
                  <td className="py-3 pr-4">{row.weeks_in_quarter}</td>
                  <td className="py-3 text-right space-x-2">
                    <Button
                      variant="secondary"
                      onClick={() => openEdit(row)}
                      data-testid={`edit-${row.id}`}
                    >
                      Edit
                    </Button>
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
                → <strong>{previewWeeks} weeks</strong> · Week 1 starts{" "}
                {formatDate(form.start_date)}. Week numbers fill in
                automatically — dates are the only input.
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
