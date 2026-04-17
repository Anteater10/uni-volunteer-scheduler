// src/pages/public/EventDetailPage.jsx
//
// SignUpGenius-style event detail page.
// Table layout: Date | Location | Time | Slot (name + volunteers) | Sign Up
// Orientations first, then period slots grouped by day.
//
// SECURITY: No PII (name, email, phone) is logged, stored in localStorage/sessionStorage,
// or passed to analytics. Identity state lives only in React component state and is
// cleared on form reset or unmount.

import React, { useState, useMemo } from "react";
import { Link, useParams, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { XCircle } from "lucide-react";

import api from "../../lib/api";
import { downloadIcs } from "../../lib/calendar";
import { toast } from "../../state/toast";
import {
  Button,
  Card,
  Chip,
  Input,
  Label,
  FieldError,
  Skeleton,
  EmptyState,
  ErrorState,
  PageHeader,
} from "../../components/ui";
import OrientationWarningModal from "../../components/OrientationWarningModal";
import SignupSuccessCard from "../../components/SignupSuccessCard";

// ---------------------------------------------------------------------------
// Date/time helpers
// ---------------------------------------------------------------------------

function formatDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString.includes("T") ? isoString : `${isoString}T00:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function formatWeekday(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString.includes("T") ? isoString : `${isoString}T00:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "long" });
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
// Slot row for the table
// ---------------------------------------------------------------------------

function SlotRow({ slot, selected, onToggle, highlight }) {
  const isFull = slot.filled >= slot.capacity;

  return (
    <tr className={[
      "border-b border-[var(--color-border)] align-top",
      highlight && !isFull && slot.slot_type === "orientation" ? "bg-blue-50/50" : "",
    ].join(" ")}>
      {/* Sign Up button */}
      <td className="py-3 px-2 text-center align-top">
        {isFull ? (
          <span
            className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs font-semibold text-[var(--color-danger,#dc2626)]"
            aria-label="Slot full"
          >
            <XCircle size={12} aria-hidden="true" />
            Full
          </span>
        ) : (
          <button
            onClick={() => onToggle(slot.id)}
            className={[
              "px-3 py-1.5 rounded text-xs font-semibold transition-colors",
              selected
                ? "bg-green-600 text-white"
                : "bg-red-600 text-white hover:bg-red-700",
            ].join(" ")}
          >
            {selected ? "Selected" : "Sign Up"}
          </button>
        )}
      </td>
      {/* Slot name + volunteer list */}
      <td className="py-3 px-2">
        <div className="font-medium text-sm text-[var(--color-fg)]">
          {slot.slot_type === "orientation"
            ? `Orientation`
            : `Period ${slot._periodLabel || ""}`}
        </div>
        {slot.capacity > 0 && (
          <div className="text-xs text-[var(--color-fg-muted)] mt-0.5 mb-1">
            {slot.filled} of {slot.capacity} filled
          </div>
        )}
        {slot.signups && slot.signups.length > 0 && (
          <div className="flex flex-wrap mt-1">
            {slot.signups.map((s, i) => (
              <VolunteerChip key={i} firstName={s.first_name} lastInitial={s.last_initial} />
            ))}
          </div>
        )}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Day group (date + location + time + slots)
// ---------------------------------------------------------------------------

function DayGroup({ dateStr, location, slots, selectedSlotIds, onToggle, highlight }) {
  return (
    <tbody>
      {slots.map((slot, idx) => (
        <React.Fragment key={slot.id}>
          {idx === 0 ? (
            <tr className="border-b border-[var(--color-border)]">
              {/* Date + Location + Time spans all rows for this day */}
              <td
                rowSpan={slots.length * 2}
                className="py-3 px-3 align-top bg-[var(--color-surface)] border-r border-[var(--color-border)] w-36"
              >
                <div className="font-semibold text-sm">{formatShortDate(dateStr)}</div>
                <div className="text-xs text-[var(--color-fg-muted)]">{formatWeekday(dateStr)}</div>
                {location && (
                  <div className="text-xs text-[var(--color-fg-muted)] mt-1">{location}</div>
                )}
              </td>
              <td className="py-3 px-3 align-top border-r border-[var(--color-border)] w-28 text-xs text-[var(--color-fg)]">
                <div>{formatTime(slot.start_time)}-</div>
                <div>{formatTime(slot.end_time)}</div>
              </td>
              <SlotRowInline
                slot={slot}
                selected={selectedSlotIds.has(slot.id)}
                onToggle={onToggle}
                highlight={highlight}
              />
            </tr>
          ) : (
            <tr className="border-b border-[var(--color-border)]">
              <td className="py-3 px-3 align-top border-r border-[var(--color-border)] w-28 text-xs text-[var(--color-fg)]">
                <div>{formatTime(slot.start_time)}-</div>
                <div>{formatTime(slot.end_time)}</div>
              </td>
              <SlotRowInline
                slot={slot}
                selected={selectedSlotIds.has(slot.id)}
                onToggle={onToggle}
                highlight={highlight}
              />
            </tr>
          )}
        </React.Fragment>
      ))}
    </tbody>
  );
}

function SlotRowInline({ slot, selected, onToggle, highlight }) {
  const isFull = slot.filled >= slot.capacity;
  return (
    <>
      {/* Sign Up button */}
      <td className="py-3 px-2 text-center align-top w-20">
        {isFull ? (
          <span
            className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs font-semibold text-[var(--color-danger,#dc2626)]"
            aria-label="Slot full"
          >
            <XCircle size={12} aria-hidden="true" />
            Full
          </span>
        ) : (
          <button
            onClick={() => onToggle(slot.id)}
            className={[
              "px-3 py-1.5 rounded text-xs font-semibold transition-colors",
              selected
                ? "bg-green-600 text-white"
                : "bg-red-600 text-white hover:bg-red-700",
            ].join(" ")}
          >
            {selected ? "Selected" : "Sign Up"}
          </button>
        )}
      </td>
      {/* Slot name + volunteers */}
      <td className={[
        "py-3 px-2 align-top",
        highlight && !isFull && slot.slot_type === "orientation" ? "bg-blue-50/30" : "",
      ].join(" ")}>
        <div className="font-medium text-sm text-[var(--color-fg)]">
          {slot.slot_type === "orientation"
            ? "Orientation"
            : `Period ${slot._periodLabel || ""}`}
        </div>
        {slot.capacity > 0 && (
          <div className="text-xs text-[var(--color-fg-muted)] mt-0.5">
            {slot.filled} of {slot.capacity} filled
          </div>
        )}
        {slot.signups && slot.signups.length > 0 && (
          <div className="flex flex-wrap mt-1">
            {slot.signups.map((s, i) => (
              <VolunteerChip key={i} firstName={s.first_name} lastInitial={s.last_initial} />
            ))}
          </div>
        )}
      </td>
    </>
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
    <Card className="text-sm text-[var(--color-fg)] leading-relaxed">
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
            <a href="mailto:chem-scitrekmanager@ucsb.edu" className="text-[var(--color-primary)] underline">
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

  // Data fetching
  const eventQ = useQuery({
    queryKey: ["publicEvent", eventId],
    queryFn: () => api.public.getEvent(eventId),
    enabled: !!eventId,
  });

  // Build slot lookup and group slots by date
  const { slotMap, orientationSlots, periodSlotsByDate } = useMemo(() => {
    const slots = eventQ.data?.slots || [];
    const map = Object.fromEntries(slots.map((s) => [s.id, s]));

    const orientations = slots.filter((s) => s.slot_type === "orientation");
    const periods = slots.filter((s) => s.slot_type === "period");

    // Label periods: group by date+start_time, assign "1", "2", etc.
    const sorted = [...periods].sort((a, b) => {
      const dateComp = String(a.date).localeCompare(String(b.date));
      if (dateComp !== 0) return dateComp;
      return String(a.start_time).localeCompare(String(b.start_time));
    });

    // Assign period labels per date
    const byDate = {};
    for (const slot of sorted) {
      const key = String(slot.date);
      if (!byDate[key]) byDate[key] = [];
      const label = String(byDate[key].length + 1);
      byDate[key].push({ ...slot, _periodLabel: label });
    }

    // Also label orientations
    const labeledOrientations = orientations.map((s, i) => ({
      ...s,
      _periodLabel: orientations.length > 1 ? `#${i + 1}` : "",
    }));

    return { slotMap: map, orientationSlots: labeledOrientations, periodSlotsByDate: byDate };
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
    // Touch fullName so the helper isn't dead code if a future linter trims it.
    void fullName;
    return errors;
  }

  // Submit signup
  async function submitSignup() {
    setStep("submitting");
    const selectedSlots = [...selectedSlotIds].map((id) => slotMap[id]).filter(Boolean);
    try {
      const response = await api.public.createSignup({
        ...identity,
        slot_ids: [...selectedSlotIds],
      });
      setSuccessData({ ...response, slots: selectedSlots });
      setStep("success");
    } catch (err) {
      if (err.status === 429) {
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

    const hasPeriod = [...selectedSlotIds].some((id) => slotMap[id]?.slot_type === "period");
    const hasOrientation = [...selectedSlotIds].some(
      (id) => slotMap[id]?.slot_type === "orientation"
    );

    if (hasPeriod && !hasOrientation) {
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
          setStep("orientation-warning");
          return;
        }
      } catch {
        // On API error, proceed
      }
    }

    await submitSignup();
  }

  // Reset
  function handleDismissSuccess() {
    setStep("browse");
    setSelectedSlotIds(new Set());
    setIdentity({ first_name: "", last_name: "", email: "", phone: "" });
    setFormErrors({});
    setSubmitError(null);
    setSuccessData(null);
    setHighlightOrientation(false);
  }

  function handleOrientationYes() {
    submitSignup();
  }

  function handleOrientationNo() {
    setStep("browse");
    setHighlightOrientation(true);
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
  const showForm =
    selectedSlotIds.size > 0 && (step === "form" || step === "checking-orientation");
  const isSubmitting = step === "submitting" || step === "checking-orientation";

  const dateKeys = Object.keys(periodSlotsByDate).sort();

  return (
    <div className="flex flex-col gap-4 py-4 max-w-4xl mx-auto">
      {/* Back link */}
      <div>
        <Link to="/events" className="text-sm text-[var(--color-primary)] hover:underline">
          &larr; Back to events
        </Link>
      </div>

      {/* Event header */}
      <div>
        <h1 className="text-xl font-bold text-[var(--color-fg)]">
          {event.title}
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)] mt-1">
          {event.school} &middot; {formatDateRange(event.start_date, event.end_date)}
        </p>
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          Times shown in Pacific Time.
        </p>
      </div>

      {/* Event description (auto-generated + any custom admin text) */}
      <EventDescription event={event} orientationSlots={orientationSlots} />

      {/* Already signed up link */}
      <div className="text-sm">
        Already signed up?{" "}
        <Link to="/signup/manage" className="text-[var(--color-primary)] hover:underline font-medium">
          Change my sign up
        </Link>
      </div>

      {/* Add to calendar (PART-13 surface A) — secondary CTA below event metadata,
          above the slot list. Only renders when there is at least one slot to add. */}
      {slots.length > 0 && (
        <div className="mt-2 mb-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              // Slot precedence: selected → first non-full orientation → first slot
              const selectedSlot =
                [...selectedSlotIds]
                  .map((id) => slotMap[id])
                  .find(Boolean) ||
                orientationSlots.find(
                  (s) => (s.filled ?? 0) < (s.capacity ?? 0)
                ) ||
                slots[0];
              if (!selectedSlot) return;
              const dateStr =
                event.start_date
                  ? String(event.start_date).slice(0, 10)
                  : selectedSlot.start_time
                  ? new Date(selectedSlot.start_time)
                      .toISOString()
                      .slice(0, 10)
                  : "event";
              const slugPart = event.slug || event.id;
              const filename = `scitrek-${slugPart}-${dateStr}.ics`;
              downloadIcs({ event, slot: selectedSlot, filename });
              toast.success(
                "Calendar file saved. Open it to add to your calendar."
              );
            }}
          >
            Add to calendar
          </Button>
        </div>
      )}

      {/* Slot table */}
      {slots.length === 0 ? (
        <EmptyState
          title="Every slot is full"
          body="This event is fully booked. Try another event from this week's list."
          action={
            <Button variant="secondary" onClick={() => navigate("/events")}>
              Back to events
            </Button>
          }
        />
      ) : (
        <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-[var(--color-surface)] border-b border-[var(--color-border)]">
                <th className="py-2 px-3 text-left font-semibold text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">Date</th>
                <th className="py-2 px-3 text-left font-semibold text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">Time</th>
                <th className="py-2 px-2 text-center font-semibold text-xs uppercase tracking-wide text-[var(--color-fg-muted)]">Available Slot</th>
                <th className="py-2 px-2 text-left font-semibold text-xs uppercase tracking-wide text-[var(--color-fg-muted)]"></th>
              </tr>
            </thead>

            {/* Orientation slots */}
            {orientationSlots.length > 0 && (
              <>
                {orientationSlots.map((slot, idx) => (
                  <tbody key={slot.id}>
                    <tr className="border-b border-[var(--color-border)]">
                      {/* Date + location */}
                      <td className="py-3 px-3 align-top bg-[var(--color-surface)] border-r border-[var(--color-border)]">
                        <div className="font-semibold">{formatShortDate(slot.date)}</div>
                        <div className="text-xs text-[var(--color-fg-muted)]">{formatWeekday(slot.date)}</div>
                        {slot.location && (
                          <div className="text-xs text-[var(--color-fg-muted)] mt-1">{slot.location}</div>
                        )}
                      </td>
                      {/* Time */}
                      <td className="py-3 px-3 align-top border-r border-[var(--color-border)]">
                        <div>{formatTime(slot.start_time)}-</div>
                        <div>{formatTime(slot.end_time)}</div>
                      </td>
                      {/* Sign Up button */}
                      <td className="py-3 px-2 text-center align-top">
                        {slot.filled >= slot.capacity ? (
                          <span
                            className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs font-semibold text-[var(--color-danger,#dc2626)]"
                            aria-label="Slot full"
                          >
                            <XCircle size={12} aria-hidden="true" />
                            Full
                          </span>
                        ) : (
                          <button
                            onClick={() => toggleSlot(slot.id)}
                            className={[
                              "px-3 py-1.5 rounded text-xs font-semibold transition-colors",
                              selectedSlotIds.has(slot.id)
                                ? "bg-green-600 text-white"
                                : "bg-red-600 text-white hover:bg-red-700",
                            ].join(" ")}
                          >
                            {selectedSlotIds.has(slot.id) ? "Selected" : "Sign Up"}
                          </button>
                        )}
                      </td>
                      {/* Slot label + volunteers */}
                      <td className={[
                        "py-3 px-2 align-top",
                        highlightOrientation && slot.filled < slot.capacity ? "bg-blue-50/50" : "",
                      ].join(" ")}>
                        <div className="font-medium">
                          Orientation {slot._periodLabel}
                        </div>
                        {slot.capacity > 0 && (
                          <div className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                            {slot.filled} of {slot.capacity} filled
                          </div>
                        )}
                        {slot.signups?.length > 0 && (
                          <div className="flex flex-wrap mt-1.5">
                            {slot.signups.map((s, i) => (
                              <VolunteerChip key={i} firstName={s.first_name} lastInitial={s.last_initial} />
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  </tbody>
                ))}
              </>
            )}

            {/* Period slots grouped by date */}
            {dateKeys.map((dateKey) => {
              const daySlots = periodSlotsByDate[dateKey];
              const firstSlot = daySlots[0];
              return (
                <tbody key={dateKey}>
                  {daySlots.map((slot, idx) => (
                    <tr key={slot.id} className="border-b border-[var(--color-border)]">
                      {/* Date cell — only first row in group */}
                      {idx === 0 ? (
                        <td
                          rowSpan={daySlots.length}
                          className="py-3 px-3 align-top bg-[var(--color-surface)] border-r border-[var(--color-border)]"
                        >
                          <div className="font-semibold">{formatShortDate(dateKey)}</div>
                          <div className="text-xs text-[var(--color-fg-muted)]">{formatWeekday(dateKey)}</div>
                          {firstSlot.location && (
                            <div className="text-xs text-[var(--color-fg-muted)] mt-1">{firstSlot.location}</div>
                          )}
                        </td>
                      ) : null}
                      {/* Time */}
                      <td className="py-3 px-3 align-top border-r border-[var(--color-border)]">
                        <div>{formatTime(slot.start_time)}-</div>
                        <div>{formatTime(slot.end_time)}</div>
                      </td>
                      {/* Sign Up button */}
                      <td className="py-3 px-2 text-center align-top">
                        {slot.filled >= slot.capacity ? (
                          <span
                            className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-0.5 text-xs font-semibold text-[var(--color-danger,#dc2626)]"
                            aria-label="Slot full"
                          >
                            <XCircle size={12} aria-hidden="true" />
                            Full
                          </span>
                        ) : (
                          <button
                            onClick={() => toggleSlot(slot.id)}
                            className={[
                              "px-3 py-1.5 rounded text-xs font-semibold transition-colors",
                              selectedSlotIds.has(slot.id)
                                ? "bg-green-600 text-white"
                                : "bg-red-600 text-white hover:bg-red-700",
                            ].join(" ")}
                          >
                            {selectedSlotIds.has(slot.id) ? "Selected" : "Sign Up"}
                          </button>
                        )}
                      </td>
                      {/* Slot label + volunteers */}
                      <td className="py-3 px-2 align-top">
                        <div className="font-medium">Period {slot._periodLabel}</div>
                        {slot.capacity > 0 && (
                          <div className="text-xs text-[var(--color-fg-muted)] mt-0.5">
                            {slot.filled} of {slot.capacity} filled
                          </div>
                        )}
                        {slot.signups?.length > 0 && (
                          <div className="flex flex-wrap mt-1.5">
                            {slot.signups.map((s, i) => (
                              <VolunteerChip key={i} firstName={s.first_name} lastInitial={s.last_initial} />
                            ))}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              );
            })}
          </table>
        </div>
      )}

      {/* Identity form — shown when at least one slot is selected */}
      {showForm && (
        <Card className="mt-2">
          <h2 className="text-base font-semibold mb-3">Your information</h2>
          {submitError && (
            <p className="text-sm text-[var(--color-danger,#dc2626)] mb-3" role="alert">
              {submitError}
            </p>
          )}
          <form onSubmit={handleSubmit} noValidate className="flex flex-col gap-4">
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
            <div>
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
            <div>
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
            <Button
              type="submit"
              variant="primary"
              className="w-full min-h-11"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Submitting..." : "Sign up"}
            </Button>
          </form>
        </Card>
      )}

      {/* Orientation warning modal */}
      <OrientationWarningModal
        open={step === "orientation-warning"}
        onYes={handleOrientationYes}
        onNo={handleOrientationNo}
      />

      {/* Success popup card */}
      <SignupSuccessCard
        open={step === "success"}
        volunteerName={identity.first_name}
        slots={successData?.slots || []}
        onDismiss={handleDismissSuccess}
      />
    </div>
  );
}
