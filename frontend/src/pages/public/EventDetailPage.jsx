// src/pages/public/EventDetailPage.jsx
//
// Volunteer-facing sign-up page.
//
// Two kinds of bookable thing, and they are shaped differently on purpose:
//   • Orientation slots are single sessions, so they get the two-layout split at
//     the Tailwind `md` (768px) breakpoint — a <table> on desktop, stacked cards
//     on mobile. Both live in the DOM at once, toggled by CSS visibility.
//   • Shifts (2026-08-02) are all-or-nothing bundles of sessions, so they are
//     cards at every width: a table row cannot hold the sessions inside a shift
//     without hiding the dates the volunteer needs in order to say yes.
//
// E2E CONTRACT (e2e/fixtures.js slotLabel/clickSlotByLabel):
//   • Desktop table: label cells are <div class="font-medium"> ("Orientation …")
//     with an in-row "Sign up" button.
//   • Mobile card / shift card: div.rounded-xl whose label is a
//     <p class="font-medium"> with an in-card "Sign up" button.
//   Only the layout visible at the current viewport is matched (`:visible`).
//
// SECURITY: No PII (name, email, phone) is logged, stored in localStorage/sessionStorage,
// or passed to analytics. Identity state lives only in React component state and is
// cleared on form reset or unmount.

import React, { useState, useMemo, useRef } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  XCircle,
  CalendarDays,
  Clock,
  MapPin,
  CheckCircle2,
  AlertCircle,
  Mail,
  ChevronDown,
  Users,
} from "lucide-react";

import api from "../../lib/api";
import { downloadIcs, buildGoogleCalendarUrl } from "../../lib/calendar";
import { toast } from "../../state/toast";
import {
  Button,
  Card,
  Input,
  Label,
  FieldError,
  Skeleton,
  EmptyState,
  ErrorState,
} from "../../components/ui";
import OrientationWarningModal from "../../components/OrientationWarningModal";
import SignupSuccessCard from "../../components/SignupSuccessCard";
import { fmtVenueDate, fmtVenueWeekday } from "../../lib/venueTime";

// ---------------------------------------------------------------------------
// Date/time helpers
// ---------------------------------------------------------------------------

function formatDate(isoString) {
  return fmtVenueDate(isoString);
}

function formatWeekday(isoString) {
  return fmtVenueWeekday(isoString);
}

function formatShortDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString.includes("T") ? isoString : `${isoString}T00:00:00`);
  return d.toLocaleDateString("en-US", { month: "2-digit", day: "2-digit", year: "numeric" });
}

// Slot datetimes arrive as UTC ISO strings. Render in venue timezone so all
// viewers see wall-clock at UCSB regardless of browser locale.
const VENUE_TZ = "America/Los_Angeles";

function formatTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d
    .toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      timeZone: VENUE_TZ,
    })
    .toLowerCase();
}

function formatDateRange(start, end) {
  if (!start) return "";
  const s = formatDate(start);
  const e = end ? formatDate(end) : null;
  return e && e !== s ? `${s} - ${e}` : s;
}

// ---------------------------------------------------------------------------
// Phone validation (PART-05) — accepts US-formatted and E.164.
// Exported only via internal use. Server-side Pydantic is authoritative.
// ---------------------------------------------------------------------------

export function isValidPhone(raw) {
  if (raw == null) return false;
  const trimmed = String(raw).trim();
  if (!trimmed) return false;
  // E.164: +[country code 1-9][7-14 more digits], total 8-15 digits after +.
  // If the string starts with '+', it MUST match E.164 — do not fall back to
  // US digit-count which would accept things like '+0123456789'.
  if (trimmed.startsWith("+")) {
    return /^\+[1-9]\d{7,14}$/.test(trimmed);
  }
  // US: strip non-digits; require exactly 10 digits, OR 11 with leading 1.
  const digitsOnly = trimmed.replace(/\D/g, "");
  if (digitsOnly.length === 10) return true;
  if (digitsOnly.length === 11 && digitsOnly.startsWith("1")) return true;
  return false;
}

// ---------------------------------------------------------------------------
// Volunteer avatar (initials circle like SignUpGenius)
// ---------------------------------------------------------------------------

// Avatar palette uses -700 shades so white text on each background clears the
// WCAG AA 4.5:1 contrast bar (PART-10). The -500/-400 shades that were here
// previously failed contrast (pink-500=3.58, orange-500=2.88, red-400=2.92, etc.)
const AVATAR_COLORS = [
  "bg-blue-700", "bg-green-700", "bg-purple-700", "bg-orange-700",
  "bg-pink-700", "bg-teal-700", "bg-indigo-700", "bg-red-700",
  "bg-cyan-700", "bg-amber-700",
];

function getAvatarColor(name) {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

function VolunteerChip({ firstName, lastInitial }) {
  const initials = `${firstName[0] || ""}${lastInitial}`.toUpperCase();
  const displayName = `${firstName} ${lastInitial}.`;
  const color = getAvatarColor(displayName);
  return (
    <span className="inline-flex items-center gap-1.5 text-xs mr-2 mb-1">
      <span className={`${color} text-white rounded-full w-6 h-6 flex items-center justify-center text-[10px] font-bold shrink-0`}>
        {initials}
      </span>
      <span className="text-[var(--color-fg-muted)]">{displayName}</span>
    </span>
  );
}

// ---------------------------------------------------------------------------
// Slot availability + display helpers
// ---------------------------------------------------------------------------

// Availability is signaled by BOTH text and color (never color alone) so it
// stays readable for color-blind volunteers (WCAG 1.4.1).
function slotStatus(slot) {
  // 2026-08-06 K10: "already happened" outranks every other state — a full
  // session that is also over should not offer a waitlist, because there is
  // nothing left to be waiting for. The server refuses these outright, so
  // anything the page still offers here would be a button that cannot work.
  if (slot.has_ended) return "ended";
  const capacity = slot.capacity ?? 0;
  const filled = slot.filled ?? 0;
  if (filled >= capacity) return "full";
  if (capacity > 0 && capacity - filled <= 3) return "few";
  return "open";
}

// 2026-08-02 shifts: orientation slots still number themselves (there is
// nothing else to call them), but the work is booked as shifts, which carry an
// organizer-given name. The old `Period N` label was derived in this file and
// had no database backing, so two views could disagree about which period was
// which — nothing derives a label any more.
function slotDisplayLabel(slot) {
  if (!slot) return "";
  if (slot._shiftName) return slot._shiftName;
  return `Orientation ${slot._periodLabel || ""}`.trim();
}

// A shift is all-or-nothing, so its availability is one number, not per session.
// It ends with its LAST session, not its first: a Tue+Wed shift still has
// Wednesday's classroom to staff on Tuesday evening. The server decides that —
// this only passes the flag through.
function shiftStatus(shift) {
  return slotStatus({
    capacity: shift.capacity,
    filled: shift.filled,
    has_ended: shift.has_ended,
  });
}

function sessionsInOrder(shift) {
  return [...(shift.sessions || [])].sort(
    (a, b) =>
      (a.sort_order ?? 0) - (b.sort_order ?? 0) ||
      String(a.start_time).localeCompare(String(b.start_time)),
  );
}

function AvailabilityBadge({ status, selected }) {
  if (selected) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50 px-2 py-0.5 text-xs font-semibold text-sky-800">
        <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
        You selected this
      </span>
    );
  }
  if (status === "ended") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
        Already happened
      </span>
    );
  }
  if (status === "full") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">
        <XCircle className="h-3.5 w-3.5" aria-hidden="true" />
        Full
      </span>
    );
  }
  if (status === "few") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-800">
        <AlertCircle className="h-3.5 w-3.5" aria-hidden="true" />
        Few spots left
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-800">
      <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
      Available
    </span>
  );
}

// ---------------------------------------------------------------------------
// Slot card — the ONE slot rendering used at every breakpoint.
// Must keep: div.rounded-xl container, p.font-medium label, "Sign up" button
// (e2e slotLabel + clickSlotByLabel contract).
// ---------------------------------------------------------------------------

function SlotCard({ slot, selected, onToggle, highlight, showDate }) {
  const isFull = slot.filled >= slot.capacity;
  const status = slotStatus(slot);
  const hasEnded = status === "ended";
  const fillPct =
    slot.capacity > 0 ? Math.min(100, Math.round((slot.filled / slot.capacity) * 100)) : 0;

  return (
    <div
      className={[
        "rounded-xl border bg-white p-4 shadow-sm transition-colors",
        selected
          ? "border-[var(--color-brand)] ring-2 ring-sky-200 bg-sky-50/40"
          : highlight && !isFull
            ? "border-sky-400 ring-2 ring-sky-200"
            : "border-[var(--color-border)] hover:border-sky-300",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-medium text-[var(--color-fg)]">
              {slot.slot_type === "orientation"
                ? <>Orientation {slot._periodLabel}</>
                : <>Period {slot._periodLabel}</>}
            </p>
            <AvailabilityBadge status={status} selected={selected} />
          </div>

          <div className="mt-1.5 flex flex-col gap-0.5 text-sm text-[var(--color-fg-muted)]">
            {showDate && (
              <span className="inline-flex items-center gap-1.5">
                <CalendarDays className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
                {formatShortDate(slot.date)} · {formatWeekday(slot.date)}
              </span>
            )}
            <span className="inline-flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
              {formatTime(slot.start_time)} – {formatTime(slot.end_time)}
            </span>
            {slot.location && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
                {slot.location}
              </span>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={() => onToggle(slot.id)}
          disabled={hasEnded}
          className={[
            "shrink-0 min-h-11 min-w-[6.5rem] px-4 rounded-lg text-sm font-semibold transition-all shadow-sm",
            hasEnded
              ? "cursor-not-allowed bg-slate-100 text-slate-500 border border-slate-200"
              : "hover:shadow-md hover:-translate-y-0.5 active:translate-y-0",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2",
            hasEnded
              ? ""
              : isFull
                ? selected
                  ? "bg-amber-500 text-white"
                  : "bg-amber-600 text-white hover:bg-amber-700"
                : selected
                  ? "bg-[var(--color-success)] text-white"
                  : "bg-[var(--color-brand)] text-white hover:brightness-110",
          ].join(" ")}
        >
          {hasEnded
            ? "Ended"
            : isFull
              ? selected ? "On waitlist" : "Join waitlist"
              : selected ? "Selected" : "Sign up"}
        </button>
      </div>

      {/* Capacity: text first (never color alone), thin progress bar as reinforcement */}
      {slot.capacity > 0 && (
        <div className="mt-3">
          <p className="text-xs text-[var(--color-fg-muted)]">
            {slot.filled} of {slot.capacity} filled
          </p>
          <div className="mt-1 h-1.5 w-full max-w-xs rounded-full bg-slate-100" aria-hidden="true">
            <div
              className={[
                "h-full rounded-full transition-all",
                status === "full" || status === "ended"
                  ? "bg-slate-400"
                  : status === "few"
                    ? "bg-amber-500"
                    : "bg-[var(--color-brand)]",
              ].join(" ")}
              style={{ width: `${fillPct}%` }}
            />
          </div>
        </div>
      )}

      {slot.signups?.length > 0 && (
        <div className="flex flex-wrap mt-3 pt-3 border-t border-[var(--color-border)]">
          {slot.signups.map((s, i) => (
            <VolunteerChip key={i} firstName={s.first_name} lastInitial={s.last_initial} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shift card — the bookable unit for the classroom work, at every breakpoint.
//
// Deliberately a card and not a table row: a shift holds several sessions, and
// one row per shift cannot show them without either hiding the detail the
// volunteer needs to check their own availability or nesting a table. Same
// label/button structure as SlotCard so the e2e helpers keep working.
// ---------------------------------------------------------------------------

function ShiftCard({ shift, selected, onToggle }) {
  const isFull = (shift.filled ?? 0) >= (shift.capacity ?? 0);
  const status = shiftStatus(shift);
  const hasEnded = status === "ended";
  const sessions = sessionsInOrder(shift);
  const fillPct =
    shift.capacity > 0
      ? Math.min(100, Math.round(((shift.filled ?? 0) / shift.capacity) * 100))
      : 0;

  return (
    <div
      data-testid={`shift-${shift.id}`}
      className={[
        "rounded-xl border bg-white p-4 shadow-sm transition-colors",
        selected
          ? "border-[var(--color-brand)] ring-2 ring-sky-200 bg-sky-50/40"
          : "border-[var(--color-border)] hover:border-sky-300",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-base font-medium text-[var(--color-fg)]">{shift.name}</p>
            <AvailabilityBadge status={status} selected={selected} />
          </div>
          <p className="mt-1 text-xs text-[var(--color-fg-muted)]">
            {sessions.length === 1
              ? "1 session — signing up commits you to it."
              : `${sessions.length} sessions — signing up commits you to all of them.`}
          </p>
        </div>

        <button
          type="button"
          onClick={() => onToggle(shift.id)}
          disabled={hasEnded}
          className={[
            "shrink-0 min-h-11 min-w-[6.5rem] px-4 rounded-lg text-sm font-semibold transition-all shadow-sm",
            hasEnded
              ? "cursor-not-allowed bg-slate-100 text-slate-500 border border-slate-200"
              : "hover:shadow-md hover:-translate-y-0.5 active:translate-y-0",
            "focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2",
            hasEnded
              ? ""
              : isFull
                ? selected
                  ? "bg-amber-500 text-white"
                  : "bg-amber-600 text-white hover:bg-amber-700"
                : selected
                  ? "bg-[var(--color-success)] text-white"
                  : "bg-[var(--color-brand)] text-white hover:brightness-110",
          ].join(" ")}
        >
          {hasEnded
            ? "Ended"
            : isFull
              ? selected ? "On waitlist" : "Join waitlist"
              : selected ? "Selected" : "Sign up"}
        </button>
      </div>

      <ul className="mt-3 flex flex-col gap-1.5 border-t border-[var(--color-border)] pt-3">
        {sessions.map((s) => (
          <li
            key={s.id}
            className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-[var(--color-fg-muted)]"
          >
            {s.name && (
              <span className="font-medium text-[var(--color-fg)]">{s.name}</span>
            )}
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
              {formatShortDate(s.date)} · {formatWeekday(s.date)}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
              {formatTime(s.start_time)} – {formatTime(s.end_time)}
            </span>
            {s.location && (
              <span className="inline-flex items-center gap-1.5">
                <MapPin className="h-3.5 w-3.5 shrink-0 text-slate-400" aria-hidden="true" />
                {s.location}
              </span>
            )}
          </li>
        ))}
      </ul>

      {/* Text first, bar as reinforcement — never colour alone (WCAG 1.4.1). */}
      {shift.capacity > 0 && (
        <div className="mt-3">
          <p className="text-xs text-[var(--color-fg-muted)]">
            {shift.filled ?? 0} of {shift.capacity} filled
          </p>
          <div className="mt-1 h-1.5 w-full max-w-xs rounded-full bg-slate-100" aria-hidden="true">
            <div
              className={[
                "h-full rounded-full transition-all",
                status === "full" || status === "ended"
                  ? "bg-slate-400"
                  : status === "few"
                    ? "bg-amber-500"
                    : "bg-[var(--color-brand)]",
              ].join(" ")}
              style={{ width: `${fillPct}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Slot table — the desktop (md+) rendering for orientation. Label cells are
// div.font-medium (e2e contract). Each row has an in-row "Sign up" button and
// an optional expandable "who signed up" drawer.
// ---------------------------------------------------------------------------

function SignUpButton({ slot, selected, onToggle }) {
  const isFull = slot.filled >= slot.capacity;
  const hasEnded = slotStatus(slot) === "ended";
  return (
    <button
      type="button"
      onClick={() => onToggle(slot.id)}
      disabled={hasEnded}
      className={[
        "min-h-10 min-w-[6rem] rounded-lg px-4 text-sm font-semibold shadow-sm transition-all",
        hasEnded
          ? "cursor-not-allowed border border-slate-200 bg-slate-100 text-slate-500"
          : "hover:shadow-md hover:-translate-y-0.5 active:translate-y-0",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600 focus-visible:ring-offset-2",
        hasEnded
          ? ""
          : isFull
            ? selected
              ? "bg-amber-500 text-white"
              : "bg-amber-600 text-white hover:bg-amber-700"
            : selected
              ? "bg-[var(--color-success)] text-white"
              : "bg-[var(--color-brand)] text-white hover:brightness-110",
      ].join(" ")}
    >
      {hasEnded
        ? "Ended"
        : isFull
          ? selected ? "On waitlist" : "Join waitlist"
          : selected ? "Selected" : "Sign up"}
    </button>
  );
}

function CapacityCell({ slot }) {
  const status = slotStatus(slot);
  const fillPct =
    slot.capacity > 0 ? Math.min(100, Math.round((slot.filled / slot.capacity) * 100)) : 0;
  return (
    <div className="flex flex-col gap-1">
      <AvailabilityBadge status={status} selected={false} />
      {slot.capacity > 0 && (
        <>
          <span className="text-xs text-[var(--color-fg-muted)]">
            {slot.filled} of {slot.capacity} filled
          </span>
          <div className="h-1.5 w-24 rounded-full bg-slate-100" aria-hidden="true">
            <div
              className={[
                "h-full rounded-full transition-all",
                status === "full" || status === "ended"
                  ? "bg-slate-400"
                  : status === "few"
                    ? "bg-amber-500"
                    : "bg-[var(--color-brand)]",
              ].join(" ")}
              style={{ width: `${fillPct}%` }}
            />
          </div>
        </>
      )}
    </div>
  );
}

function SlotTable({
  slots,
  kind,
  showDate,
  selectedSlotIds,
  onToggle,
  expandedIds,
  onToggleExpand,
  highlight,
}) {
  const colCount = 2 + (showDate ? 1 : 0) + 3; // label, [date], time, loc, spots, signup
  return (
    <div className="hidden overflow-hidden rounded-xl border border-[var(--color-border)] shadow-sm md:block">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--color-border)] bg-slate-50 text-left text-xs font-semibold uppercase tracking-wide text-[var(--color-fg-muted)]">
            <th scope="col" className="px-4 py-3">
              {kind === "orientation" ? "Session" : "Period"}
            </th>
            {showDate && <th scope="col" className="px-4 py-3">Date</th>}
            <th scope="col" className="px-4 py-3">Time</th>
            <th scope="col" className="px-4 py-3">Location</th>
            <th scope="col" className="px-4 py-3">Availability</th>
            <th scope="col" className="px-4 py-3 text-right">Sign up</th>
          </tr>
        </thead>
        <tbody>
          {slots.map((slot) => {
            const selected = selectedSlotIds.has(slot.id);
            const isFull = slot.filled >= slot.capacity;
            const expanded = expandedIds.has(slot.id);
            const signupCount = slot.signups?.length || 0;
            return (
              <React.Fragment key={slot.id}>
                <tr
                  className={[
                    "border-b border-[var(--color-border)] transition-colors last:border-b-0",
                    selected
                      ? "bg-sky-50/60"
                      : highlight && !isFull
                        ? "bg-sky-50/40"
                        : "hover:bg-slate-50",
                  ].join(" ")}
                >
                  <td className="px-4 py-3 align-top">
                    <div className="font-medium text-[var(--color-fg)]">
                      {kind === "orientation"
                        ? `Orientation ${slot._periodLabel || ""}`.trim()
                        : `Period ${slot._periodLabel || ""}`.trim()}
                    </div>
                    {signupCount > 0 && (
                      <button
                        type="button"
                        onClick={() => onToggleExpand(slot.id)}
                        aria-expanded={expanded}
                        className="mt-1 inline-flex items-center gap-1 text-xs text-[var(--color-brand)] hover:underline"
                      >
                        <Users className="h-3 w-3" aria-hidden="true" />
                        {signupCount} signed up
                        <ChevronDown
                          className={`h-3 w-3 transition-transform ${expanded ? "rotate-180" : ""}`}
                          aria-hidden="true"
                        />
                      </button>
                    )}
                  </td>
                  {showDate && (
                    <td className="px-4 py-3 align-top text-[var(--color-fg-muted)]">
                      {formatShortDate(slot.date)}
                      <span className="block text-xs">{formatWeekday(slot.date)}</span>
                    </td>
                  )}
                  <td className="whitespace-nowrap px-4 py-3 align-top text-[var(--color-fg-muted)]">
                    {formatTime(slot.start_time)} – {formatTime(slot.end_time)}
                  </td>
                  <td className="px-4 py-3 align-top text-[var(--color-fg-muted)]">
                    {slot.location || "—"}
                  </td>
                  <td className="px-4 py-3 align-top">
                    <CapacityCell slot={slot} />
                  </td>
                  <td className="px-4 py-3 text-right align-top">
                    <SignUpButton slot={slot} selected={selected} onToggle={onToggle} />
                  </td>
                </tr>
                {expanded && signupCount > 0 && (
                  <tr className="border-b border-[var(--color-border)] bg-slate-50/60 last:border-b-0">
                    <td colSpan={colCount} className="px-4 py-3">
                      <div className="flex flex-wrap">
                        {slot.signups.map((s, i) => (
                          <VolunteerChip
                            key={i}
                            firstName={s.first_name}
                            lastInitial={s.last_initial}
                          />
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Auto-generated event description (mirrors SignUpGenius format)
// ---------------------------------------------------------------------------

function formatFullDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString.includes("T") ? isoString : `${isoString}T00:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

function formatModuleName(slug) {
  if (!slug) return "";
  return slug
    .replace(/-/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function capitalizeQuarter(q) {
  if (!q) return "";
  return q.charAt(0).toUpperCase() + q.slice(1);
}

function EventDescription({ event, orientationSlots }) {
  const moduleName = formatModuleName(event.module_slug);
  const quarter = capitalizeQuarter(event.quarter);
  const hasCustomDescription = !!(event.description && event.description.trim());

  return (
    <Card className="text-sm text-[var(--color-fg)] leading-relaxed !border-sky-100 shadow-sm">
      <h2 className="mb-3 flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-sky-800">
        <span
          aria-hidden="true"
          className="inline-flex h-6 w-6 items-center justify-center rounded-full bg-sky-100 text-sky-700"
        >
          <Mail className="h-3.5 w-3.5" />
        </span>
        About this event
      </h2>
      {hasCustomDescription ? (
        <p className="whitespace-pre-wrap">{event.description}</p>
      ) : (
        <p>
          SciTrek will be conducting the {moduleName || event.title} Module
          {event.school ? ` at ${event.school}` : ""}
          {event.week_number ? ` for Week ${event.week_number} of ${quarter} quarter` : ""}.
        </p>
      )}

      {orientationSlots.length > 0 && (
        <>
          {!hasCustomDescription && (
            <>
              <p className="mt-3 font-semibold">NOTE:</p>
              <p>
                You must attend one Orientation. Attending an Orientation before mentoring
                in the classroom is required. Previously attended orientations and/or
                training workshops that covered {moduleName || "this module"} fulfill this requirement.
              </p>
            </>
          )}
          <p className="mt-2">Available orientation slots:</p>
          <ul className="mt-1 ml-4 list-disc">
            {orientationSlots.map((slot, i) => (
              <li key={slot.id}>
                Orientation {orientationSlots.length > 1 ? `${i + 1} - ` : "- "}
                {formatFullDate(slot.date)} from {formatTime(slot.start_time)} - {formatTime(slot.end_time)}
                {slot.location ? ` in ${slot.location}` : ""}
              </li>
            ))}
          </ul>
        </>
      )}

      {!hasCustomDescription && (
        <>
          <p className="mt-3">
            All shifts meet at the SciTrek office in room Chem 1204 and travel by van to the school.
            We begin boarding vans at the exact start time of your shift. Please be on time
            (we are not able to accommodate late arrivals).
          </p>

          <p className="mt-3">We look forward to working with you!</p>

          <p className="mt-3">
            Please contact the SciTrek Manager at{" "}
            <a href="mailto:chem-scitrekmanager@ucsb.edu" className="text-[var(--color-brand)] underline">
              chem-scitrekmanager@ucsb.edu
            </a>{" "}
            if you have any questions. If you sign up for a shift but cannot make it,
            please notify us as soon as possible.
          </p>
        </>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div
      className="flex flex-col gap-4 py-4"
      role="status"
      aria-busy="true"
      aria-live="polite"
      aria-label="Loading event details"
    >
      <Skeleton className="h-16 rounded-xl" />
      <Skeleton className="h-32 rounded-xl" />
      <Skeleton className="h-64 rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EventDetailPage() {
  const { eventId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // State machine
  const [step, setStep] = useState("browse");
  const [selectedSlotIds, setSelectedSlotIds] = useState(new Set());
  // Kept separate from the orientation slot ids: they are different kinds of
  // booking with different endpoints, and a single set would need a lookup on
  // every read just to tell which it was holding.
  const [selectedShiftIds, setSelectedShiftIds] = useState(new Set());
  const [identity, setIdentity] = useState({
    first_name: "",
    last_name: "",
    email: "",
    phone: "",
  });
  const [formErrors, setFormErrors] = useState({});
  const [submitError, setSubmitError] = useState(null);
  const [successData, setSuccessData] = useState(null);
  const [highlightOrientation, setHighlightOrientation] = useState(false);
  // Desktop table: which slots have their "who's signed up" drawer open.
  const [expandedIds, setExpandedIds] = useState(new Set());

  function toggleExpand(id) {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  // Anchor for the mobile "Continue" bar → scrolls to the identity form.
  const formRef = useRef(null);
  function scrollToForm() {
    formRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }

  // Data fetching
  const eventQ = useQuery({
    queryKey: ["publicEvent", eventId],
    queryFn: () => api.public.getEvent(eventId),
    enabled: !!eventId,
  });

  // Phase 22 — effective custom form schema
  const formSchemaQ = useQuery({
    queryKey: ["publicEventFormSchema", eventId],
    queryFn: () => api.public.getFormSchema(eventId),
    enabled: !!eventId,
  });
  const formSchema = formSchemaQ.data?.schema || [];
  const [responses, setResponses] = useState({}); // { field_id: value }

  // `event.slots` is orientation-only now; the classroom work arrives as
  // `event.shifts`, each already carrying its sessions in organizer order.
  const { slotMap, labeledSlotMap, orientationSlots, shifts, shiftMap } = useMemo(() => {
    const slots = eventQ.data?.slots || [];
    const map = Object.fromEntries(slots.map((s) => [s.id, s]));

    const orientations = slots.filter((s) => s.slot_type === "orientation");
    const labeledOrientations = orientations.map((s, i) => ({
      ...s,
      _periodLabel: orientations.length > 1 ? `#${i + 1}` : "",
    }));

    const orderedShifts = [...(eventQ.data?.shifts || [])].sort(
      (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0),
    );

    // Labeled lookup for the selection summary (raw map lacks _periodLabel).
    const labeledMap = { ...map };
    for (const s of labeledOrientations) labeledMap[s.id] = s;

    return {
      slotMap: map,
      labeledSlotMap: labeledMap,
      orientationSlots: labeledOrientations,
      shifts: orderedShifts,
      shiftMap: Object.fromEntries(orderedShifts.map((s) => [s.id, s])),
    };
  }, [eventQ.data]);

  // Slot toggle
  function toggleSlot(id) {
    setSelectedSlotIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setStep((prev) => (prev === "browse" ? "form" : prev));
    setHighlightOrientation(false);
  }

  // Shifts are toggled whole — the commitment covers every session in one.
  function toggleShift(id) {
    setSelectedShiftIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setStep((prev) => (prev === "browse" ? "form" : prev));
    setHighlightOrientation(false);
  }

  // Identity field change
  function handleIdentityChange(field, value) {
    setIdentity((prev) => ({ ...prev, [field]: value }));
    if (formErrors[field]) {
      setFormErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  // Client-side validation (UI-SPEC §Form validation copy)
  // Phone accepts BOTH US-formatted (10 digits, optional leading 1) and
  // E.164 (+[country][number], total 8-15 digits). Server (D-14) remains
  // authoritative; this only improves UX before the round-trip. PART-05.
  function validateIdentity() {
    const errors = {};
    const fullName = `${identity.first_name} ${identity.last_name}`.trim();
    if (!identity.first_name.trim() || !identity.last_name.trim()) {
      const msg = "Enter your full name";
      if (!identity.first_name.trim()) errors.first_name = msg;
      if (!identity.last_name.trim()) errors.last_name = msg;
    }
    if (!identity.email.trim()) {
      errors.email = "Enter your email address";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identity.email)) {
      errors.email = "That doesn't look like a valid email";
    }
    if (!identity.phone.trim()) {
      errors.phone = "Enter your phone number";
    } else if (!isValidPhone(identity.phone)) {
      errors.phone = "Use a US format: (805) 555-1234 or +18055551234";
    }
    // Phase 22 — validate required custom fields. Server accepts missing
    // (organizer override), but we block client-side unless the volunteer
    // explicitly confirms skip. For v1.3 we just block at submit: organizer
    // can still add the volunteer later.
    for (const f of formSchema) {
      if (!f.required) continue;
      const v = responses[f.id];
      const isBlank =
        v === undefined ||
        v === null ||
        (typeof v === "string" && !v.trim()) ||
        (Array.isArray(v) && v.length === 0);
      if (isBlank) {
        errors[`custom_${f.id}`] = `Please answer: ${f.label}`;
      }
    }
    // Touch fullName so the helper isn't dead code if a future linter trims it.
    void fullName;
    return errors;
  }

  // Phase 22 — dynamic form renderer
  function renderFormField(field) {
    const fieldErrKey = `custom_${field.id}`;
    const value = responses[field.id];
    function setValue(v) {
      setResponses((prev) => ({ ...prev, [field.id]: v }));
      if (formErrors[fieldErrKey]) {
        setFormErrors((prev) => {
          const n = { ...prev };
          delete n[fieldErrKey];
          return n;
        });
      }
    }
    const fid = `ff-${field.id}`;
    let input;
    switch (field.type) {
      case "textarea":
        input = (
          <textarea
            id={fid}
            value={value || ""}
            onChange={(e) => setValue(e.target.value)}
            className="w-full min-h-16 rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-sm"
          />
        );
        break;
      case "select":
        input = (
          <select
            id={fid}
            value={value || ""}
            onChange={(e) => setValue(e.target.value)}
            className="min-h-11 w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] px-3 text-base"
          >
            <option value="">— select —</option>
            {(field.options || []).map((o) => (
              <option key={o} value={o}>
                {o}
              </option>
            ))}
          </select>
        );
        break;
      case "radio":
        input = (
          <div className="space-y-1" role="radiogroup" aria-labelledby={`${fid}-label`}>
            {(field.options || []).map((o) => (
              <label key={o} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name={fid}
                  value={o}
                  checked={value === o}
                  onChange={() => setValue(o)}
                />
                {o}
              </label>
            ))}
          </div>
        );
        break;
      case "checkbox": {
        const selected = new Set(Array.isArray(value) ? value : []);
        input = (
          <div className="space-y-1">
            {(field.options || []).map((o) => (
              <label key={o} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={selected.has(o)}
                  onChange={(e) => {
                    const next = new Set(selected);
                    if (e.target.checked) next.add(o);
                    else next.delete(o);
                    setValue(Array.from(next));
                  }}
                />
                {o}
              </label>
            ))}
          </div>
        );
        break;
      }
      case "phone":
        input = (
          <Input
            id={fid}
            type="tel"
            value={value || ""}
            onChange={(e) => setValue(e.target.value)}
          />
        );
        break;
      case "email":
        input = (
          <Input
            id={fid}
            type="email"
            value={value || ""}
            onChange={(e) => setValue(e.target.value)}
          />
        );
        break;
      case "text":
      default:
        input = (
          <Input
            id={fid}
            type="text"
            value={value || ""}
            onChange={(e) => setValue(e.target.value)}
          />
        );
    }
    return (
      <div key={field.id}>
        <Label htmlFor={fid} id={`${fid}-label`}>
          {field.label}
          {field.required ? " *" : ""}
        </Label>
        {input}
        {field.help_text && (
          <p className="text-xs text-[var(--color-fg-muted)] mt-1">
            {field.help_text}
          </p>
        )}
        <FieldError>{formErrors[fieldErrKey]}</FieldError>
      </div>
    );
  }

  // Phase 22 — build the response array from state
  function buildResponsesArray() {
    return Object.entries(responses)
      .filter(([, v]) => v !== undefined && v !== null)
      .map(([field_id, value]) => ({ field_id, value }));
  }

  // Submit signup
  async function submitSignup() {
    setStep("submitting");
    // The success card and the calendar buttons want concrete sessions, so a
    // selected shift contributes each of its sessions, tagged with the shift
    // name they were booked under.
    const selectedSlots = [
      ...[...selectedSlotIds].map((id) => slotMap[id]).filter(Boolean),
      ...[...selectedShiftIds].flatMap((id) => {
        const shift = shiftMap[id];
        if (!shift) return [];
        return sessionsInOrder(shift).map((s) => ({
          ...s,
          slot_type: "period",
          _shiftName: shift.name,
          // The signup result for a shift is anchored on the shift, not on
          // each session, so the card needs the id to find its status.
          _shiftId: shift.id,
        }));
      }),
    ];
    try {
      const response = await api.public.createSignup({
        ...identity,
        slot_ids: [...selectedSlotIds],
        shift_ids: [...selectedShiftIds],
        responses: buildResponsesArray(),
      });
      // Phase 25 (WAIT-01): if any selected slot was at capacity the server
      // puts the signup on the waitlist instead of rejecting. Surface that
      // explicitly so the volunteer knows what happened.
      const waitlistedItems = (response.signups || []).filter(
        (s) => s.status === "waitlisted",
      );
      if (waitlistedItems.length > 0) {
        const minPosition = waitlistedItems.reduce(
          (acc, s) => (s.position != null && (acc == null || s.position < acc) ? s.position : acc),
          null,
        );
        const positionText = minPosition != null ? ` — position ${minPosition}` : "";
        toast.info
          ? toast.info(`You're on the waitlist${positionText}.`)
          : toast.success(`You're on the waitlist${positionText}.`);
      }
      setSuccessData({ ...response, slots: selectedSlots });
      setStep("success");
    } catch (err) {
      if (err.code === "ORIENTATION_REQUIRED") {
        // Server-enforced backstop: the volunteer needs an orientation
        // session in this signup. Same modal as the pre-submit check.
        // Refetch so the modal variant + schedule reflect current slots.
        queryClient.invalidateQueries({ queryKey: ["publicEvent", eventId] });
        setStep("orientation-warning");
      } else if (err.status === 429) {
        toast.error("Too many submissions. Please wait a moment and try again.");
        setStep("form");
      } else if (err.status === 422) {
        const detail = err.response?.data?.detail;
        if (Array.isArray(detail)) {
          const fieldErrs = {};
          detail.forEach((d) => {
            const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
            if (field) fieldErrs[field] = d.msg || "Invalid value";
          });
          if (Object.keys(fieldErrs).length > 0) setFormErrors(fieldErrs);
          else setSubmitError(err.message);
        } else {
          setSubmitError(err.message);
        }
        setStep("form");
      } else if (
        err.status === 409 &&
        err.message?.toLowerCase().includes("already signed up")
      ) {
        // Duplicate signup (same email + slot) — not a capacity problem.
        toast.error(
          "You've already signed up for this session with that email — check your inbox for the confirmation link."
        );
        setStep("form");
      } else if (
        err.message?.toLowerCase().includes("capacity") ||
        err.message?.toLowerCase().includes("full") ||
        err.status === 409
      ) {
        toast.error("One or more selected slots are now full. Please pick different slots.");
        setStep("browse");
        queryClient.invalidateQueries({ queryKey: ["publicEvent", eventId] });
      } else {
        toast.error(err.message || "Something went wrong. Please try again.");
        setStep("form");
      }
    }
  }

  // Handle form submit
  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitError(null);

    const errors = validateIdentity();
    if (Object.keys(errors).length > 0) {
      setFormErrors(errors);
      return;
    }

    // The gate is now "committing to a shift without an orientation", which is
    // exactly what the backend enforces (orientation_gate retargeted from
    // period slots to shifts).
    const hasShift = selectedShiftIds.size > 0;
    const hasOrientation = [...selectedSlotIds].some(
      (id) => slotMap[id]?.slot_type === "orientation"
    );

    if (hasShift && !hasOrientation) {
      setStep("checking-orientation");
      try {
        // Phase 21: credit check is cross-week / cross-module within the same
        // module family. Pass eventId so the backend can resolve the family.
        const result = await api.public.orientationCheck(
          identity.email,
          eventId,
        );
        // `has_credit` is the new field; fall back to `has_attended_orientation`
        // so the check still works if we ever point at the legacy endpoint.
        const hasCredit = result?.has_credit ?? result?.has_attended_orientation;
        if (!hasCredit) {
          // The modal's required/advisory variant derives from event.slots —
          // refetch so it can't disagree with what the server will enforce
          // (organizer may have added/removed orientation slots mid-visit).
          queryClient.invalidateQueries({ queryKey: ["publicEvent", eventId] });
          setStep("orientation-warning");
          return;
        }
      } catch {
        // On API error, proceed and let the server decide — signup create
        // enforces the orientation requirement (422 ORIENTATION_REQUIRED)
        // and submitSignup maps that back to the modal.
      }
    }

    await submitSignup();
  }

  // Reset
  function handleDismissSuccess() {
    setStep("browse");
    setSelectedSlotIds(new Set());
    setSelectedShiftIds(new Set());
    setIdentity({ first_name: "", last_name: "", email: "", phone: "" });
    setFormErrors({});
    setSubmitError(null);
    setSuccessData(null);
    setHighlightOrientation(false);
    setResponses({});
  }

  function handleOrientationYes() {
    submitSignup();
  }

  function handleOrientationNo() {
    // Fresh schedule for picking an orientation session.
    queryClient.invalidateQueries({ queryKey: ["publicEvent", eventId] });
    setStep("browse");
    setHighlightOrientation(true);
  }

  // K22: the advisory variant of the modal only renders when this event has
  // *no* orientation slots, so highlighting them here highlighted nothing —
  // "show me orientation events" dropped the volunteer back on the same page
  // unchanged. Send them somewhere that can actually answer.
  function handleFindOrientationElsewhere() {
    setStep("browse");
    navigate("/volunteer?only=orientation");
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (eventQ.isPending) return <DetailSkeleton />;

  if (eventQ.isError) {
    return (
      <ErrorState
        title="We couldn't load this page"
        body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
        action={
          <Button variant="secondary" onClick={() => eventQ.refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  const event = eventQ.data;
  const slots = event?.slots || [];
  const selectionCount = selectedSlotIds.size + selectedShiftIds.size;
  const showForm =
    selectionCount > 0 && (step === "form" || step === "checking-orientation");
  const isSubmitting = step === "submitting" || step === "checking-orientation";

  // Phase 29 (LOCK-01) — compute signup-window state for banner + submit gate.
  const now = new Date();
  const opensAt = event?.signup_open_at ? new Date(event.signup_open_at) : null;
  const closesAt = event?.signup_close_at ? new Date(event.signup_close_at) : null;
  const beforeWindow = !!(opensAt && now < opensAt);
  const afterWindow = !!(closesAt && now > closesAt);
  const outsideWindow = beforeWindow || afterWindow;
  const windowBannerText = beforeWindow
    ? `Signup opens ${opensAt?.toLocaleString("en-US", { timeZone: "America/Los_Angeles", dateStyle: "medium", timeStyle: "short" })} PT`
    : afterWindow
      ? `Signup closed ${closesAt?.toLocaleString("en-US", { timeZone: "America/Los_Angeles", dateStyle: "medium", timeStyle: "short" })} PT`
      : null;

  const selectedSlots = [...selectedSlotIds]
    .map((id) => labeledSlotMap[id])
    .filter(Boolean);
  const selectedShifts = [...selectedShiftIds].map((id) => shiftMap[id]).filter(Boolean);

  // What "Add to calendar" should export, in order of preference: whatever the
  // volunteer has ticked, else the first orientation with room left, else the
  // first slot on the page. Shared by both calendar buttons so they can never
  // disagree about which session they added.
  function calendarSlots() {
    const chosen = [
      ...selectedSlots,
      ...selectedShifts.flatMap((sh) =>
        sessionsInOrder(sh).map((se) => ({ ...se, _shiftName: sh.name })),
      ),
    ];
    if (chosen.length > 0) return chosen;
    const openOrientation = orientationSlots.find(
      (s) => (s.filled ?? 0) < (s.capacity ?? 0),
    );
    const firstSession = shifts.length > 0 ? sessionsInOrder(shifts[0])[0] : null;
    const fallback = openOrientation || slots[0] || firstSession;
    return fallback ? [fallback] : [];
  }

  return (
    <div
      className="flex flex-col gap-5 pt-4 pb-8 max-w-5xl mx-auto w-full animate-fade-up"
    >
      {/* Selection announcer for screen readers */}
      <p aria-live="polite" className="sr-only">
        {selectionCount === 1 ? "1 selected" : `${selectionCount} selected`}
      </p>

      {/* Back link */}
      <div>
        <Link
          to="/volunteer"
          className="inline-flex min-h-11 items-center gap-1 text-sm text-[var(--color-brand)] hover:underline"
        >
          &larr; Back to events
        </Link>
      </div>

      {/* Event header — hero card (SciTrek blue field + orange accent) */}
      <section className="relative overflow-hidden rounded-2xl md:rounded-3xl bg-gradient-to-br from-sky-600 via-sky-700 to-sky-900 text-white p-6 sm:p-8 md:p-10">
        <div
          aria-hidden="true"
          className="absolute -top-16 -right-16 h-64 w-64 rounded-full bg-sky-300/25 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-20 -left-10 h-72 w-72 rounded-full bg-orange-400/15 blur-3xl"
        />
        <div className="relative z-10">
          <span aria-hidden="true" className="block h-1 w-12 rounded-full bg-orange-400" />
          {event.school && (
            <p className="mt-4 text-xs sm:text-sm font-semibold uppercase tracking-widest text-sky-200">
              {event.school}
            </p>
          )}
          <h1 className="mt-2 text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight leading-tight">
            {event.title}
          </h1>
          <div className="mt-4 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-sm text-sky-100">
            <span className="inline-flex items-center gap-1.5">
              <CalendarDays className="h-4 w-4 shrink-0 text-sky-300" aria-hidden="true" />
              {formatDateRange(event.start_date, event.end_date)}
            </span>
            <span className="inline-flex items-center gap-1.5 text-sky-200/90">
              <Clock className="h-4 w-4 shrink-0 text-sky-300" aria-hidden="true" />
              Times shown in Pacific Time.
            </span>
          </div>
        </div>
      </section>

      {/* Phase 29 (LOCK-01) — signup window banner */}
      {outsideWindow && (
        <div
          role="status"
          className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
          data-testid="signup-window-banner"
        >
          {windowBannerText}
        </div>
      )}

      {/* Event description (auto-generated + any custom admin text) */}
      <EventDescription event={event} orientationSlots={orientationSlots} />

      {/* Already-signed-up hint. Manage page requires a token from the
          confirmation email, so a bare link would error — we explain instead. */}
      <div className="inline-flex items-center gap-2 self-start rounded-full bg-[var(--color-brand-soft)] px-4 py-2 text-sm text-[var(--color-brand)]">
        <span aria-hidden="true">✉️</span>
        Already signed up? Use the <span className="font-semibold">Manage my signups</span> link in your confirmation email.
      </div>

      {/* Add to calendar (PART-13 surface A) — secondary CTA below event metadata,
          above the slot list. Only renders when there is at least one slot to add. */}
      {(slots.length > 0 || shifts.length > 0) && (
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              const [first] = calendarSlots();
              if (!first) return;
              const url = buildGoogleCalendarUrl({
                event,
                slot: first,
                origin: window.location.origin,
              });
              window.open(url, "_blank", "noopener,noreferrer");
            }}
          >
            Add to Google Calendar
          </Button>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              // The .ics can hold every session at once, so when several slots
              // are ticked the download covers all of them rather than
              // silently exporting only the first.
              const chosen = calendarSlots();
              if (chosen.length === 0) return;
              downloadIcs({ event, slots: chosen });
              toast.success(
                chosen.length > 1
                  ? `Calendar file saved with ${chosen.length} sessions. Open it to add them.`
                  : "Calendar file saved. Open it to add to your calendar."
              );
            }}
          >
            Download .ics
          </Button>
        </div>
      )}

      {/* Booking sections: orientation slots, then shifts */}
      {slots.length === 0 && shifts.length === 0 ? (
        <EmptyState
          title="Every slot is full"
          body="This event is fully booked. Try another event from this week's list."
          action={
            <Button variant="secondary" onClick={() => navigate("/volunteer")}>
              Back to events
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-6">
          {orientationSlots.length > 0 && (
            <section aria-labelledby="orientation-heading">
              <div className="mb-3 border-l-4 border-[var(--color-brand)] pl-3">
                <h2
                  id="orientation-heading"
                  className="text-sm font-semibold uppercase tracking-wide text-[var(--color-fg)]"
                >
                  Orientation
                </h2>
                <p className="text-sm text-[var(--color-fg-muted)]">
                  Attend one before mentoring in the classroom — pick a session below.
                </p>
              </div>

              {/* Desktop: one Orientation table */}
              <SlotTable
                slots={orientationSlots}
                kind="orientation"
                showDate
                selectedSlotIds={selectedSlotIds}
                onToggle={toggleSlot}
                expandedIds={expandedIds}
                onToggleExpand={toggleExpand}
                highlight={highlightOrientation}
              />

              {/* Mobile: stacked cards */}
              <div className="grid gap-3 sm:grid-cols-2 md:hidden">
                {orientationSlots.map((slot) => (
                  <SlotCard
                    key={slot.id}
                    slot={slot}
                    selected={selectedSlotIds.has(slot.id)}
                    onToggle={toggleSlot}
                    highlight={highlightOrientation}
                    showDate
                  />
                ))}
              </div>
            </section>
          )}

          {shifts.length > 0 && (
            <section aria-labelledby="modules-heading">
              <div className="mb-3 border-l-4 border-[var(--color-accent)] pl-3">
                <h2
                  id="modules-heading"
                  className="text-sm font-semibold uppercase tracking-wide text-[var(--color-fg)]"
                >
                  Shifts
                </h2>
                <p className="text-sm text-[var(--color-fg-muted)]">
                  Pick the shifts you can mentor. Each shift is all-or-nothing —
                  signing up commits you to every session listed inside it.
                </p>
              </div>

              <div className="flex flex-col gap-3">
                {shifts.map((shift) => (
                  <ShiftCard
                    key={shift.id}
                    shift={shift}
                    selected={selectedShiftIds.has(shift.id)}
                    onToggle={toggleShift}
                  />
                ))}
              </div>
            </section>
          )}

        </div>
      )}

      {/* Identity form — shown when at least one slot is selected */}
      {showForm && (
        <div ref={formRef} className="scroll-mt-6">
          <Card className="mt-2 !border-sky-100 shadow-sm">
            {/* Selection summary — review before entering details */}
            {selectionCount > 0 && (
              <div className="mb-5 rounded-lg border border-sky-100 bg-sky-50/60 p-3 sm:p-4">
                <p className="text-sm font-semibold text-sky-900">
                  Your selections ({selectionCount})
                </p>
                <ul className="mt-2 flex flex-col gap-1">
                  {/* One line per shift, not per session — the volunteer picked
                      the shift, and listing its days here would read as several
                      separate bookings they could drop individually. */}
                  {selectedShifts.map((shift) => (
                    <li
                      key={shift.id}
                      className="flex items-center justify-between gap-2 text-sm text-[var(--color-fg)]"
                    >
                      <span className="min-w-0">
                        <span className="font-semibold">{shift.name}</span>
                        <span className="text-[var(--color-fg-muted)]">
                          {" "}· {sessionsInOrder(shift).length === 1
                            ? "1 session"
                            : `${sessionsInOrder(shift).length} sessions`}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() => toggleShift(shift.id)}
                        aria-label={`Remove ${shift.name}`}
                        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-rose-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600"
                      >
                        <XCircle className="h-5 w-5" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                  {selectedSlots.map((slot) => (
                    <li
                      key={slot.id}
                      className="flex items-center justify-between gap-2 text-sm text-[var(--color-fg)]"
                    >
                      <span className="min-w-0">
                        <span className="font-semibold">{slotDisplayLabel(slot)}</span>
                        <span className="text-[var(--color-fg-muted)]">
                          {" "}· {formatDate(slot.date)} · {formatTime(slot.start_time)} – {formatTime(slot.end_time)}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() => toggleSlot(slot.id)}
                        aria-label={`Remove ${slotDisplayLabel(slot)}`}
                        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-rose-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-600"
                      >
                        <XCircle className="h-5 w-5" aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <h2 className="text-lg font-semibold">Your information</h2>
            <p className="mt-1 mb-4 text-sm text-[var(--color-fg-muted)]">
              We'll email your confirmation and signup-management link here.
            </p>
            {submitError && (
              <p className="text-sm text-[var(--color-danger,#dc2626)] mb-3" role="alert">
                {submitError}
              </p>
            )}
            <form onSubmit={handleSubmit} noValidate className="grid gap-4 sm:grid-cols-2">
              <div>
                <Label htmlFor="first_name">First name</Label>
                <Input
                  id="first_name"
                  type="text"
                  value={identity.first_name}
                  onChange={(e) => handleIdentityChange("first_name", e.target.value)}
                  autoComplete="given-name"
                  required
                />
                <FieldError>{formErrors.first_name}</FieldError>
              </div>
              <div>
                <Label htmlFor="last_name">Last name</Label>
                <Input
                  id="last_name"
                  type="text"
                  value={identity.last_name}
                  onChange={(e) => handleIdentityChange("last_name", e.target.value)}
                  autoComplete="family-name"
                  required
                />
                <FieldError>{formErrors.last_name}</FieldError>
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  value={identity.email}
                  onChange={(e) => handleIdentityChange("email", e.target.value)}
                  autoComplete="email"
                  required
                />
                <FieldError>{formErrors.email}</FieldError>
              </div>
              <div className="sm:col-span-2">
                <Label htmlFor="phone">Phone</Label>
                <Input
                  id="phone"
                  type="tel"
                  value={identity.phone}
                  onChange={(e) => handleIdentityChange("phone", e.target.value)}
                  placeholder="(555) 123-4567"
                  autoComplete="tel"
                  required
                />
                <FieldError>{formErrors.phone}</FieldError>
              </div>
              {/* Phase 22 — dynamic custom form fields */}
              {formSchema.length > 0 && (
                <div className="sm:col-span-2 pt-2 border-t border-[var(--color-border)] flex flex-col gap-4">
                  <h3 className="text-sm font-semibold">
                    A few more questions
                  </h3>
                  {formSchema.map((f) => renderFormField(f))}
                </div>
              )}
              <div className="sm:col-span-2">
                <Button
                  type="submit"
                  variant="primary"
                  className="w-full min-h-11"
                  disabled={isSubmitting || outsideWindow}
                  title={outsideWindow ? windowBannerText : undefined}
                  data-testid="signup-submit"
                >
                  {isSubmitting
                    ? "Submitting..."
                    : outsideWindow
                      ? beforeWindow
                        ? "Signup not open yet"
                        : "Signup closed"
                      : "Sign up"}
                </Button>
                <p className="mt-2 text-center text-xs text-[var(--color-fg-muted)]">
                  You'll get a confirmation email with a link to view your signups.
                </p>
              </div>
            </form>
          </Card>
        </div>
      )}

      {/* Sticky mobile selection bar — pins to the viewport bottom while the
          volunteer scrolls the slot list (sticky, not fixed: the page root's
          entrance animation leaves a transform that would re-anchor fixed
          elements). Desktop shows the summary in the form card instead. */}
      {showForm && (
        <div
          className="sticky z-30 rounded-xl border border-sky-100 bg-white/95 px-4 py-3 shadow-[0_-4px_16px_rgba(15,23,42,0.12)] backdrop-blur md:hidden"
          style={{ bottom: "calc(0.75rem + env(safe-area-inset-bottom))" }}
        >
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm font-semibold text-[var(--color-fg)]">
              {selectionCount === 1 ? "1 selected" : `${selectionCount} selected`}
            </span>
            <Button type="button" variant="primary" className="min-h-11 px-6" onClick={scrollToForm}>
              Continue
            </Button>
          </div>
        </div>
      )}

      {/* Orientation modal — hard requirement when this event offers
          orientation sessions (server enforces it); advisory click-through
          only when it offers none (server exempts that case). */}
      <OrientationWarningModal
        open={step === "orientation-warning"}
        required={slots.some((s) => s.slot_type === "orientation")}
        onPickOrientation={handleOrientationNo}
        onYes={handleOrientationYes}
        onNo={handleOrientationNo}
        onFindOrientation={handleFindOrientationElsewhere}
      />

      {/* Success popup card */}
      {/* `event` enables the calendar buttons: right after signing up is the
          moment a volunteer actually wants the sessions on their phone. */}
      <SignupSuccessCard
        open={step === "success"}
        volunteerName={identity.first_name}
        slots={successData?.slots || []}
        signups={successData?.signups || []}
        event={event}
        onDismiss={handleDismissSuccess}
      />
    </div>
  );
}
