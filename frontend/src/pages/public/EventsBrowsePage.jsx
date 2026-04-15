// src/pages/public/EventsBrowsePage.jsx
//
// Public events browse page with week navigation.
// No auth required — renders for logged-out users (REQ-10-07).
// URL shape: /events?quarter=spring&year=2026&week=3

import React from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight } from "lucide-react";

import api from "../../lib/api";
import { getNextWeek, getPrevWeek, formatWeekLabel } from "../../lib/weekUtils";
import { Button, Card, Skeleton, EmptyState, ErrorState } from "../../components/ui";
import { toast } from "../../state/toast";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format a date string (ISO) into a short readable form, e.g. "Apr 22". */
function formatShortDate(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/** Summarise slot counts for a card subtitle, e.g. "2 orientation · 3 period". */
function slotSummary(slots) {
  if (!slots || slots.length === 0) return "No slots";
  const counts = slots.reduce(
    (acc, s) => {
      acc[s.slot_type] = (acc[s.slot_type] || 0) + 1;
      return acc;
    },
    {}
  );
  return Object.entries(counts)
    .map(([type, n]) => `${n} ${type}`)
    .join(" · ");
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function EventCard({ event }) {
  const dateRange =
    event.start_date && event.end_date
      ? `${formatShortDate(event.start_date)} – ${formatShortDate(event.end_date)}`
      : "";

  return (
    <Link to={`/events/${event.id}`} className="block focus-visible:outline-none">
      <Card className="hover:shadow-md transition-shadow cursor-pointer">
        <p className="font-semibold text-[var(--color-fg)]">{event.title}</p>
        {dateRange && (
          <p className="text-sm text-[var(--color-fg-muted)] mt-1">{dateRange}</p>
        )}
        <p className="text-xs text-[var(--color-fg-muted)] mt-1">
          {slotSummary(event.slots)}
        </p>
      </Card>
    </Link>
  );
}

function LoadingSkeletons() {
  return (
    <div aria-busy="true" aria-live="polite" className="flex flex-col gap-3">
      <Skeleton className="h-24 rounded-xl" />
      <Skeleton className="h-24 rounded-xl" />
      <Skeleton className="h-24 rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function EventsBrowsePage() {
  const [searchParams, setSearchParams] = useSearchParams();

  // ------------------------------------------------------------------
  // Step 1: Fetch the current week from backend (used as default when
  // no URL params are present).
  // ------------------------------------------------------------------
  const currentWeekQ = useQuery({
    queryKey: ["publicCurrentWeek"],
    queryFn: () => api.public.getCurrentWeek(),
    staleTime: 5 * 60 * 1000, // 5 min — quarter/week won't change mid-session
  });

  // ------------------------------------------------------------------
  // Step 2: Derive active quarter/year/weekNumber from URL or backend.
  // ------------------------------------------------------------------
  const defaultWeek = currentWeekQ.data;

  const quarter =
    searchParams.get("quarter") || (defaultWeek ? defaultWeek.quarter : null);
  const year = searchParams.get("year")
    ? Number(searchParams.get("year"))
    : defaultWeek
    ? defaultWeek.year
    : null;
  const weekNumber = searchParams.get("week")
    ? Number(searchParams.get("week"))
    : defaultWeek
    ? defaultWeek.week_number
    : null;

  const allParamsReady = !!quarter && !!year && !!weekNumber;

  // ------------------------------------------------------------------
  // Step 3: Fetch events for the active week.
  // ------------------------------------------------------------------
  const eventsQ = useQuery({
    queryKey: ["publicEvents", quarter, year, weekNumber],
    queryFn: async () => {
      try {
        return await api.public.listEvents({
          quarter,
          year,
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

  // ------------------------------------------------------------------
  // Navigation helpers
  // ------------------------------------------------------------------
  function applyWeek({ quarter: q, year: y, week_number: w }) {
    setSearchParams({ quarter: q, year: String(y), week: String(w) });
  }

  function handlePrev() {
    if (!allParamsReady) return;
    applyWeek(getPrevWeek(quarter, year, weekNumber));
  }

  function handleNext() {
    if (!allParamsReady) return;
    applyWeek(getNextWeek(quarter, year, weekNumber));
  }

  function handleThisWeek() {
    if (!defaultWeek) return;
    applyWeek({
      quarter: defaultWeek.quarter,
      year: defaultWeek.year,
      week_number: defaultWeek.week_number,
    });
  }

  // ------------------------------------------------------------------
  // Group events by school
  // ------------------------------------------------------------------
  const events = eventsQ.data || [];
  const grouped = events.reduce((acc, e) => {
    const school = e.school || "Unknown";
    (acc[school] = acc[school] || []).push(e);
    return acc;
  }, {});

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------
  const weekLabel = allParamsReady
    ? formatWeekLabel(quarter, year, weekNumber)
    : "Loading…";

  return (
    <div className="flex flex-col gap-4 py-4 px-4 md:px-8">
      {/* ---- Week navigator ---- */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <button
            onClick={handlePrev}
            disabled={!allParamsReady}
            aria-label="Previous week"
            className="min-h-11 min-w-11 flex items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] hover:bg-[var(--color-surface)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronLeft size={20} />
          </button>

          <span className="flex-1 text-center font-semibold text-[var(--color-fg)]">
            {weekLabel}
          </span>

          <button
            onClick={handleNext}
            disabled={!allParamsReady}
            aria-label="Next week"
            className="min-h-11 min-w-11 flex items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-bg)] hover:bg-[var(--color-surface)] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            <ChevronRight size={20} />
          </button>
        </div>

        <div className="flex justify-center">
          <Button
            variant="secondary"
            size="md"
            onClick={handleThisWeek}
            disabled={!defaultWeek}
          >
            This week
          </Button>
        </div>
      </div>

      {/* ---- Event list ---- */}
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
        <EmptyState
          title="Nothing scheduled this week"
          body="New events go up on Mondays. Check back then, or browse next week's calendar."
          action={
            <Button variant="secondary" onClick={handleNext}>
              View next week
            </Button>
          }
        />
      ) : (
        <div className="flex flex-col gap-2">
          {Object.entries(grouped).map(([school, schoolEvents]) => (
            <section key={school}>
              <h2 className="text-sm font-medium uppercase tracking-wide text-[var(--color-fg-muted)] mt-4 mb-2">
                {school}
              </h2>
              <div className="flex flex-col gap-3">
                {schoolEvents.map((e) => (
                  <EventCard key={e.id} event={e} />
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
