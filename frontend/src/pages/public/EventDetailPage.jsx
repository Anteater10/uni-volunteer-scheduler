// src/pages/public/EventDetailPage.jsx
//
// Event detail page with slot checkboxes, identity form, orientation warning modal,
// and success popup card. State machine: browse -> form -> checking-orientation ->
// orientation-warning -> submitting -> success.
//
// SECURITY: No PII (name, email, phone) is logged, stored in localStorage/sessionStorage,
// or passed to analytics. Identity state lives only in React component state and is
// cleared on form reset or unmount.

import React, { useState, useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import api from "../../lib/api";
import { toast } from "../../state/toast";
import {
  Button,
  Card,
  Input,
  Label,
  FieldError,
  Skeleton,
  EmptyState,
  PageHeader,
} from "../../components/ui";
import OrientationWarningModal from "../../components/OrientationWarningModal";
import SignupSuccessCard from "../../components/SignupSuccessCard";

// ---------------------------------------------------------------------------
// Date/time helpers (no PII involved)
// ---------------------------------------------------------------------------

function formatDate(isoString) {
  if (!isoString) return "";
  // Date strings like "2026-04-22" arrive without timezone; parse as local
  const d = new Date(isoString.includes("T") ? isoString : `${isoString}T00:00:00`);
  return d.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });
}

function formatTime(isoString) {
  if (!isoString) return "";
  // Do not append Z — treat as local time (the backend stores event times in local school TZ)
  const d = new Date(isoString);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function formatDateRange(start, end) {
  if (!start) return "";
  const s = formatDate(start);
  const e = end ? formatDate(end) : null;
  return e && e !== s ? `${s} – ${e}` : s;
}

// ---------------------------------------------------------------------------
// Slot card
// ---------------------------------------------------------------------------

function SlotCard({ slot, selected, onToggle, highlight }) {
  const isFull = slot.filled >= slot.capacity;
  const spotsLeft = slot.capacity - slot.filled;

  const handleClick = () => {
    if (!isFull) onToggle(slot.id);
  };

  return (
    <li
      onClick={handleClick}
      className={[
        "min-h-14 rounded-xl border p-3 flex items-center justify-between gap-3 cursor-pointer transition-colors",
        isFull
          ? "border-[var(--color-border)] opacity-60 cursor-not-allowed"
          : selected
          ? "border-[var(--color-primary)] bg-[var(--color-surface)]"
          : "border-[var(--color-border)] hover:bg-[var(--color-surface)]",
        highlight && !isFull && slot.slot_type === "orientation"
          ? "ring-2 ring-[var(--color-primary)]"
          : "",
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <div className="text-sm flex-1">
        <div className="font-medium">
          {formatDate(slot.date)}{" "}
          <span className="font-normal">
            {formatTime(slot.start_time)}–{formatTime(slot.end_time)}
          </span>
        </div>
        <div className="text-[var(--color-fg-muted)] text-xs mt-0.5">
          {slot.location}
          {" · "}
          {isFull ? (
            <span className="font-medium text-[var(--color-danger,#dc2626)]">Full</span>
          ) : (
            `${spotsLeft}/${slot.capacity} spots left`
          )}
        </div>
      </div>
      <input
        type="checkbox"
        className="h-5 w-5 min-w-5 accent-[var(--color-primary)]"
        checked={selected}
        onChange={() => onToggle(slot.id)}
        onClick={(e) => e.stopPropagation()}
        disabled={isFull}
        aria-label={`Select slot at ${formatTime(slot.start_time)} on ${formatDate(slot.date)}`}
      />
    </li>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function DetailSkeleton() {
  return (
    <div className="flex flex-col gap-4 py-4">
      <Skeleton className="h-16 rounded-xl" />
      <Skeleton className="h-32 rounded-xl" />
      <Skeleton className="h-32 rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EventDetailPage() {
  const { eventId } = useParams();
  const queryClient = useQueryClient();

  // State machine
  const [step, setStep] = useState("browse");
  // "browse" | "form" | "checking-orientation" | "orientation-warning" | "submitting" | "success"

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

  // Build a quick slot lookup map
  const slotMap = useMemo(() => {
    if (!eventQ.data?.slots) return {};
    return Object.fromEntries(eventQ.data.slots.map((s) => [s.id, s]));
  }, [eventQ.data]);

  // Slot toggle
  function toggleSlot(id) {
    setSelectedSlotIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
    // Auto-transition from browse to form when first slot selected
    setStep((prev) => (prev === "browse" ? "form" : prev));
    // Clear orientation highlight when user changes slots
    setHighlightOrientation(false);
  }

  // Identity field change
  function handleIdentityChange(field, value) {
    setIdentity((prev) => ({ ...prev, [field]: value }));
    // Clear per-field error on change
    if (formErrors[field]) {
      setFormErrors((prev) => {
        const next = { ...prev };
        delete next[field];
        return next;
      });
    }
  }

  // Client-side validation
  function validateIdentity() {
    const errors = {};
    if (!identity.first_name.trim()) errors.first_name = "First name is required";
    if (!identity.last_name.trim()) errors.last_name = "Last name is required";
    if (!identity.email.trim()) {
      errors.email = "Email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(identity.email)) {
      errors.email = "Enter a valid email address";
    }
    if (!identity.phone.trim()) {
      errors.phone = "Phone number is required";
    } else {
      const digits = identity.phone.replace(/\D/g, "");
      if (digits.length < 10) errors.phone = "Enter a valid phone number (10+ digits)";
    }
    return errors;
  }

  // Submit the signup to the backend
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
        // Parse FastAPI validation errors into per-field errors
        const detail = err.response?.data?.detail;
        if (Array.isArray(detail)) {
          const fieldErrs = {};
          detail.forEach((d) => {
            const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : null;
            if (field) {
              fieldErrs[field] = d.msg || "Invalid value";
            }
          });
          if (Object.keys(fieldErrs).length > 0) {
            setFormErrors(fieldErrs);
          } else {
            setSubmitError(err.message);
          }
        } else {
          setSubmitError(err.message);
        }
        setStep("form");
      } else if (
        err.message?.toLowerCase().includes("capacity") ||
        err.message?.toLowerCase().includes("full") ||
        err.status === 409
      ) {
        toast.error(
          "One or more selected slots are now full. Please pick different slots."
        );
        setStep("browse");
        // Refetch event to get updated filled counts
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

    // Check if orientation check is needed:
    // any selected slot is slot_type="period" AND no selected slot is slot_type="orientation"
    const hasPeriod = [...selectedSlotIds].some((id) => slotMap[id]?.slot_type === "period");
    const hasOrientation = [...selectedSlotIds].some(
      (id) => slotMap[id]?.slot_type === "orientation"
    );

    if (hasPeriod && !hasOrientation) {
      setStep("checking-orientation");
      try {
        const result = await api.public.orientationStatus(identity.email);
        if (!result.has_attended_orientation) {
          setStep("orientation-warning");
          return;
        }
        // has_attended_orientation === true: skip modal, proceed
      } catch {
        // On API error, proceed — don't block signup over a failed orientation check
      }
    }

    await submitSignup();
  }

  // Dismiss success card and reset everything
  function handleDismissSuccess() {
    setStep("browse");
    setSelectedSlotIds(new Set());
    setIdentity({ first_name: "", last_name: "", email: "", phone: "" });
    setFormErrors({});
    setSubmitError(null);
    setSuccessData(null);
    setHighlightOrientation(false);
  }

  // Orientation modal handlers
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
      <EmptyState
        title="Could not load event"
        body={eventQ.error?.message || "Something went wrong."}
        action={
          <Button variant="secondary" onClick={() => eventQ.refetch()}>
            Retry
          </Button>
        }
      />
    );
  }

  const event = eventQ.data;
  const slots = event?.slots || [];
  const orientationSlots = slots.filter((s) => s.slot_type === "orientation");
  const periodSlots = slots.filter((s) => s.slot_type === "period");

  const showForm =
    selectedSlotIds.size > 0 && (step === "form" || step === "checking-orientation");
  const isSubmitting = step === "submitting" || step === "checking-orientation";

  return (
    <div className="flex flex-col gap-4 py-4">
      {/* Back link */}
      <div>
        <Link
          to="/events"
          className="text-sm text-[var(--color-primary)] hover:underline"
        >
          ← Back to events
        </Link>
      </div>

      {/* Event header */}
      <PageHeader
        title={event.title}
        subtitle={[
          event.school,
          formatDateRange(event.start_date, event.end_date),
        ]
          .filter(Boolean)
          .join(" · ")}
      />

      {/* Orientation slots */}
      {orientationSlots.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-fg-muted)] mb-2">
            Orientation Slots
          </h2>
          <ul className="flex flex-col gap-2">
            {orientationSlots.map((slot) => (
              <SlotCard
                key={slot.id}
                slot={slot}
                selected={selectedSlotIds.has(slot.id)}
                onToggle={toggleSlot}
                highlight={highlightOrientation}
              />
            ))}
          </ul>
        </section>
      )}

      {/* Period slots */}
      {periodSlots.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wide text-[var(--color-fg-muted)] mb-2">
            Period Slots
          </h2>
          <ul className="flex flex-col gap-2">
            {periodSlots.map((slot) => (
              <SlotCard
                key={slot.id}
                slot={slot}
                selected={selectedSlotIds.has(slot.id)}
                onToggle={toggleSlot}
                highlight={false}
              />
            ))}
          </ul>
        </section>
      )}

      {slots.length === 0 && (
        <EmptyState title="No slots available" body="Check back later." />
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
            {/* First name */}
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

            {/* Last name */}
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

            {/* Email */}
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

            {/* Phone */}
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
              {isSubmitting ? "Submitting…" : "Sign up"}
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
