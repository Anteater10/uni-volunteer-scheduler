// src/pages/public/EventsBrowsePage.jsx
//
// Public events browse page with week navigation.
// No auth required — renders for logged-out users (REQ-10-07).
// URL shape (issue #24): /events?quarter_id=<uuid>&week=3 — navigation walks
// the admin-entered quarter rows (summer Sessions A/B are separate rows).
// Legacy ?quarter=spring&year=2026&week=3 links canonicalize on load.

import React, { useContext, useEffect } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Calendar, Users, MapPin } from "lucide-react";

import api from "../../lib/api";
import { useQuarters } from "../../lib/useQuarters";
import {
  findQuarterById,
  formatWeekLabel,
  getNextWeek,
  getPrevWeek,
  resolveLegacyParams,
} from "../../lib/weekUtils";
import { Button, Skeleton, EmptyState, ErrorState } from "../../components/ui";
import { toast } from "../../state/toast";
import { AuthContext } from "../../state/AuthContext";

function formatLongDate(isoDate) {
  if (!isoDate) return "";
  return new Date(`${isoDate}T00:00:00Z`).toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatShortDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDayOfWeek(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleDateString("en-US", { weekday: "short" });
}

function slotCounts(slots) {
  if (!slots || slots.length === 0) return { total: 0, types: {}, filled: 0, capacity: 0 };
  const types = slots.reduce((acc, s) => {
    acc[s.slot_type] = (acc[s.slot_type] || 0) + 1;
    return acc;
  }, {});
  const filled = slots.reduce((n, s) => n + (s.filled ?? s.current_count ?? 0), 0);
  const capacity = slots.reduce((n, s) => n + (s.capacity ?? 0), 0);
  return { total: slots.length, types, filled, capacity };
}

function capacityStatus(filled, capacity) {
  if (!capacity) return { label: "Open", bg: "bg-[var(--color-brand-soft)]", fg: "text-[var(--color-brand)]", bar: "bg-[var(--color-brand)]" };
  const pct = filled / capacity;
  if (pct >= 1)
    return { label: "Full", bg: "bg-slate-100", fg: "text-slate-600", bar: "bg-slate-400" };
  if (pct >= 0.75)
    return { label: "Filling fast", bg: "bg-amber-50", fg: "text-[var(--color-warn)]", bar: "bg-[var(--color-warn)]" };
  return { label: "Open", bg: "bg-[var(--color-brand-soft)]", fg: "text-[var(--color-brand)]", bar: "bg-[var(--color-brand)]" };
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EventCard({ event }) {
  const { total, types, filled, capacity } = slotCounts(event.slots);
  const status = capacityStatus(filled, capacity);
  const pct = capacity ? Math.min(100, Math.round((filled / capacity) * 100)) : 0;
  const dateRange =
    event.start_date && event.end_date
      ? `${formatShortDate(event.start_date)} – ${formatShortDate(event.end_date)}`
      : "";
  const dayOfWeek = formatDayOfWeek(event.start_date);

  return (
    <Link
      to={`/volunteer/events/${event.id}`}
      className="group block focus-visible:outline-none rounded-2xl focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2"
    >
      <div className="hover-lift h-full flex flex-col rounded-2xl border border-[var(--color-border)] bg-white shadow-sm hover:shadow-lg hover:border-[var(--color-brand)]/40 overflow-hidden">
        {/* Accent bar */}
        <div className="h-1.5 bg-gradient-to-r from-[var(--color-brand)] via-indigo-500 to-[var(--color-accent)]" />

        <div className="flex-1 p-5 flex flex-col gap-3">
          {/* Top row: date chip + status chip */}
          <div className="flex items-center justify-between gap-2">
            {dateRange && (
              <div className="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-brand-soft)] px-3 py-1 text-xs font-medium text-[var(--color-brand)]">
                <Calendar size={12} />
                {dayOfWeek ? `${dayOfWeek} · ` : ""}
                {dateRange}
              </div>
            )}
            <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${status.bg} ${status.fg}`}>
              <span className={`h-1.5 w-1.5 rounded-full ${status.bar}`} />
              {status.label}
            </span>
          </div>

          {/* Title */}
          <h3 className="text-lg font-semibold text-[var(--color-fg)] leading-snug group-hover:text-[var(--color-brand)] transition-colors">
            {event.title}
          </h3>

          {/* School */}
          {event.school && (
            <p className="inline-flex items-center gap-1.5 text-sm text-[var(--color-fg-muted)]">
              <MapPin size={14} className="text-[var(--color-accent)]" />
              {event.school}
            </p>
          )}

          {/* Capacity progress */}
          {capacity > 0 && (
            <div className="mt-1">
              <div className="flex items-center justify-between text-xs mb-1">
                <span className="inline-flex items-center gap-1 text-[var(--color-fg-muted)]">
                  <Users size={12} />
                  {filled} of {capacity} volunteers
                </span>
                <span className={`font-semibold ${status.fg}`}>{pct}%</span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-slate-100 overflow-hidden">
                <div
                  className={`h-full ${status.bar} rounded-full transition-all duration-500`}
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          )}

          {/* Slot summary */}
          <div className="mt-auto pt-3 border-t border-[var(--color-border)] flex items-center justify-between text-sm">
            <div className="flex items-center gap-1.5 text-[var(--color-fg-muted)]">
              <Users size={14} />
              <span>
                {total} {total === 1 ? "slot" : "slots"}
              </span>
            </div>
            <div className="flex gap-1.5 flex-wrap justify-end">
              {Object.entries(types).map(([type, n]) => (
                <span
                  key={type}
                  className="inline-flex items-center rounded-md bg-[var(--color-accent-soft)] px-2 py-0.5 text-xs font-medium text-[var(--color-accent-strong)] capitalize"
                >
                  {n} {type}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    </Link>
  );
}

function LoadingSkeletons() {
  return (
    <div
      aria-busy="true"
      aria-live="polite"
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
    >
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <Skeleton key={i} className="h-48 rounded-2xl" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EventsBrowsePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  // Read auth context directly (not useAuth) so the public page still renders
  // when there's no AuthProvider wrapper (REQ-10-07). role is null when
  // logged out / no provider → the admin shortcut below stays hidden.
  const auth = useContext(AuthContext);
  const role = auth?.role ?? null;

  const currentWeekQ = useQuery({
    queryKey: ["publicCurrentWeek"],
    queryFn: () => api.public.getCurrentWeek(),
    staleTime: 5 * 60 * 1000,
  });
  const quartersQ = useQuarters();
  const quarters = quartersQ.data;

  const defaultWeek = currentWeekQ.data;
  const unconfigured = !!defaultWeek && defaultWeek.configured === false;

  const urlQuarterId = searchParams.get("quarter_id");
  const urlWeek = searchParams.get("week") ? Number(searchParams.get("week")) : null;
  const legacyQuarter = searchParams.get("quarter");
  const legacyYear = searchParams.get("year");
  const pendingLegacy = !urlQuarterId && !!legacyQuarter && !!legacyYear && !!urlWeek;

  // Legacy links (?quarter=&year=&week=) rewrite to quarter_id form once the
  // quarters list is available — summer resolves to its first session.
  useEffect(() => {
    if (!pendingLegacy || !quarters) return;
    const resolved = resolveLegacyParams(quarters, {
      quarter: legacyQuarter,
      year: legacyYear,
      week: urlWeek,
    });
    if (resolved) {
      setSearchParams(
        { quarter_id: resolved.quarter_id, week: String(resolved.week_number) },
        { replace: true },
      );
    } else {
      setSearchParams({}, { replace: true });
    }
  }, [pendingLegacy, quarters, legacyQuarter, legacyYear, urlWeek, setSearchParams]);

  const quarterId =
    urlQuarterId || (!pendingLegacy && defaultWeek ? defaultWeek.quarter_id : null);
  const weekNumber =
    urlQuarterId && urlWeek
      ? urlWeek
      : !pendingLegacy && defaultWeek
      ? defaultWeek.week_number
      : null;

  const allParamsReady = !unconfigured && !pendingLegacy && !!quarterId && !!weekNumber;
  const quarterRow = findQuarterById(quarters || [], quarterId);
  const isCurrentWeek =
    allParamsReady &&
    defaultWeek &&
    quarterId === defaultWeek.quarter_id &&
    weekNumber === defaultWeek.week_number;

  const eventsQ = useQuery({
    queryKey: ["publicEvents", quarterId, weekNumber],
    queryFn: async () => {
      try {
        return await api.public.listEvents({
          quarter_id: quarterId,
          week_number: weekNumber,
        });
      } catch (err) {
        if (err.status === 429) {
          toast.error("Please wait a moment and try again");
        }
        throw err;
      }
    },
    enabled: allParamsReady,
  });

  function applyWeek(target) {
    if (!target) return;
    setSearchParams({
      quarter_id: target.quarter_id,
      week: String(target.week_number),
    });
  }

  const nextTarget =
    allParamsReady && quarters ? getNextWeek(quarters, quarterId, weekNumber) : null;
  const prevTarget =
    allParamsReady && quarters ? getPrevWeek(quarters, quarterId, weekNumber) : null;

  function handlePrev() {
    applyWeek(prevTarget);
  }

  function handleNext() {
    applyWeek(nextTarget);
  }

  function handleThisWeek() {
    if (!defaultWeek || !defaultWeek.quarter_id) return;
    applyWeek({
      quarter_id: defaultWeek.quarter_id,
      week_number: defaultWeek.week_number,
    });
  }

  const events = eventsQ.data || [];
  const grouped = events.reduce((acc, e) => {
    const school = e.school || "Unknown";
    (acc[school] = acc[school] || []).push(e);
    return acc;
  }, {});

  const weekLabel =
    allParamsReady && quarterRow
      ? formatWeekLabel(quarterRow, weekNumber)
      : "Loading…";

  // Gap messaging: the resolved current week can point ahead at the next
  // quarter (starts_on set) or trail the last entered one (starts_on null).
  const gapRow = defaultWeek?.is_gap
    ? findQuarterById(quarters || [], defaultWeek.quarter_id)
    : null;
  const gapName =
    defaultWeek?.is_gap &&
    (gapRow?.display_name ||
      `${(defaultWeek.quarter || "").charAt(0).toUpperCase()}${(defaultWeek.quarter || "").slice(1)} ${defaultWeek.year}${defaultWeek.label ? ` · ${defaultWeek.label}` : ""}`);

  if (unconfigured) {
    return (
      <div className="flex flex-col">
        <section className="mt-8 animate-fade-up relative overflow-hidden rounded-3xl border border-[var(--color-border)] bg-gradient-to-br from-white to-[var(--color-brand-soft)] px-6 py-20 sm:py-28 text-center shadow-sm">
          <div className="relative z-10 max-w-lg mx-auto">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-brand-soft)] text-[var(--color-brand)] shadow-sm">
              <Calendar size={28} />
            </div>
            <h3 className="text-2xl sm:text-3xl font-bold text-[var(--color-fg)] tracking-tight">
              Schedule coming soon
            </h3>
            <p className="mt-3 text-[var(--color-fg-muted)]">
              The volunteer schedule hasn't been published yet. Check back
              soon!
            </p>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="flex flex-col">
      {/* ---- Admin/organizer shortcut (hidden for public + participants) ---- */}
      {(role === "admin" || role === "organizer") && (
        <div className="flex justify-end pt-4">
          <Link
            to="/admin"
            className="inline-flex items-center gap-1.5 rounded-lg bg-[var(--color-brand)] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:opacity-90 transition"
          >
            Admin control panel →
          </Link>
        </div>
      )}

      {/* ---- Hero / week navigator ---- */}
      <section className="animate-fade-up relative overflow-hidden rounded-2xl md:rounded-3xl bg-gradient-to-br from-[var(--color-brand)] via-indigo-600 to-indigo-800 text-white px-5 py-7 sm:px-8 sm:py-10 md:px-12 md:py-14 mt-4">
        {/* decorative blobs */}
        <div
          aria-hidden="true"
          className="absolute -top-20 -right-20 h-72 w-72 rounded-full bg-blue-400/25 blur-3xl"
        />
        <div
          aria-hidden="true"
          className="absolute -bottom-24 -left-10 h-80 w-80 rounded-full bg-indigo-300/20 blur-3xl"
        />

        <div className="relative z-10 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
          <div className="max-w-xl">
            <p className="text-xs sm:text-sm font-medium uppercase tracking-widest text-blue-200">
              UCSB SciTrek · Volunteer
            </p>
            <h1 className="mt-2 text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight leading-tight">
              Find a volunteer shift this week
            </h1>
            <p className="mt-3 text-sm sm:text-base text-blue-100/90">
              Pick a school, choose a time slot, and you're set — no account
              required.
            </p>
          </div>

          {/* Week nav */}
          <div className="flex flex-col gap-3 md:items-end">
            <div className="flex items-center gap-2 rounded-2xl bg-white/10 backdrop-blur ring-1 ring-white/20 p-1.5">
              <button
                onClick={handlePrev}
                disabled={!prevTarget}
                aria-label="Previous week"
                className="h-10 w-10 flex items-center justify-center rounded-xl hover:bg-white/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft size={20} />
              </button>
              <span className="px-3 min-w-[10rem] text-center text-sm sm:text-base font-semibold">
                {weekLabel}
              </span>
              <button
                onClick={handleNext}
                disabled={!nextTarget}
                aria-label="Next week"
                className="h-10 w-10 flex items-center justify-center rounded-xl hover:bg-white/15 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight size={20} />
              </button>
            </div>
            {!isCurrentWeek && defaultWeek && (
              <button
                type="button"
                onClick={handleThisWeek}
                className="self-start md:self-end text-sm font-medium text-blue-100 hover:text-white underline underline-offset-4 transition-colors"
              >
                Jump to this week
              </button>
            )}
          </div>
        </div>
      </section>

      {/* ---- Between-quarters banner (issue #24) ---- */}
      {defaultWeek?.is_gap && (
        <div
          role="status"
          className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900"
        >
          {defaultWeek.starts_on ? (
            <>
              We're between quarters — <strong>{gapName}</strong> starts{" "}
              {formatLongDate(defaultWeek.starts_on)}. You're viewing its
              upcoming schedule.
            </>
          ) : (
            <>
              The <strong>{gapName}</strong> schedule has wrapped up — check
              back soon for the next quarter.
            </>
          )}
        </div>
      )}

      {/* ---- Event list ---- */}
      <section className="mt-6 sm:mt-8">
        {!allParamsReady || eventsQ.isPending ? (
          <LoadingSkeletons />
        ) : eventsQ.isError ? (
          <ErrorState
            title="We couldn't load this page"
            body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
            action={
              <Button variant="secondary" onClick={() => eventsQ.refetch()}>
                Try again
              </Button>
            }
          />
        ) : events.length === 0 ? (
          <div className="animate-fade-up relative overflow-hidden rounded-3xl border border-[var(--color-border)] bg-gradient-to-br from-white to-[var(--color-brand-soft)] px-6 py-20 sm:py-28 text-center shadow-sm">
            <div aria-hidden="true" className="absolute -top-12 -right-12 h-48 w-48 rounded-full bg-[var(--color-brand)]/15 blur-3xl" />
            <div aria-hidden="true" className="absolute -bottom-16 -left-10 h-56 w-56 rounded-full bg-[var(--color-accent)]/15 blur-3xl" />
            <div className="relative z-10 max-w-lg mx-auto">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-[var(--color-brand-soft)] text-[var(--color-brand)] shadow-sm">
                <Calendar size={28} />
              </div>
              <h3 className="text-2xl sm:text-3xl font-bold text-[var(--color-fg)] tracking-tight">
                Nothing scheduled this week
              </h3>
              <p className="mt-3 text-[var(--color-fg-muted)]">
                New events go up on Mondays. Check back then, or browse next week's calendar.
              </p>
              <div className="mt-6">
                <Button variant="primary" onClick={handleNext}>
                  View next week →
                </Button>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-8 animate-fade-up">
            {Object.entries(grouped).map(([school, schoolEvents]) => (
              <section key={school}>
                <div className="flex items-baseline justify-between mb-3">
                  <h2 className="text-base sm:text-lg font-semibold text-[var(--color-fg)]">
                    {school}
                  </h2>
                  <span className="text-xs sm:text-sm text-[var(--color-fg-muted)]">
                    {schoolEvents.length}{" "}
                    {schoolEvents.length === 1 ? "event" : "events"}
                  </span>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                  {schoolEvents.map((e) => (
                    <EventCard key={e.id} event={e} />
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
