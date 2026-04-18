import React, { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../../lib/api";
import { useAdminPageTitle } from "./AdminLayout";
import { toast } from "../../state/toast";

function fmtDateTime(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

// HTML datetime-local needs "YYYY-MM-DDTHH:MM" with no timezone.
function isoToLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localInputToIso(value) {
  if (!value) return null;
  return new Date(value).toISOString();
}

// Combine "YYYY-MM-DD" + "HH:MM" (wall-clock) into an ISO string using the
// browser's local timezone. The backend normalizes to UTC on receipt.
function combineDateTime(date, time) {
  if (!date || !time) return null;
  return new Date(`${date}T${time}`).toISOString();
}

// Convert a loaded SlotRead (ISO strings) into form-shape (wall-clock HH:MM
// and YYYY-MM-DD) so edits round-trip without drift.
function loadedSlotToForm(slot) {
  const pad = (n) => String(n).padStart(2, "0");
  const start = new Date(slot.start_time);
  const end = new Date(slot.end_time);
  const dateStr =
    slot.date ||
    `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`;
  const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return {
    id: slot.id,
    slot_type: slot.slot_type || "period",
    date: dateStr,
    start_time: fmtTime(start),
    end_time: fmtTime(end),
    capacity: String(slot.capacity ?? ""),
    location: slot.location || "",
    current_count: Number(slot.current_count || 0),
  };
}

function newEmptySlot(defaults = {}) {
  return {
    // no id → this is a new slot when diffing
    slot_type: "period",
    date: defaults.date || "",
    start_time: "",
    end_time: "",
    capacity: "",
    location: defaults.location || "",
    current_count: 0,
  };
}

function slotFormToApiPayload(slot) {
  return {
    slot_type: slot.slot_type,
    date: slot.date || null,
    start_time: combineDateTime(slot.date, slot.start_time),
    end_time: combineDateTime(slot.date, slot.end_time),
    capacity: Number(slot.capacity),
    location: slot.location?.trim() || null,
  };
}

function slotChanged(a, b) {
  return (
    a.slot_type !== b.slot_type ||
    a.date !== b.date ||
    a.start_time !== b.start_time ||
    a.end_time !== b.end_time ||
    Number(a.capacity) !== Number(b.capacity) ||
    (a.location || "") !== (b.location || "")
  );
}

function diffSlots(initial, draft) {
  const initialById = new Map((initial || []).map((s) => [s.id, s]));
  const draftIds = new Set(draft.filter((s) => s.id).map((s) => s.id));
  const creates = draft.filter((s) => !s.id);
  const updates = draft.filter(
    (s) => s.id && initialById.has(s.id) && slotChanged(initialById.get(s.id), s),
  );
  const deletes = [...initialById.keys()].filter((id) => !draftIds.has(id));
  return { creates, updates, deletes };
}

function localDatePart(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function validateSlot(slot, eventStartIso, eventEndIso) {
  if (!slot.date) return "Date is required.";
  if (!slot.start_time || !slot.end_time) return "Start and end times are required.";
  const start = new Date(`${slot.date}T${slot.start_time}`);
  const end = new Date(`${slot.date}T${slot.end_time}`);
  if (!(end > start)) return "End time must be after start time.";
  const cap = Number(slot.capacity);
  if (!Number.isFinite(cap) || cap <= 0) return "Capacity must be a positive integer.";
  const evStartDate = localDatePart(eventStartIso);
  const evEndDate = localDatePart(eventEndIso);
  if (evStartDate && slot.date < evStartDate) return "Slot date is before the event start.";
  if (evEndDate && slot.date > evEndDate) return "Slot date is after the event end.";
  return null;
}

const EMPTY_FORM = {
  title: "",
  description: "",
  location: "",
  start_date: "",
  end_date: "",
  max_signups_per_user: "",
  visibility: "public",
  school: "",
  module_slug: "",
};

function slugify(name) {
  return String(name || "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function NewModuleDialog({ open, onCancel, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const slug = slugify(name);

  async function submit(e) {
    e.preventDefault();
    setErr(null);
    if (!name.trim()) return setErr("Name is required.");
    if (slug.length < 2) return setErr("Name must produce a slug of at least 2 characters.");
    setBusy(true);
    try {
      const created = await api.admin.templates.create({
        slug,
        name: name.trim(),
        description: description.trim() || null,
      });
      onCreated(created);
      setName("");
      setDescription("");
    } catch (e2) {
      setErr(e2?.message || "Create failed");
    } finally {
      setBusy(false);
    }
  }

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onClick={onCancel}>
      <div
        className="bg-white rounded-xl w-full max-w-md shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="border-b border-gray-200 px-5 py-3 flex justify-between items-center">
          <h3 className="text-base font-semibold">New module</h3>
          <button
            type="button"
            onClick={onCancel}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-700 text-2xl leading-none"
          >
            ×
          </button>
        </div>
        <form onSubmit={submit} className="px-5 py-4 space-y-3">
          <div>
            <label className="block text-sm font-medium mb-1">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              placeholder="e.g. CRISPR Intro"
              required
            />
            <p className="text-xs text-gray-500 mt-1">
              Slug: <code className="font-mono">{slug || "—"}</code>
            </p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm"
              placeholder="Optional"
            />
          </div>
          {err && <p className="text-sm text-red-700" role="alert">{err}</p>}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={onCancel}
              className="px-3 py-2 text-sm text-gray-700 hover:bg-gray-100 rounded"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy}
              className="px-3 py-2 text-sm text-white bg-blue-600 rounded disabled:opacity-50"
            >
              {busy ? "Creating…" : "Create module"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EventForm({ initial, mode, onSubmit, onCancel, submitting }) {
  const isEdit = mode === "edit";
  const [form, setForm] = useState(() => ({
    ...EMPTY_FORM,
    ...(initial || {}),
    start_date: isoToLocalInput(initial?.start_date),
    end_date: isoToLocalInput(initial?.end_date),
    max_signups_per_user: initial?.max_signups_per_user ?? "",
    school: initial?.school ?? "",
    module_slug: initial?.module_slug ?? "",
  }));
  const [showNewModule, setShowNewModule] = useState(false);

  const modulesQ = useQuery({
    queryKey: ["adminModuleTemplatesForEventForm"],
    queryFn: () => api.admin.templates.list(),
    staleTime: 30_000,
  });
  const modules = Array.isArray(modulesQ.data) ? modulesQ.data : [];
  const [slots, setSlots] = useState(() => {
    if (initial?.slots?.length) {
      return initial.slots.map(loadedSlotToForm);
    }
    return [newEmptySlot()];
  });
  const [error, setError] = useState(null);
  const [slotErrors, setSlotErrors] = useState({});

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function updateSlot(index, patch) {
    setSlots((arr) => arr.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function addSlot() {
    setSlots((arr) => [
      ...arr,
      newEmptySlot({
        date: form.start_date ? form.start_date.slice(0, 10) : "",
        location: form.location,
      }),
    ]);
  }

  function removeSlot(index) {
    setSlots((arr) => arr.filter((_, i) => i !== index));
    setSlotErrors((errs) => {
      const next = { ...errs };
      delete next[index];
      return next;
    });
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSlotErrors({});

    if (!form.title.trim()) return setError("Title is required.");
    if (!form.module_slug)
      return setError("Pick a module, or create one with '+ New module'.");
    if (!form.start_date || !form.end_date)
      return setError("Start and end times are required.");
    if (new Date(form.end_date) <= new Date(form.start_date))
      return setError("Event end time must be after start time.");

    if (slots.length === 0) {
      return setError("At least one slot is required.");
    }

    const startIso = localInputToIso(form.start_date);
    const endIso = localInputToIso(form.end_date);
    const perSlotErrors = {};
    slots.forEach((s, i) => {
      const err = validateSlot(s, startIso, endIso);
      if (err) perSlotErrors[i] = err;
    });
    if (Object.keys(perSlotErrors).length) {
      setSlotErrors(perSlotErrors);
      return setError("Fix the slot errors below before saving.");
    }

    const metadata = {
      title: form.title.trim(),
      description: form.description?.trim() || null,
      location: form.location?.trim() || null,
      visibility: form.visibility || "public",
      start_date: startIso,
      end_date: endIso,
      max_signups_per_user: form.max_signups_per_user
        ? Number(form.max_signups_per_user)
        : null,
      school: form.school?.trim() || null,
      module_slug: form.module_slug,
    };

    const initialSlotsFormShape = (initial?.slots || []).map(loadedSlotToForm);

    try {
      await onSubmit({
        metadata,
        slots,
        initialSlots: initialSlotsFormShape,
      });
    } catch (err) {
      setError(err?.message || "Save failed");
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label className="block text-sm font-medium mb-1">Title *</label>
        <input
          aria-label="Title *"
          value={form.title}
          onChange={(e) => update("title", e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          required
        />
      </div>
      <div>
        <label className="block text-sm font-medium mb-1">Description</label>
        <textarea
          aria-label="Description"
          value={form.description || ""}
          onChange={(e) => update("description", e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">Location</label>
          <input
            aria-label="Location"
            value={form.location || ""}
            onChange={(e) => update("location", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">School</label>
          <input
            aria-label="School"
            value={form.school || ""}
            onChange={(e) => update("school", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Optional"
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">Start *</label>
          <input
            aria-label="Start *"
            type="datetime-local"
            value={form.start_date}
            onChange={(e) => update("start_date", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">End *</label>
          <input
            aria-label="End *"
            type="datetime-local"
            value={form.end_date}
            onChange={(e) => update("end_date", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            required
          />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">
            Max signups per volunteer
          </label>
          <input
            type="number"
            min="1"
            value={form.max_signups_per_user}
            onChange={(e) => update("max_signups_per_user", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="No limit"
          />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Visibility</label>
          <select
            value={form.visibility}
            onChange={(e) => update("visibility", e.target.value)}
            className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
          >
            <option value="public">Public</option>
            <option value="private">Private</option>
          </select>
        </div>
      </div>

      <section className="border-t border-gray-200 pt-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">Module *</h3>
          <button
            type="button"
            onClick={() => setShowNewModule(true)}
            className="text-sm text-blue-600 hover:underline"
          >
            + New module
          </button>
        </div>
        <select
          aria-label="Module *"
          value={form.module_slug}
          onChange={(e) => update("module_slug", e.target.value)}
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        >
          <option value="">
            {modulesQ.isLoading ? "Loading modules…" : "— pick a module —"}
          </option>
          {modules.map((m) => (
            <option key={m.slug} value={m.slug}>
              {m.name} ({m.slug})
            </option>
          ))}
        </select>
        <p className="text-xs text-gray-500 mt-1">
          Orientation credit is scoped per module — volunteers who orient for one
          module don't automatically get credit for others.
        </p>
      </section>

      <NewModuleDialog
        open={showNewModule}
        onCancel={() => setShowNewModule(false)}
        onCreated={(m) => {
          modulesQ.refetch();
          update("module_slug", m.slug);
          setShowNewModule(false);
        }}
      />

      <section className="border-t border-gray-200 pt-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-semibold">Slots</h3>
          <button
            type="button"
            onClick={addSlot}
            className="text-sm text-blue-600 hover:underline"
          >
            + Add slot
          </button>
        </div>
        {slots.length === 0 ? (
          <p className="text-xs text-gray-500">
            Click "+ Add slot" to add at least one slot.
          </p>
        ) : (
          <ul className="space-y-3">
            {slots.map((s, i) => {
              const removeDisabled = isEdit && s.current_count > 0;
              return (
                <li
                  key={s.id || `new-${i}`}
                  className="rounded-lg border border-gray-200 bg-gray-50 p-3"
                  data-testid={`slot-row-${i}`}
                >
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
                    <div className="md:col-span-1">
                      <label className="block text-xs text-gray-600 mb-1">Type</label>
                      <select
                        aria-label={`Slot ${i + 1} type`}
                        value={s.slot_type}
                        onChange={(e) => updateSlot(i, { slot_type: e.target.value })}
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm bg-white"
                      >
                        <option value="period">Period</option>
                        <option value="orientation">Orientation</option>
                      </select>
                    </div>
                    <div className="md:col-span-1">
                      <label className="block text-xs text-gray-600 mb-1">Date</label>
                      <input
                        type="date"
                        aria-label={`Slot ${i + 1} date`}
                        value={s.date}
                        onChange={(e) => updateSlot(i, { date: e.target.value })}
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Start</label>
                      <input
                        type="time"
                        aria-label={`Slot ${i + 1} start time`}
                        value={s.start_time}
                        onChange={(e) => updateSlot(i, { start_time: e.target.value })}
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">End</label>
                      <input
                        type="time"
                        aria-label={`Slot ${i + 1} end time`}
                        value={s.end_time}
                        onChange={(e) => updateSlot(i, { end_time: e.target.value })}
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Capacity</label>
                      <input
                        type="number"
                        min="1"
                        aria-label={`Slot ${i + 1} capacity`}
                        value={s.capacity}
                        onChange={(e) => updateSlot(i, { capacity: e.target.value })}
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-gray-600 mb-1">Location</label>
                      <input
                        aria-label={`Slot ${i + 1} location`}
                        value={s.location}
                        onChange={(e) => updateSlot(i, { location: e.target.value })}
                        placeholder="(uses event)"
                        className="w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
                      />
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    {slotErrors[i] ? (
                      <p
                        className="text-xs text-red-700"
                        role="alert"
                        data-testid={`slot-error-${i}`}
                      >
                        {slotErrors[i]}
                      </p>
                    ) : (
                      <span className="text-xs text-gray-500">
                        {isEdit && s.current_count > 0
                          ? `${s.current_count} signup${s.current_count === 1 ? "" : "s"}`
                          : ""}
                      </span>
                    )}
                    <button
                      type="button"
                      onClick={() => removeSlot(i)}
                      disabled={removeDisabled}
                      title={
                        removeDisabled
                          ? `Has ${s.current_count} signup${s.current_count === 1 ? "" : "s"} — cannot remove`
                          : "Remove this slot"
                      }
                      className="text-xs text-red-600 hover:underline disabled:text-gray-400 disabled:no-underline disabled:cursor-not-allowed"
                    >
                      Remove
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {error && (
        <p className="text-sm text-red-700" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg disabled:opacity-50"
        >
          {submitting ? "Saving…" : "Save"}
        </button>
      </div>
    </form>
  );
}

function ConfirmDialog({ open, title, body, onCancel, onConfirm, confirmLabel = "Delete", busy }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-lg max-w-md w-full p-6 shadow-xl">
        <h3 className="text-lg font-semibold">{title}</h3>
        <p className="text-sm text-gray-600 mt-2">{body}</p>
        <div className="flex justify-end gap-2 mt-4">
          <button
            onClick={onCancel}
            className="px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className="px-4 py-2 text-sm font-medium text-white bg-red-600 rounded-lg disabled:opacity-50"
          >
            {busy ? "…" : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

function Modal({ open, title, onClose, children }) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-white border-b border-gray-200 px-6 py-4 flex justify-between items-center rounded-t-xl">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="text-gray-400 hover:text-gray-700 text-2xl leading-none w-8 h-8 flex items-center justify-center rounded hover:bg-gray-100"
          >
            ×
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

// Run slot-diff mutations after the metadata update has persisted. Throws
// with a message listing failing slot indexes when any op rejects.
async function applySlotDiff(eventId, initialSlots, draftSlots) {
  const { creates, updates, deletes } = diffSlots(initialSlots, draftSlots);
  const ops = [];
  creates.forEach((s, i) => {
    const label = `new #${i + 1}`;
    ops.push({
      label,
      promise: api.slots.create(eventId, slotFormToApiPayload(s)),
    });
  });
  updates.forEach((s) => {
    ops.push({
      label: `slot ${s.id}`,
      promise: api.slots.update(s.id, slotFormToApiPayload(s)),
    });
  });
  deletes.forEach((id) => {
    ops.push({ label: `delete ${id}`, promise: api.slots.delete(id) });
  });
  if (ops.length === 0) return;
  const results = await Promise.allSettled(ops.map((o) => o.promise));
  const failed = results
    .map((r, i) => (r.status === "rejected" ? ops[i].label : null))
    .filter(Boolean);
  if (failed.length) {
    throw new Error(`Slot changes failed: ${failed.join(", ")}`);
  }
}

export default function EventsSection() {
  useAdminPageTitle("Events");
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("upcoming"); // upcoming | past | all
  const [drawerMode, setDrawerMode] = useState(null); // "create" | "edit"
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const q = useQuery({
    queryKey: ["adminEventsList"],
    queryFn: () => api.events.list(),
  });

  const events = q.data || [];

  const filtered = useMemo(() => {
    const now = Date.now();
    const term = search.toLowerCase().trim();
    return events
      .filter((e) => {
        if (scope === "upcoming" && new Date(e.end_date).getTime() < now) return false;
        if (scope === "past" && new Date(e.end_date).getTime() >= now) return false;
        if (term && !(e.title || "").toLowerCase().includes(term)) return false;
        return true;
      })
      .sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
  }, [events, search, scope]);

  const createM = useMutation({
    mutationFn: ({ metadata, slots }) =>
      api.events.create({
        ...metadata,
        slots: slots.map(slotFormToApiPayload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDrawerMode(null);
      toast.success("Event created.");
    },
  });

  const updateM = useMutation({
    mutationFn: async ({ id, metadata, slots, initialSlots }) => {
      await api.events.update(id, metadata);
      await applySlotDiff(id, initialSlots, slots);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDrawerMode(null);
      setEditing(null);
      toast.success("Event updated.");
    },
    onError: (e) => toast.error(e?.message || "Update failed"),
  });

  const deleteM = useMutation({
    mutationFn: (id) => api.events.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDeleting(null);
      toast.success("Event deleted.");
    },
    onError: (e) => toast.error(e?.message || "Delete failed"),
  });

  const cloneM = useMutation({
    mutationFn: (id) => api.events.clone(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      toast.success("Event cloned.");
    },
    onError: (e) => toast.error(e?.message || "Clone failed"),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Events</h1>
          <p className="text-sm text-gray-600">
            All events in the system. Create, edit, or delete events here.
          </p>
        </div>
        <button
          onClick={() => {
            setEditing(null);
            setDrawerMode("create");
          }}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg"
        >
          + New event
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <input
          placeholder="Search by title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[14rem] rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white"
        >
          <option value="upcoming">Upcoming</option>
          <option value="past">Past</option>
          <option value="all">All</option>
        </select>
      </div>

      {q.isPending ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : q.error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          Couldn't load events: {q.error.message}{" "}
          <button onClick={() => q.refetch()} className="underline ml-2">
            Retry
          </button>
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-6 text-sm text-gray-600">
          No events match.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="py-2 px-3">Title</th>
                <th className="py-2 px-3">Start</th>
                <th className="py-2 px-3">End</th>
                <th className="py-2 px-3">Location</th>
                <th className="py-2 px-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="py-2 px-3 font-medium">
                    <Link
                      to={`/admin/events/${e.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {e.title || "(untitled)"}
                    </Link>
                  </td>
                  <td className="py-2 px-3">{fmtDateTime(e.start_date)}</td>
                  <td className="py-2 px-3">{fmtDateTime(e.end_date)}</td>
                  <td className="py-2 px-3">{e.location || "—"}</td>
                  <td className="py-2 px-3 text-right space-x-2 whitespace-nowrap">
                    <button
                      onClick={() => {
                        setEditing(e);
                        setDrawerMode("edit");
                      }}
                      className="text-blue-600 hover:underline"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => cloneM.mutate(e.id)}
                      className="text-gray-700 hover:underline"
                    >
                      Clone
                    </button>
                    <button
                      onClick={() => setDeleting(e)}
                      className="text-red-600 hover:underline"
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={drawerMode === "create"}
        title="New event"
        onClose={() => setDrawerMode(null)}
      >
        <EventForm
          mode="create"
          onSubmit={(payload) => createM.mutateAsync(payload)}
          onCancel={() => setDrawerMode(null)}
          submitting={createM.isPending}
        />
      </Modal>

      <Modal
        open={drawerMode === "edit"}
        title="Edit event"
        onClose={() => {
          setDrawerMode(null);
          setEditing(null);
        }}
      >
        {editing && (
          <EventForm
            mode="edit"
            initial={editing}
            onSubmit={(payload) =>
              updateM.mutateAsync({ id: editing.id, ...payload })
            }
            onCancel={() => {
              setDrawerMode(null);
              setEditing(null);
            }}
            submitting={updateM.isPending}
          />
        )}
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        title="Delete event?"
        body={`This will permanently delete "${deleting?.title}" and its slots. Existing signups will be removed. This cannot be undone.`}
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleteM.mutate(deleting.id)}
        busy={deleteM.isPending}
      />
    </div>
  );
}

// Exports for tests
export { diffSlots, slotFormToApiPayload, validateSlot, loadedSlotToForm };
