import React, { useEffect, useMemo, useState } from "react";
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
import {
  useSelectedQuarter,
  ALL_QUARTERS,
} from "../../state/QuarterSelectionContext";
import { toast } from "../../state/toast";
import AdminPageHeader from "../../components/admin/AdminPageHeader";
import FormModal from "../../components/admin/FormModal";
import DuplicateEventModal from "../../components/admin/DuplicateEventModal";
import ConfirmDialog from "../../components/ui/ConfirmDialog";
import { fmtVenueDateTime } from "../../lib/venueTime";

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

// Venue time, not browser time: see src/lib/venueTime.js for the event that
// claimed to end on a Saturday.
function fmtDateTime(iso) {
  return fmtVenueDateTime(iso);
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
    // no id → this is a new slot when diffing.
    // Orientation is the only kind a slot row can be now: a period slot has to
    // belong to a shift, so it is created through the shift instead.
    slot_type: "orientation",
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

// ---------------------------------------------------------------------------
// Shift form shape (2026-08-02 shifts design)
//
// A shift is the bookable unit: a name, a capacity, and one or more sessions.
// The sessions are ordinary period slots under the hood, but the form never
// treats them as independently bookable — capacity lives on the shift, so a
// session row has no capacity field at all.
// ---------------------------------------------------------------------------

function loadedSessionToForm(session) {
  const pad = (n) => String(n).padStart(2, "0");
  const start = new Date(session.start_time);
  const end = new Date(session.end_time);
  const fmtTime = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return {
    id: session.id,
    name: session.name || "",
    date:
      session.date ||
      `${start.getFullYear()}-${pad(start.getMonth() + 1)}-${pad(start.getDate())}`,
    start_time: fmtTime(start),
    end_time: fmtTime(end),
    location: session.location || "",
  };
}

function sessionsInOrder(shift) {
  return [...(shift.sessions || [])].sort(
    (a, b) =>
      (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
      String(a.start_time).localeCompare(String(b.start_time)),
  );
}

function loadedShiftToForm(shift) {
  return {
    id: shift.id,
    name: shift.name || "",
    capacity: String(shift.capacity ?? ""),
    // `current_count` gates removal the same way a slot's does: you cannot
    // delete a bundle somebody is holding a seat in.
    current_count: Number(shift.current_count || 0),
    sessions: sessionsInOrder(shift).map(loadedSessionToForm),
    // Open/closed lives on the row itself so reordering carries it along —
    // an index-keyed Set would hand the state to whichever shift moved in.
    _expanded: false,
  };
}

function newEmptySession(defaults = {}) {
  return {
    name: "",
    date: defaults.date || "",
    start_time: "",
    end_time: "",
    location: defaults.location || "",
  };
}

function newEmptyShift(defaults = {}) {
  return {
    name: "",
    capacity: "",
    current_count: 0,
    // A shift with no sessions is not bookable, and the API rejects it, so a
    // fresh shift starts with one row rather than an empty list.
    sessions: [newEmptySession(defaults)],
    _expanded: true,
  };
}

function sessionFormToApiPayload(session, index) {
  return {
    name: session.name?.trim() || null,
    date: session.date || null,
    start_time: combineDateTime(session.date, session.start_time),
    end_time: combineDateTime(session.date, session.end_time),
    location: session.location?.trim() || null,
    sort_order: index,
  };
}

function shiftFormToApiPayload(shift, index = 0) {
  const name = shift.name?.trim();
  return {
    // Omitted rather than sent blank, so the payload says "no name given" and
    // the server generates one. JSON.stringify drops undefined keys.
    name: name || undefined,
    capacity: Number(shift.capacity),
    sort_order: index,
    sessions: shift.sessions.map(sessionFormToApiPayload),
  };
}

function sessionChanged(a, b) {
  return (
    (a.name || "") !== (b.name || "") ||
    a.date !== b.date ||
    a.start_time !== b.start_time ||
    a.end_time !== b.end_time ||
    (a.location || "") !== (b.location || "")
  );
}

function validateShift(shift, eventStartIso, eventEndIso) {
  // Name is optional (2026-08-14). Left blank, the server names the shift after
  // its first session ("Tue 9:00-10:30") — the same format migration 0037 used,
  // so a generated name and a migrated one read identically in the roster.
  // Deliberately not generated here: the format is timezone-sensitive and
  // belongs in one place, shift_service.default_shift_name.
  const cap = Number(shift.capacity);
  if (!Number.isFinite(cap) || cap <= 0) return "Capacity must be a positive integer.";
  if (!shift.sessions?.length) return "A shift needs at least one session.";
  const evStartDate = localDatePart(eventStartIso);
  const evEndDate = localDatePart(eventEndIso);
  for (let i = 0; i < shift.sessions.length; i += 1) {
    const s = shift.sessions[i];
    const where = `Session ${i + 1}: `;
    if (!s.date) return `${where}date is required.`;
    if (!s.start_time || !s.end_time) return `${where}start and end times are required.`;
    const start = new Date(`${s.date}T${s.start_time}`);
    const end = new Date(`${s.date}T${s.end_time}`);
    if (!(end > start)) return `${where}end time must be after start time.`;
    if (evStartDate && s.date < evStartDate) return `${where}date is before the event start.`;
    if (evEndDate && s.date > evEndDate) return `${where}date is after the event end.`;
  }
  return null;
}

// Shift-level diff. Sessions are diffed inside each surviving shift because
// they have their own endpoints — a shift PATCH carries name/capacity/order
// only, never its session list.
function diffShifts(initial, draft) {
  const initialById = new Map((initial || []).map((s) => [s.id, s]));
  const draftIds = new Set(draft.filter((s) => s.id).map((s) => s.id));
  const creates = [];
  const updates = [];
  draft.forEach((shift, index) => {
    if (!shift.id) {
      creates.push({ shift, index });
      return;
    }
    const before = initialById.get(shift.id);
    if (!before) return;
    const fieldsChanged =
      before.name !== shift.name ||
      Number(before.capacity) !== Number(shift.capacity) ||
      (initial || []).findIndex((s) => s.id === shift.id) !== index;
    const sessionsBefore = new Map((before.sessions || []).map((s) => [s.id, s]));
    const draftSessionIds = new Set(shift.sessions.filter((s) => s.id).map((s) => s.id));
    const sessionCreates = shift.sessions
      .map((s, sessionIndex) => ({ session: s, index: sessionIndex }))
      .filter(({ session }) => !session.id);
    // Ordering rides along on the PATCH rather than a separate reorder call:
    // every session carries its index, so a pure drag with no field edits is
    // still a set of updates.
    const sessionUpdates = [];
    shift.sessions.forEach((s, sessionIndex) => {
      if (!s.id || !sessionsBefore.has(s.id)) return;
      const wasAt = (before.sessions || []).findIndex((b) => b.id === s.id);
      if (sessionChanged(sessionsBefore.get(s.id), s) || wasAt !== sessionIndex) {
        sessionUpdates.push({ session: s, index: sessionIndex });
      }
    });
    const sessionDeletes = [...sessionsBefore.keys()].filter(
      (id) => !draftSessionIds.has(id),
    );
    if (
      fieldsChanged ||
      sessionCreates.length ||
      sessionUpdates.length ||
      sessionDeletes.length
    ) {
      updates.push({
        shift,
        index,
        fieldsChanged,
        sessionCreates,
        sessionUpdates,
        sessionDeletes,
      });
    }
  });
  const deletes = [...initialById.keys()].filter((id) => !draftIds.has(id));
  return { creates, updates, deletes };
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
      const created = await api.admin.modules.create({
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

function EventForm({
  initial,
  mode,
  onSubmit,
  onCancel,
  submitting,
  submitLabel = "Save",
  onDirtyChange,
}) {
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
    queryKey: ["adminModulesForEventForm"],
    queryFn: () => api.admin.modules.list(),
    staleTime: 30_000,
  });
  const modules = Array.isArray(modulesQ.data) ? modulesQ.data : [];
  // `initial.slots` is the flat list — orientation slots plus every shift's
  // sessions. Only the orientation ones are editable here; sessions are edited
  // inside their shift.
  const [slots, setSlots] = useState(() =>
    (initial?.slots || [])
      .filter((s) => (s.slot_type || "period") === "orientation")
      .map(loadedSlotToForm),
  );
  const [shifts, setShifts] = useState(() =>
    initial?.shifts?.length
      ? initial.shifts.map(loadedShiftToForm)
      : isEdit
        ? []
        : [newEmptyShift()],
  );
  const [error, setError] = useState(null);
  const [slotErrors, setSlotErrors] = useState({});
  const [shiftErrors, setShiftErrors] = useState({});

  // Everything the operator typed lives in this component, and the modal
  // unmounts it on close — so the modal has to know whether closing would
  // destroy anything before it lets a stray backdrop click through. The
  // baseline is whatever the form was built with, captured once at mount;
  // anything different from that counts as unsaved work.
  const pristine = React.useRef(null);
  const current = JSON.stringify({ form, slots, shifts });
  if (pristine.current === null) pristine.current = current;
  useEffect(() => {
    onDirtyChange?.(current !== pristine.current);
  }, [current, onDirtyChange]);

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

  // --- shifts -------------------------------------------------------------
  function updateShift(index, patch) {
    setShifts((arr) => arr.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function addShift() {
    setShifts((arr) => [
      ...arr,
      newEmptyShift({
        date: form.start_date ? form.start_date.slice(0, 10) : "",
        location: form.location,
      }),
    ]);
  }

  function removeShift(index) {
    setShifts((arr) => arr.filter((_, i) => i !== index));
    setShiftErrors((errs) => {
      const next = { ...errs };
      delete next[index];
      return next;
    });
  }

  function moveShift(index, delta) {
    setShifts((arr) => {
      const to = index + delta;
      if (to < 0 || to >= arr.length) return arr;
      const next = [...arr];
      [next[index], next[to]] = [next[to], next[index]];
      return next;
    });
    setShiftErrors({});
  }

  function updateSession(shiftIndex, sessionIndex, patch) {
    setShifts((arr) =>
      arr.map((s, i) =>
        i === shiftIndex
          ? {
              ...s,
              sessions: s.sessions.map((sess, j) =>
                j === sessionIndex ? { ...sess, ...patch } : sess,
              ),
            }
          : s,
      ),
    );
  }

  function addSession(shiftIndex) {
    setShifts((arr) =>
      arr.map((s, i) =>
        i === shiftIndex
          ? {
              ...s,
              sessions: [
                ...s.sessions,
                newEmptySession({
                  // A second session almost always shares the first one's day
                  // and room, so seed from it rather than from the event.
                  date: s.sessions.at(-1)?.date || "",
                  location: s.sessions.at(-1)?.location || form.location,
                }),
              ],
            }
          : s,
      ),
    );
  }

  function removeSession(shiftIndex, sessionIndex) {
    setShifts((arr) =>
      arr.map((s, i) =>
        i === shiftIndex
          ? { ...s, sessions: s.sessions.filter((_, j) => j !== sessionIndex) }
          : s,
      ),
    );
  }

  function moveSession(shiftIndex, sessionIndex, delta) {
    setShifts((arr) =>
      arr.map((s, i) => {
        if (i !== shiftIndex) return s;
        const to = sessionIndex + delta;
        if (to < 0 || to >= s.sessions.length) return s;
        const next = [...s.sessions];
        [next[sessionIndex], next[to]] = [next[to], next[sessionIndex]];
        return { ...s, sessions: next };
      }),
    );
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setSlotErrors({});
    setShiftErrors({});

    if (!form.title.trim()) return setError("Title is required.");
    if (!form.module_slug)
      return setError("Pick a module, or create one with '+ New module'.");
    if (!form.start_date || !form.end_date)
      return setError("Start and end times are required.");
    if (new Date(form.end_date) <= new Date(form.start_date))
      return setError("Event end time must be after start time.");

    if (slots.length === 0 && shifts.length === 0) {
      return setError("Add at least one shift or orientation slot.");
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

    const perShiftErrors = {};
    shifts.forEach((s, i) => {
      const err = validateShift(s, startIso, endIso);
      if (err) perShiftErrors[i] = err;
    });
    if (Object.keys(perShiftErrors).length) {
      setShiftErrors(perShiftErrors);
      return setError("Fix the shift errors below before saving.");
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

    const initialSlotsFormShape = (initial?.slots || [])
      .filter((s) => (s.slot_type || "period") === "orientation")
      .map(loadedSlotToForm);
    const initialShiftsFormShape = (initial?.shifts || []).map(loadedShiftToForm);

    try {
      await onSubmit({
        metadata,
        slots,
        shifts,
        initialSlots: initialSlotsFormShape,
        initialShifts: initialShiftsFormShape,
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

      {/* Where + When sit side by side once the widened modal has room. */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2 lg:gap-x-8 lg:[&>section]:min-w-0">
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
            <label className={LABEL}>Max shifts per volunteer</label>
            <input
              type="number"
              min="1"
              value={form.max_signups_per_user}
              onChange={(e) => update("max_signups_per_user", e.target.value)}
              className={FIELD}
              placeholder="No limit"
            />
            {/* K8: this box did nothing at all until the backend started
                reading it. Say what it covers now that it is real —
                orientation is exempt, or a cap of 1 would make an
                orientation-required event unbookable. */}
            <p className="mt-1 text-xs text-[var(--color-fg-muted)]">
              Leave blank for no limit. Orientation sessions don&apos;t count.
            </p>
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
      </div>

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

      {/* Shifts — the bookable unit. Capacity and the waitlist live here, not
          on the sessions inside, so a volunteer says yes to the whole bundle
          or not at all. */}
      <FormSection
        icon={LayoutGrid}
        title="Shifts"
        hint="A shift is what volunteers book. Signing up commits them to every session inside it."
        action={
          <InlineAction onClick={addShift}>
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            Add shift
          </InlineAction>
        }
      >
        {shifts.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-8 text-center">
            <p className="text-sm text-[var(--color-fg-muted)]">
              No shifts yet — add at least one so volunteers can sign up.
            </p>
            <button
              type="button"
              onClick={addShift}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-brand)] px-3 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:brightness-110 focus:outline-none focus:ring-4 focus:ring-[var(--color-brand)]/25"
            >
              <Plus className="h-4 w-4" strokeWidth={2.5} />
              Add shift
            </button>
          </div>
        ) : (
          <ul className="space-y-3">
            {shifts.map((sh, i) => {
              const removeDisabled = isEdit && sh.current_count > 0;
              return (
                <li
                  key={sh.id || `new-shift-${i}`}
                  className="group relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-[0_2px_10px_rgba(15,23,42,0.07)]"
                  data-testid={`shift-row-${i}`}
                >
                  <span
                    aria-hidden="true"
                    className="absolute inset-y-0 left-0 w-1 bg-[var(--color-brand)]"
                  />
                  <div className="flex items-center justify-between gap-3 mb-3 pl-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
                      Shift {i + 1}
                    </span>
                    <div className="flex items-center gap-2">
                      {isEdit && sh.current_count > 0 ? (
                        <span className="rounded-full bg-[var(--color-brand-soft)] px-2 py-0.5 text-xs font-medium text-[var(--color-brand)]">
                          {sh.current_count} signup
                          {sh.current_count === 1 ? "" : "s"}
                        </span>
                      ) : null}
                      {/* Order is what volunteers see on the public page, so it
                          is set here rather than derived from the times. */}
                      <button
                        type="button"
                        onClick={() => moveShift(i, -1)}
                        disabled={i === 0}
                        aria-label={`Move shift ${i + 1} up`}
                        className="rounded-md px-1.5 py-1 text-xs text-[var(--color-fg-muted)] transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        ↑
                      </button>
                      <button
                        type="button"
                        onClick={() => moveShift(i, 1)}
                        disabled={i === shifts.length - 1}
                        aria-label={`Move shift ${i + 1} down`}
                        className="rounded-md px-1.5 py-1 text-xs text-[var(--color-fg-muted)] transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        ↓
                      </button>
                      <button
                        type="button"
                        onClick={() => removeShift(i)}
                        disabled={removeDisabled}
                        title={
                          removeDisabled
                            ? `Has ${sh.current_count} signup${sh.current_count === 1 ? "" : "s"} — cannot remove`
                            : "Remove this shift"
                        }
                        className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-[var(--color-danger)] transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        Remove
                      </button>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 items-end pl-2">
                    <div className="md:col-span-2">
                      <label className={LABEL_SM}>
                        Name{" "}
                        <span className="font-normal normal-case text-[var(--color-fg-muted)]">
                          — optional
                        </span>
                      </label>
                      <input
                        aria-label={`Shift ${i + 1} name`}
                        value={sh.name}
                        onChange={(e) => updateShift(i, { name: e.target.value })}
                        placeholder="Leave blank to name it by time"
                        className={FIELD_SM}
                      />
                    </div>
                    <div>
                      <label className={LABEL_SM}>Capacity</label>
                      <input
                        type="number"
                        min="1"
                        aria-label={`Shift ${i + 1} capacity`}
                        value={sh.capacity}
                        onChange={(e) => updateShift(i, { capacity: e.target.value })}
                        className={FIELD_SM}
                      />
                    </div>
                    <div>
                      <button
                        type="button"
                        onClick={() => updateShift(i, { _expanded: !sh._expanded })}
                        aria-expanded={Boolean(sh._expanded)}
                        className="w-full rounded-md border border-[var(--color-border)] px-2.5 py-1.5 text-sm font-medium text-[var(--color-fg-muted)] transition-colors hover:bg-slate-50"
                      >
                        {sh._expanded ? "Hide" : "Show"} {sh.sessions.length} session
                        {sh.sessions.length === 1 ? "" : "s"}
                      </button>
                    </div>
                  </div>

                  {sh._expanded ? (
                    <div className="mt-4 ml-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
                      <div className="flex items-center justify-between gap-3 mb-2">
                        <span className="text-[11px] font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
                          Sessions
                        </span>
                        <InlineAction onClick={() => addSession(i)}>
                          <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
                          Add session
                        </InlineAction>
                      </div>
                      <ul className="space-y-3">
                        {sh.sessions.map((sess, j) => (
                          <li
                            key={sess.id || `new-session-${j}`}
                            className="rounded-md border border-[var(--color-border)] bg-white p-3"
                            data-testid={`shift-${i}-session-${j}`}
                          >
                            <div className="flex items-center justify-between gap-2 mb-2">
                              <span className="text-[11px] font-medium text-[var(--color-fg-muted)]">
                                Session {j + 1}
                              </span>
                              <div className="flex items-center gap-1">
                                <button
                                  type="button"
                                  onClick={() => moveSession(i, j, -1)}
                                  disabled={j === 0}
                                  aria-label={`Move shift ${i + 1} session ${j + 1} up`}
                                  className="rounded px-1.5 py-0.5 text-xs text-[var(--color-fg-muted)] hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                  ↑
                                </button>
                                <button
                                  type="button"
                                  onClick={() => moveSession(i, j, 1)}
                                  disabled={j === sh.sessions.length - 1}
                                  aria-label={`Move shift ${i + 1} session ${j + 1} down`}
                                  className="rounded px-1.5 py-0.5 text-xs text-[var(--color-fg-muted)] hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                  ↓
                                </button>
                                {/* A shift must keep one session — the API
                                    refuses the last delete, so don't offer it. */}
                                <button
                                  type="button"
                                  onClick={() => removeSession(i, j)}
                                  disabled={sh.sessions.length === 1}
                                  aria-label={`Remove shift ${i + 1} session ${j + 1}`}
                                  title={
                                    sh.sessions.length === 1
                                      ? "A shift must keep at least one session"
                                      : "Remove this session"
                                  }
                                  className="rounded px-1.5 py-0.5 text-xs font-medium text-[var(--color-danger)] hover:bg-red-50 disabled:cursor-not-allowed disabled:text-slate-400 disabled:hover:bg-transparent"
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                </button>
                              </div>
                            </div>
                            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 items-end">
                              <div>
                                <label className={LABEL_SM}>Name</label>
                                <input
                                  aria-label={`Shift ${i + 1} session ${j + 1} name`}
                                  value={sess.name}
                                  onChange={(e) =>
                                    updateSession(i, j, { name: e.target.value })
                                  }
                                  placeholder="e.g. Period 1"
                                  className={FIELD_SM}
                                />
                              </div>
                              <div>
                                <label className={LABEL_SM}>Date</label>
                                <PickerInput
                                  type="date"
                                  aria-label={`Shift ${i + 1} session ${j + 1} date`}
                                  value={sess.date}
                                  onChange={(e) =>
                                    updateSession(i, j, { date: e.target.value })
                                  }
                                  className={FIELD_SM}
                                />
                              </div>
                              <div>
                                <label className={LABEL_SM}>Start</label>
                                <PickerInput
                                  type="time"
                                  aria-label={`Shift ${i + 1} session ${j + 1} start time`}
                                  value={sess.start_time}
                                  onChange={(e) =>
                                    updateSession(i, j, { start_time: e.target.value })
                                  }
                                  className={FIELD_SM}
                                />
                              </div>
                              <div>
                                <label className={LABEL_SM}>End</label>
                                <PickerInput
                                  type="time"
                                  aria-label={`Shift ${i + 1} session ${j + 1} end time`}
                                  value={sess.end_time}
                                  onChange={(e) =>
                                    updateSession(i, j, { end_time: e.target.value })
                                  }
                                  className={FIELD_SM}
                                />
                              </div>
                              <div>
                                <label className={LABEL_SM}>Location</label>
                                <input
                                  aria-label={`Shift ${i + 1} session ${j + 1} location`}
                                  value={sess.location}
                                  onChange={(e) =>
                                    updateSession(i, j, { location: e.target.value })
                                  }
                                  placeholder="(uses event)"
                                  className={FIELD_SM}
                                />
                              </div>
                            </div>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {shiftErrors[i] ? (
                    <p
                      className="mt-3 ml-2 rounded-md bg-red-50 px-2.5 py-1.5 text-xs font-medium text-red-700"
                      role="alert"
                      data-testid={`shift-error-${i}`}
                    >
                      {shiftErrors[i]}
                    </p>
                  ) : null}
                </li>
              );
            })}
          </ul>
        )}
      </FormSection>

      {/* Orientation slots stay individually bookable — they are a one-off
          prerequisite, not part of a week's commitment, so they keep their own
          capacity and their own row. */}
      <FormSection
        icon={LayoutGrid}
        title="Orientation slots"
        hint="Optional. Booked one at a time, separately from shifts."
        action={
          <InlineAction onClick={addSlot}>
            <Plus className="h-3.5 w-3.5" strokeWidth={2.5} />
            Add orientation slot
          </InlineAction>
        }
      >
        {slots.length === 0 ? (
          <p className="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-5 text-center text-sm text-[var(--color-fg-muted)]">
            No orientation slots for this event.
          </p>
        ) : (
          <ul className="space-y-3">
            {slots.map((s, i) => {
              const removeDisabled = isEdit && s.current_count > 0;
              return (
                <li
                  key={s.id || `new-${i}`}
                  className="group relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-white p-4 shadow-[0_1px_2px_rgba(15,23,42,0.04)] transition-shadow hover:shadow-[0_2px_10px_rgba(15,23,42,0.07)]"
                  data-testid={`slot-row-${i}`}
                >
                  <span
                    aria-hidden="true"
                    className="absolute inset-y-0 left-0 w-1 bg-[var(--color-accent)]"
                  />
                  <div className="flex items-center justify-between gap-3 mb-3 pl-2">
                    <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
                      Orientation {i + 1}
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
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-3 items-end pl-2">
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
          {submitting ? "Saving…" : submitLabel}
        </button>
      </div>
    </form>
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

// The shift twin of applySlotDiff. Session ops inside one shift run in
// sequence — the backend rejects adding or removing a session once the shift
// has signups, and a delete that would empty the shift, so the order the
// admin sees is the order those refusals arrive in.
async function applyShiftDiff(eventId, initialShifts, draftShifts) {
  const { creates, updates, deletes } = diffShifts(initialShifts, draftShifts);
  const failed = [];

  async function run(label, work) {
    try {
      await work();
    } catch (err) {
      // Keep the reason. This used to be a bare `catch {}`, so a refusal the
      // backend had explained ("… has ended and is read-only", "cannot change
      // sessions once a shift has signups") reached the admin as a shift label
      // and nothing else — a save that failed for a knowable reason looked
      // arbitrary.
      const why = err?.message ? `: ${err.message}` : "";
      failed.push(`${label}${why}`);
    }
  }

  await Promise.all([
    ...creates.map(({ shift, index }) =>
      run(`new shift "${shift.name || index + 1}"`, () =>
        api.shifts.create(eventId, shiftFormToApiPayload(shift, index)),
      ),
    ),
    ...deletes.map((id) => run(`delete shift ${id}`, () => api.shifts.delete(id))),
    ...updates.map((u) =>
      run(`shift "${u.shift.name}"`, async () => {
        if (u.fieldsChanged) {
          const name = u.shift.name?.trim();
          await api.shifts.update(u.shift.id, {
            // Clearing the box on an *existing* shift leaves its name alone
            // rather than blanking it — volunteers have already seen that label
            // in their confirmation email. The PATCH refuses an empty name, so
            // the key is omitted instead of sent empty.
            ...(name ? { name } : {}),
            capacity: Number(u.shift.capacity),
            sort_order: u.index,
          });
        }
        for (const id of u.sessionDeletes) {
          await api.shifts.deleteSession(id);
        }
        for (const { session, index } of u.sessionUpdates) {
          await api.shifts.updateSession(
            session.id,
            sessionFormToApiPayload(session, index),
          );
        }
        for (const { session, index } of u.sessionCreates) {
          await api.shifts.addSession(
            u.shift.id,
            sessionFormToApiPayload(session, index),
          );
        }
      }),
    ),
  ]);

  if (failed.length) {
    throw new Error(`Shift changes failed: ${failed.join(", ")}`);
  }
}

// fix/ux-quarter-batch — make an ended event unmistakable in the list.
// "Completed" = every slot was ended (events.completed_at is stamped);
// "Ended" = the dates went by but attendance was never closed out.
function EventStatusBadge({ event }) {
  if (event.completed_at) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
        ✓ Completed
      </span>
    );
  }
  if (new Date(event.end_date).getTime() < Date.now()) {
    return (
      <span className="inline-flex items-center rounded-full bg-gray-200 px-2 py-0.5 text-xs font-semibold text-gray-700">
        Ended — not closed out
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-xs font-semibold text-blue-800">
      Upcoming
    </span>
  );
}

export default function EventsSection() {
  useAdminPageTitle("Events");
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  // Default to everything — the quarter is the scope, the time filter is an
  // opt-in narrowing. (live quarter: all | upcoming | past;
  //  ended quarter:  all | completed | open)
  const [scope, setScope] = useState("all");
  const [drawerMode, setDrawerMode] = useState(null); // "create" | "edit"
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [duplicating, setDuplicating] = useState(null); // source event for the duplicate modal
  // Reported up from EventForm: true once the operator has typed something the
  // form would lose if the modal closed. Reset on every open so a previous
  // session's edits can't arm the discard prompt on a fresh form.
  const [formDirty, setFormDirty] = useState(false);
  useEffect(() => {
    setFormDirty(false);
  }, [drawerMode]);

  // fix/ux-quarter-batch: the list is quarter-scoped and shares its selection
  // with Overview / Manage Quarters. Default = the current quarter.
  const {
    quarters,
    viewingAll,
    selectedQuarter,
    setSelectedQuarterId,
  } = useSelectedQuarter();
  const quarterParam = !viewingAll && selectedQuarter ? selectedQuarter.id : null;

  // An ended quarter is history: nothing in it is "upcoming" and no new
  // events belong in it, so the page flips into a read-mostly mode.
  const todayIso = new Date().toISOString().slice(0, 10);
  const quarterEnded =
    !viewingAll && Boolean(selectedQuarter) && selectedQuarter.end_date < todayIso;

  // The filter options differ between live and ended quarters — reset when
  // the quarter context changes so a stale value can't blank the list.
  useEffect(() => {
    setScope("all");
  }, [quarterParam, viewingAll]);

  const q = useQuery({
    queryKey: ["adminEventsList", quarterParam || "all"],
    queryFn: () =>
      api.events.list(quarterParam ? { quarter_id: quarterParam } : undefined),
  });

  const events = q.data || [];

  const filtered = useMemo(() => {
    const now = Date.now();
    const term = search.toLowerCase().trim();
    // An event is "past" once its dates have gone by OR it was explicitly
    // completed (every slot ended) — ending an event files it under Past
    // immediately, and reopening it brings it back.
    const isPast = (e) =>
      Boolean(e.completed_at) || new Date(e.end_date).getTime() < now;
    return events
      .filter((e) => {
        if (quarterEnded) {
          // Everything in an ended quarter is past — filter by whether the
          // attendance was actually closed out instead.
          if (scope === "completed" && !e.completed_at) return false;
          if (scope === "open" && e.completed_at) return false;
        } else {
          if (scope === "upcoming" && isPast(e)) return false;
          if (scope === "past" && !isPast(e)) return false;
        }
        if (term && !(e.title || "").toLowerCase().includes(term)) return false;
        return true;
      })
      .sort((a, b) => new Date(a.start_date) - new Date(b.start_date));
  }, [events, search, scope, quarterEnded]);

  const createM = useMutation({
    mutationFn: ({ metadata, slots, shifts }) =>
      // One call: the create endpoint takes orientation slots and whole shifts
      // (sessions included), so a new event never lands half-built.
      api.events.create({
        ...metadata,
        slots: slots.map(slotFormToApiPayload),
        shifts: shifts.map(shiftFormToApiPayload),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["adminEventsList"] });
      setDrawerMode(null);
      toast.success("Event created.");
    },
  });

  const updateM = useMutation({
    mutationFn: async ({ id, metadata, slots, shifts, initialSlots, initialShifts }) => {
      await api.events.update(id, metadata);
      await applySlotDiff(id, initialSlots, slots);
      await applyShiftDiff(id, initialShifts, shifts);
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

  return (
    <div className="space-y-4">
      <AdminPageHeader
        title="Events"
        subtitle={
          viewingAll || !selectedQuarter
            ? "All events across every quarter. Create, edit, or delete events here."
            : quarterEnded
              ? `Everything that ran in ${selectedQuarter.display_name || "the selected quarter"} — rosters and stats are kept for looking back.`
              : `Events in ${selectedQuarter.display_name || "the selected quarter"} — upcoming and past. Create, edit, or delete events here.`
        }
      >
        {/* No new events in a quarter that's over — it's history. */}
        {quarterEnded ? null : (
          <button
            onClick={() => {
              setEditing(null);
              setDrawerMode("create");
            }}
            className="px-4 py-2 text-sm font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow"
          >
            + New event
          </button>
        )}
      </AdminPageHeader>

      {quarterEnded ? (
        <div
          data-testid="ended-quarter-strip"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-900"
        >
          <span>
            <span className="font-semibold">
              {selectedQuarter.display_name}
            </span>{" "}
            ended{" "}
            {new Date(
              `${selectedQuarter.end_date}T00:00:00`,
            ).toLocaleDateString("en-US", {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
            {selectedQuarter.archived_at ? " and is archived" : ""} — you're
            viewing its history. New events go in the current quarter.
          </span>
          <button
            type="button"
            onClick={() => setSelectedQuarterId(null)}
            className="font-semibold underline hover:no-underline"
          >
            Back to current quarter
          </button>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-4">
        <input
          placeholder="Search by title…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[20rem] rounded-lg border border-gray-300 px-3 py-2 text-sm"
        />
        {/* Quarter scope — shared with Overview, so switching here re-scopes
            the dashboard too. Archived quarters stay pickable: that's how
            past rosters and stats are revisited. */}
        <select
          aria-label="Quarter"
          value={viewingAll ? ALL_QUARTERS : selectedQuarter?.id || ALL_QUARTERS}
          onChange={(e) =>
            setSelectedQuarterId(
              e.target.value === ALL_QUARTERS ? ALL_QUARTERS : e.target.value,
            )
          }
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white"
        >
          {(quarters || []).map((qr) => (
            <option key={qr.id} value={qr.id}>
              {qr.display_name || `${qr.season} ${qr.year}`}
              {qr.archived_at ? " (archived)" : ""}
            </option>
          ))}
          <option value={ALL_QUARTERS}>All quarters</option>
        </select>
        <select
          aria-label="Time filter"
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm bg-white"
        >
          {quarterEnded ? (
            /* Nothing in an ended quarter is upcoming — filter by whether
               attendance was closed out instead. */
            <>
              <option value="all">All events</option>
              <option value="completed">Completed</option>
              <option value="open">Not closed out</option>
            </>
          ) : (
            <>
              <option value="all">All</option>
              <option value="upcoming">Upcoming</option>
              <option value="past">Past</option>
            </>
          )}
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
                <th className="py-3 px-4">Status</th>
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
                  <td className="py-3 px-4">
                    <EventStatusBadge event={e} />
                  </td>
                  <td className="py-3 px-4 text-gray-800">{fmtDateTime(e.start_date)}</td>
                  <td className="py-3 px-4 text-gray-800">{fmtDateTime(e.end_date)}</td>
                  <td className="py-3 px-4 text-gray-800">{e.location || "—"}</td>
                  <td className="py-3 px-4 text-right space-x-5 whitespace-nowrap">
                    {/* Sweep remediation task 5: the server now rejects
                        update/delete against an ended quarter's events
                        (422 QUARTER_READONLY), so those actions don't even
                        render here. Duplicate stays — it always creates the
                        copy in a target quarter, never the source's, so
                        re-running a past event from history keeps working. */}
                    {quarterEnded ? null : (
                      <button
                        onClick={() => {
                          setEditing(e);
                          setDrawerMode("edit");
                        }}
                        className="text-blue-600 hover:underline font-medium"
                      >
                        Edit
                      </button>
                    )}
                    <button
                      onClick={() => setDuplicating(e)}
                      className="text-gray-700 hover:underline font-medium"
                    >
                      Duplicate
                    </button>
                    {quarterEnded ? null : (
                      <button
                        onClick={() => setDeleting(e)}
                        className="text-red-600 hover:underline font-medium"
                      >
                        Delete
                      </button>
                    )}
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
        subtitle="Schedule the visit, pick its module, and lay out the volunteer slots."
        dirty={formDirty}
        onClose={() => setDrawerMode(null)}
      >
        <EventForm
          mode="create"
          onSubmit={(payload) => createM.mutateAsync(payload)}
          onCancel={() => setDrawerMode(null)}
          submitting={createM.isPending}
          onDirtyChange={setFormDirty}
        />
      </FormModal>

      <FormModal
        open={drawerMode === "edit"}
        title="Edit event"
        subtitle="Details and slot changes save together when you hit Save."
        dirty={formDirty}
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
            onDirtyChange={setFormDirty}
          />
        )}
      </FormModal>

      {/* Duplicate = prefilled create form targeting another quarter/week.
          Works from ended-quarter history too — that's the main use case:
          re-run a past event in the current quarter. */}
      <DuplicateEventModal
        open={!!duplicating}
        onClose={() => setDuplicating(null)}
        sourceEvent={duplicating}
        quarters={quarters}
      />

      {/* K14: this destroys the event, its slots and every signup on them, and
          the row it is launched from sits between Edit and Duplicate. Typing the
          title is the only thing that makes it impossible to delete the wrong
          event by muscle memory — the same bar the CCPA delete already sets. */}
      <ConfirmDialog
        open={!!deleting}
        title="Delete this event?"
        body={`This permanently deletes "${deleting?.title}", its slots and shifts, and every signup on them. Volunteers are not told. This cannot be undone.`}
        requireTyped={deleting?.title}
        requireTypedHint="Type the event title to confirm:"
        confirmLabel="Delete event"
        busyLabel="Deleting…"
        cancelLabel="Keep it"
        onCancel={() => setDeleting(null)}
        onConfirm={() => deleteM.mutate(deleting.id)}
        busy={deleteM.isPending}
      />
    </div>
  );
}

// Exports for tests
export { diffSlots, slotFormToApiPayload, validateSlot, loadedSlotToForm };
export { diffShifts, shiftFormToApiPayload, validateShift, loadedShiftToForm };

// Shared with the event page's "Event settings" modal so there is exactly one
// event form and one slot-save path, not a second copy that drifts.
export { EventForm, applySlotDiff, applyShiftDiff };
