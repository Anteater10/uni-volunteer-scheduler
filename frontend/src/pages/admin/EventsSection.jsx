import React, { useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  CalendarClock,
  GraduationCap,
  LayoutGrid,
  MapPin,
  Plus,
  Trash2,
} from "lucide-react";
import { api } from "../../lib/api";
import { useAdminPageTitle } from "./AdminLayout";
import { toast } from "../../state/toast";
import AdminPageHeader from "../../components/admin/AdminPageHeader";
import FormModal from "../../components/admin/FormModal";

// ---------------------------------------------------------------------------
// Form styling tokens
//
// The event modal is where admins spend most of their time, so its controls
// get one shared definition rather than a class string copy-pasted per field.
// Colours come from the CSS variables in index.css so the modal stays in step
// with the rest of the admin surface instead of hard-coding blue-600.
// ---------------------------------------------------------------------------

const FIELD =
  "w-full rounded-lg border border-[var(--color-border)] bg-white px-3 py-2.5 text-sm " +
  "shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-all duration-150 " +
  "placeholder:text-slate-400 hover:border-slate-300 " +
  "focus:outline-none focus:border-[var(--color-brand)] " +
  "focus:ring-4 focus:ring-[var(--color-brand)]/12";

const FIELD_SM =
  "w-full rounded-md border border-[var(--color-border)] bg-white px-2.5 py-1.5 text-sm " +
  "transition-all duration-150 hover:border-slate-300 " +
  "focus:outline-none focus:border-[var(--color-brand)] " +
  "focus:ring-4 focus:ring-[var(--color-brand)]/12";

const LABEL = "block text-sm font-medium text-[var(--color-fg)] mb-1.5";
const LABEL_SM =
  "block text-[11px] font-medium uppercase tracking-wide text-[var(--color-fg-muted)] mb-1";

// A section heading with an icon in a soft brand tile — gives the long form a
// scannable rhythm so the eye can find "Slots" without reading every label.
function FormSection({ icon: Icon, title, hint, action, children }) {
  return (
    <section className="border-t border-[var(--color-border)] pt-5">
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[var(--color-brand-soft)] text-[var(--color-brand)]">
            <Icon className="h-4 w-4" strokeWidth={2.2} />
          </span>
          <h3 className="text-sm font-semibold text-[var(--color-fg)]">{title}</h3>
        </div>
        {action}
      </div>
      {children}
      {hint ? (
        <p className="text-xs text-[var(--color-fg-muted)] mt-2 leading-relaxed">
          {hint}
        </p>
      ) : null}
    </section>
  );
}

// ---------------------------------------------------------------------------
// PickerInput — date/time input that also opens on click and accepts
// mouse-wheel nudges.
//
// A bare <input type="time"> only responds to typing and arrow keys, and the
// native picker is not something we can rely on: Safari renders time and
// datetime-local as plain segmented text with no picker at all, so
// showPicker() silently does nothing there. Admins set dozens of slot times
// per sitting, so for `type="time"` we ship our own dropdown of quarter-hour
// options that behaves the same in every browser. Date fields keep the native
// calendar, which every browser does provide.
//
// The dropdown renders in a portal at fixed coordinates so it is never clipped
// by the modal's scroll container, and closes as soon as anything scrolls.
//
// The wheel handler is deliberately focus-gated: scrolling this long modal
// with the cursor over a time field must never silently rewrite it. You have
// to click into the field first, which also makes the behaviour discoverable
// rather than surprising.
// ---------------------------------------------------------------------------

const WHEEL_STEP_MINUTES = 5;
const MENU_STEP_MINUTES = 15;
const MENU_START_HOUR = 6; // SciTrek days run school hours; no 3am options
const MENU_END_HOUR = 21;
const WHEEL_SEED_TIME = { h: 9, m: 0 }; // school-day default when empty

function parseTimeValue(value, type) {
  if (type === "time") {
    const m = /^(\d{1,2}):(\d{2})/.exec(value || "");
    return m ? { date: null, h: Number(m[1]), m: Number(m[2]) } : null;
  }
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{1,2}):(\d{2})/.exec(value || "");
  return m ? { date: m[1], h: Number(m[2]), m: Number(m[3]) } : null;
}

function formatTimeValue({ date, h, m }, type) {
  const pad = (n) => String(n).padStart(2, "0");
  const hhmm = `${pad(h)}:${pad(m)}`;
  return type === "time" ? hhmm : `${date}T${hhmm}`;
}

// Step a time value by whole minutes, clamping at midnight either end so a
// stray scroll can't roll a 9am slot back to the previous day.
function stepTimeValue(value, type, deltaMinutes, todayIso) {
  let parts = parseTimeValue(value, type);
  if (!parts) {
    // Nothing entered yet: seed a sensible time instead of jumping from 00:00.
    if (type !== "time" && !todayIso) return value;
    parts = { date: todayIso, ...WHEEL_SEED_TIME };
    return formatTimeValue(parts, type);
  }
  const total = parts.h * 60 + parts.m + deltaMinutes;
  const clamped = Math.max(0, Math.min(23 * 60 + 59, total));
  return formatTimeValue(
    { date: parts.date, h: Math.floor(clamped / 60), m: clamped % 60 },
    type
  );
}

// Quarter-hour options, built once. 12-hour labels because that is how staff
// talk about a school day, while the stored value stays 24-hour "HH:MM".
const TIME_OPTIONS = (() => {
  const pad = (n) => String(n).padStart(2, "0");
  const out = [];
  for (let mins = MENU_START_HOUR * 60; mins <= MENU_END_HOUR * 60; mins += MENU_STEP_MINUTES) {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    const h12 = h % 12 === 0 ? 12 : h % 12;
    out.push({ value: `${pad(h)}:${pad(m)}`, label: `${h12}:${pad(m)} ${h < 12 ? "AM" : "PM"}` });
  }
  return out;
})();

function TimeMenu({ anchor, value, onPick, onClose }) {
  const listRef = React.useRef(null);
  const rect = anchor.getBoundingClientRect();
  // Flip above the field when there isn't room below it.
  const below = window.innerHeight - rect.bottom > 240;
  const style = {
    position: "fixed",
    left: Math.round(rect.left),
    minWidth: Math.round(rect.width),
    ...(below ? { top: Math.round(rect.bottom + 4) } : { bottom: Math.round(window.innerHeight - rect.top + 4) }),
  };

  // Bring the current (or nearest) option into view so the wheel starts from
  // where the admin already is rather than at 6am.
  React.useEffect(() => {
    const el = listRef.current?.querySelector("[data-active='true']");
    el?.scrollIntoView({ block: "center" });
  }, []);

  React.useEffect(() => {
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    // Scrolling the page would leave the menu stranded at stale coordinates,
    // but wheeling the option list itself is the whole point — let that pass.
    function onScroll(e) {
      if (listRef.current?.contains(e.target)) return;
      onClose();
    }
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onClose);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onClose);
    };
  }, [onClose]);

  return createPortal(
    <div
      ref={listRef}
      role="listbox"
      style={style}
      className="z-[60] max-h-60 overflow-y-auto rounded-xl border border-[var(--color-border)] bg-white py-1 shadow-xl"
      onMouseDown={(e) => e.preventDefault()} // keep focus on the input
    >
      {TIME_OPTIONS.map((opt) => {
        const active = opt.value === (value || "").slice(0, 5);
        return (
          <button
            key={opt.value}
            type="button"
            role="option"
            aria-selected={active}
            data-active={active}
            onClick={() => onPick(opt.value)}
            className={
              "block w-full px-3 py-1.5 text-left text-sm tabular-nums transition-colors " +
              (active
                ? "bg-[var(--color-brand)] text-white"
                : "text-slate-700 hover:bg-[var(--color-brand-soft)]")
            }
          >
            {opt.label}
          </button>
        );
      })}
    </div>,
    document.body
  );
}

function PickerInput({ type, value, onChange, ...rest }) {
  const ref = React.useRef(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const isTimey = type === "time" || type === "datetime-local";
  const hasMenu = type === "time";

  const closeMenu = React.useCallback(() => setMenuOpen(false), []);

  // Wheel must be a non-passive native listener — React's synthetic onWheel
  // cannot preventDefault, so the page would scroll as well as the value step.
  React.useEffect(() => {
    const el = ref.current;
    if (!el || !isTimey) return undefined;
    function handleWheel(e) {
      if (document.activeElement !== el) return;
      e.preventDefault();
      const dir = e.deltaY < 0 ? 1 : -1;
      // Shift scrolls by the hour for crossing a morning quickly.
      const step = e.shiftKey ? 60 : WHEEL_STEP_MINUTES;
      const today = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      const todayIso = `${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}`;
      const next = stepTimeValue(el.value, type, dir * step, todayIso);
      if (next !== el.value) onChange({ target: { value: next } });
    }
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [type, isTimey, onChange]);

  function handleClick(e) {
    if (hasMenu) {
      setMenuOpen(true);
      return;
    }
    // Date fields: every browser ships a calendar, so ask for it. showPicker
    // throws if unsupported or called outside a user gesture.
    try {
      e.currentTarget.showPicker?.();
    } catch {
      /* fall back to the browser's own affordance */
    }
  }

  return (
    <>
      <input
        ref={ref}
        type={type}
        value={value}
        onChange={onChange}
        onClick={handleClick}
        onBlur={hasMenu ? closeMenu : undefined}
        {...rest}
      />
      {menuOpen && ref.current ? (
        <TimeMenu
          anchor={ref.current}
          value={value}
          onClose={closeMenu}
          onPick={(v) => {
            onChange({ target: { value: v } });
            closeMenu();
          }}
        />
      ) : null}
    </>
  );
}

// Text-button used for "+ New module" / "+ Add slot". Keeps the accessible
// name identical to the old plain-text buttons the tests query by.
function InlineAction({ onClick, children }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-sm font-medium text-[var(--color-brand)] transition-colors hover:bg-[var(--color-brand-soft)] focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30"
    >
      {children}
    </button>
  );
}

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
    <form onSubmit={handleSubmit} className="space-y-6">
      {/* Headline field: the title carries the most weight, so it gets a
          larger type size than the fields beneath it. */}
      <div>
        <label className={LABEL}>
          Title <span className="text-[var(--color-danger)]">*</span>
        </label>
        <input
          aria-label="Title *"
          value={form.title}
          onChange={(e) => update("title", e.target.value)}
          placeholder="e.g. CRISPR Module 1 at Franklin Elementary"
          className={`${FIELD} text-base font-medium`}
          required
        />
      </div>
      <div>
        <label className={LABEL}>Description</label>
        <textarea
          aria-label="Description"
          value={form.description || ""}
          onChange={(e) => update("description", e.target.value)}
          rows={3}
          placeholder="Optional — what volunteers should know before signing up"
          className={`${FIELD} resize-y leading-relaxed`}
        />
      </div>

      <FormSection icon={MapPin} title="Where">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={LABEL}>Location</label>
            <input
              aria-label="Location"
              value={form.location || ""}
              onChange={(e) => update("location", e.target.value)}
              placeholder="Room, building, or address"
              className={FIELD}
            />
          </div>
          <div>
            <label className={LABEL}>School</label>
            <input
              aria-label="School"
              value={form.school || ""}
              onChange={(e) => update("school", e.target.value)}
              className={FIELD}
              placeholder="Optional"
            />
          </div>
        </div>
      </FormSection>

      <FormSection icon={CalendarClock} title="When">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={LABEL}>
              Start <span className="text-[var(--color-danger)]">*</span>
            </label>
            <PickerInput
              aria-label="Start *"
              type="datetime-local"
              value={form.start_date}
              onChange={(e) => update("start_date", e.target.value)}
              className={FIELD}
              required
            />
          </div>
          <div>
            <label className={LABEL}>
              End <span className="text-[var(--color-danger)]">*</span>
            </label>
            <PickerInput
              aria-label="End *"
              type="datetime-local"
              value={form.end_date}
              onChange={(e) => update("end_date", e.target.value)}
              className={FIELD}
              required
            />
          </div>
          <div>
            <label className={LABEL}>Max signups per volunteer</label>
            <input
              type="number"
              min="1"
              value={form.max_signups_per_user}
              onChange={(e) => update("max_signups_per_user", e.target.value)}
              className={FIELD}
              placeholder="No limit"
            />
          </div>
          <div>
            <label className={LABEL}>Visibility</label>
            <select
              value={form.visibility}
              onChange={(e) => update("visibility", e.target.value)}
              className={FIELD}
            >
              <option value="public">Public</option>
              <option value="private">Private</option>
            </select>
          </div>
        </div>
      </FormSection>

      <FormSection
        icon={GraduationCap}
        title="Module *"
        hint="Orientation credit is scoped per module — volunteers who orient for one module don't automatically get credit for others."
        action={
          <InlineAction onClick={() => setShowNewModule(true)}>
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            New module
          </InlineAction>
        }
      >
        <select
          aria-label="Module *"
          value={form.module_slug}
          onChange={(e) => update("module_slug", e.target.value)}
          className={FIELD}
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
      </FormSection>

      <NewModuleDialog
        open={showNewModule}
        onCancel={() => setShowNewModule(false)}
        onCreated={(m) => {
          modulesQ.refetch();
          update("module_slug", m.slug);
          setShowNewModule(false);
        }}
      />

      <FormSection
        icon={LayoutGrid}
        title="Slots"
        action={
          <InlineAction onClick={addSlot}>
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            Add slot
          </InlineAction>
        }
      >
        {slots.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-8 text-center">
            <p className="text-sm text-[var(--color-fg-muted)]">
              No slots yet — add at least one so volunteers can sign up.
            </p>
            <button
              type="button"
              onClick={addSlot}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-brand)] px-3 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:brightness-110 focus:outline-none focus:ring-4 focus:ring-[var(--color-brand)]/25"
            >
              <Plus className="h-4 w-4" strokeWidth={2.5} />
              Add slot
            </button>
          </div>
        ) : (
          <ul className="space-y-3">
            {slots.map((s, i) => {
              const removeDisabled = isEdit && s.current_count > 0;
              const isOrientation = s.slot_type === "orientation";
              return (
                <li
                  key={s.id || `new-${i}`}
                  className="group relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-[0_2px_10px_rgba(15,23,42,0.07)]"
                  data-testid={`slot-row-${i}`}
                >
                  {/* Colour spine: orientation slots read differently at a
                      glance from ordinary class periods. */}
                  <span
                    aria-hidden="true"
                    className={`absolute inset-y-0 left-0 w-1 ${
                      isOrientation
                        ? "bg-[var(--color-accent)]"
                        : "bg-[var(--color-brand)]"
                    }`}
                  />
                  <div className="flex items-center justify-between gap-3 mb-3 pl-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
                      Slot {i + 1}
                    </span>
                    <div className="flex items-center gap-3">
                      {isEdit && s.current_count > 0 ? (
                        <span className="rounded-full bg-[var(--color-brand-soft)] px-2 py-0.5 text-xs font-medium text-[var(--color-brand)]">
                          {s.current_count} signup
                          {s.current_count === 1 ? "" : "s"}
                        </span>
                      ) : null}
                      <button
                        type="button"
                        onClick={() => removeSlot(i)}
                        disabled={removeDisabled}
                        title={
                          removeDisabled
                            ? `Has ${s.current_count} signup${s.current_count === 1 ? "" : "s"} — cannot remove`
                            : "Remove this slot"
                        }
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-[var(--color-danger)] transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Remove
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-6 gap-3 items-end pl-2">
                    <div className="md:col-span-1">
                      <label className={LABEL_SM}>Type</label>
                      <select
                        aria-label={`Slot ${i + 1} type`}
                        value={s.slot_type}
                        onChange={(e) => updateSlot(i, { slot_type: e.target.value })}
                        className={FIELD_SM}
                      >
                        <option value="period">Period</option>
                        <option value="orientation">Orientation</option>
                      </select>
                    </div>
                    <div className="md:col-span-1">
                      <label className={LABEL_SM}>Date</label>
                      <PickerInput
                        type="date"
                        aria-label={`Slot ${i + 1} date`}
                        value={s.date}
                        onChange={(e) => updateSlot(i, { date: e.target.value })}
                        className={FIELD_SM}
                      />
                    </div>
                    <div>
                      <label className={LABEL_SM}>Start</label>
                      <PickerInput
                        type="time"
                        aria-label={`Slot ${i + 1} start time`}
                        value={s.start_time}
                        onChange={(e) => updateSlot(i, { start_time: e.target.value })}
                        className={FIELD_SM}
                      />
                    </div>
                    <div>
                      <label className={LABEL_SM}>End</label>
                      <PickerInput
                        type="time"
                        aria-label={`Slot ${i + 1} end time`}
                        value={s.end_time}
                        onChange={(e) => updateSlot(i, { end_time: e.target.value })}
                        className={FIELD_SM}
                      />
                    </div>
                    <div>
                      <label className={LABEL_SM}>Capacity</label>
                      <input
                        type="number"
                        min="1"
                        aria-label={`Slot ${i + 1} capacity`}
                        value={s.capacity}
                        onChange={(e) => updateSlot(i, { capacity: e.target.value })}
                        className={FIELD_SM}
                      />
                    </div>
                    <div>
                      <label className={LABEL_SM}>Location</label>
                      <input
                        aria-label={`Slot ${i + 1} location`}
                        value={s.location}
                        onChange={(e) => updateSlot(i, { location: e.target.value })}
                        placeholder="(uses event)"
                        className={FIELD_SM}
                      />
                    </div>
                  </div>
                  {slotErrors[i] ? (
                    <p
                      className="mt-3 ml-2 rounded-md bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-700"
                      role="alert"
                      data-testid={`slot-error-${i}`}
                    >
                      {slotErrors[i]}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </FormSection>

      {error && (
        <p
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-sm font-medium text-red-700"
          role="alert"
        >
          {error}
        </p>
      )}

      {/* Sticky action bar: the form is long enough that Save would otherwise
          scroll out of reach on a laptop screen. */}
      <div className="sticky bottom-0 -mx-6 -mb-5 flex justify-end gap-2 border-t border-[var(--color-border)] bg-white/95 px-6 py-4 backdrop-blur">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg px-4 py-2.5 text-sm font-medium text-[var(--color-fg-muted)] transition-colors hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-slate-300"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex items-center gap-2 rounded-lg bg-[var(--color-brand)] px-5 py-2.5 text-sm font-semibold text-white shadow-sm transition-all hover:brightness-110 focus:outline-none focus:ring-4 focus:ring-[var(--color-brand)]/30 disabled:cursor-not-allowed disabled:opacity-50"
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
      <AdminPageHeader
        title="Events"
        subtitle="All events in the system. Create, edit, or delete events here."
      >
        <button
          onClick={() => {
            setEditing(null);
            setDrawerMode("create");
          }}
          className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow"
        >
          + New event
        </button>
      </AdminPageHeader>

      <div className="flex flex-wrap items-center gap-4">
        <input
          placeholder="Search by title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[20rem] rounded-lg border border-gray-300 px-3 py-2 text-sm"
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
        <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white shadow-sm">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-600">
              <tr>
                <th className="py-3 px-4">Title</th>
                <th className="py-3 px-4">Start</th>
                <th className="py-3 px-4">End</th>
                <th className="py-3 px-4">Location</th>
                <th className="py-3 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((e) => (
                <tr key={e.id} className="hover:bg-gray-50">
                  <td className="py-3 px-4 font-semibold">
                    <Link
                      to={`/admin/events/${e.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      {e.title || "(untitled)"}
                    </Link>
                  </td>
                  <td className="py-3 px-4 text-gray-800">{fmtDateTime(e.start_date)}</td>
                  <td className="py-3 px-4 text-gray-800">{fmtDateTime(e.end_date)}</td>
                  <td className="py-3 px-4 text-gray-800">{e.location || "—"}</td>
                  <td className="py-3 px-4 text-right space-x-5 whitespace-nowrap">
                    <button
                      onClick={() => {
                        setEditing(e);
                        setDrawerMode("edit");
                      }}
                      className="text-blue-600 hover:underline font-medium"
                    >
                      Edit
                    </button>
                    <button
                      onClick={() => cloneM.mutate(e.id)}
                      className="text-gray-700 hover:underline font-medium"
                    >
                      Clone
                    </button>
                    <button
                      onClick={() => setDeleting(e)}
                      className="text-red-600 hover:underline font-medium"
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

      <FormModal
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
      </FormModal>

      <FormModal
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
      </FormModal>

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

// Shared with the event page's "Event settings" modal so there is exactly one
// event form and one slot-save path, not a second copy that drifts.
export { EventForm, applySlotDiff };
