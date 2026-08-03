// src/pages/public/ManageSignupsPage.jsx
//
// Token-gated read-only view of a volunteer's signups plus their reminder
// preferences. Can be rendered standalone at /signup/manage?token= or
// embedded by ConfirmSignupPage after a successful confirm (via
// tokenOverride prop).
//
// 2026-08-02 read-only signups: cancel and move-to-another-slot are gone.
// Schedule changes are now coordinated directly with the SciTrek organizers
// — the page surfaces an "email the organizers" notice (using the
// admin-configured contact_email off the manage payload, with a fallback to
// "reply to your confirmation email" when no address is configured) instead
// of self-service cancel/swap controls.
//
// Carried over from Phase 15-05 polish:
// - Local ErrorCard deleted; both error branches now use the shared
//   ErrorState primitive with UI-SPEC network-error copy.
// - Empty state uses UI-SPEC "You haven't signed up for anything yet"
//   with a "View events" PRIMARY action navigating to /events.
// - Status badges carry a lucide icon (CheckCircle / Clock) alongside the
//   text label so color is not the sole signal.

import React, { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Clock } from "lucide-react";
import api from "../../lib/api";
import {
  Button,
  Card,
  Skeleton,
  EmptyState,
  ErrorState,
} from "../../components/ui";
import ReminderPreferencesCard from "../../components/ReminderPreferencesCard";

// Slot datetimes arrive as UTC ISO strings (e.g. "2026-04-16T09:00:00Z").
// Render them in SciTrek's venue timezone so all viewers see wall-clock at UCSB.
const VENUE_TZ = "America/Los_Angeles";

function formatTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: VENUE_TZ,
  });
}

function formatDate(dateString) {
  if (!dateString) return "";
  return new Date(dateString + "T00:00:00").toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
}

export default function ManageSignupsPage({ tokenOverride }) {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = tokenOverride || searchParams.get("token");

  const [signups, setSignups] = useState([]);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["manage-signups", token],
    queryFn: () => api.public.getManageSignups(token),
    enabled: !!token,
    retry: false,
  });

  // Sync signups from query data when it arrives
  React.useEffect(() => {
    if (data?.signups) {
      setSignups(data.signups);
    }
  }, [data]);

  // ------------------------------------------------------------------
  // Guard: no token in URL and no override
  // ------------------------------------------------------------------
  if (!token) {
    return (
      <ErrorState
        title="We couldn't load this page"
        body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
        action={
          <Button variant="primary" onClick={() => navigate("/volunteer")}>
            Back to events
          </Button>
        }
      />
    );
  }

  // ------------------------------------------------------------------
  // Loading state
  // ------------------------------------------------------------------
  if (isLoading) {
    return (
      <div className="max-w-xl mx-auto mt-8 space-y-4 px-4">
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
        <Skeleton className="h-24 rounded-xl" />
      </div>
    );
  }

  // ------------------------------------------------------------------
  // Token / fetch error state
  // ------------------------------------------------------------------
  if (error) {
    return (
      <ErrorState
        title="We couldn't load this page"
        body="Check your connection and try again. If the problem continues, email scitrek@ucsb.edu."
        action={
          <Button variant="secondary" onClick={() => refetch()}>
            Try again
          </Button>
        }
      />
    );
  }

  // ------------------------------------------------------------------
  // Empty state
  // ------------------------------------------------------------------
  if (signups.length === 0) {
    return (
      <div className="max-w-xl mx-auto mt-8 px-4">
        <EmptyState
          title="You haven't signed up for anything yet"
          body="Browse this week's volunteer events to get started."
          action={
            <Button variant="primary" onClick={() => navigate("/volunteer")}>
              View events
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto mt-6 sm:mt-8 px-1 sm:px-4 space-y-5">
      <section className="relative overflow-hidden rounded-2xl md:rounded-3xl bg-gradient-to-br from-blue-600 via-indigo-600 to-indigo-800 text-white p-6 sm:p-8">
        <div
          aria-hidden="true"
          className="absolute -top-16 -right-16 h-56 w-56 rounded-full bg-blue-400/25 blur-3xl"
        />
        <div className="relative z-10">
          <p className="text-xs sm:text-sm font-medium uppercase tracking-widest text-blue-200">
            Your signups
          </p>
          <h1 className="mt-2 text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight leading-tight">
            {data?.volunteer_first_name
              ? `Hi ${data.volunteer_first_name}`
              : "Your signups"}
          </h1>
          <p className="mt-2 text-sm text-blue-100">
            View your volunteer shifts. Times shown in Pacific Time.
          </p>
        </div>
      </section>

      {signups.map((signup) => (
        <Card key={signup.signup_id} className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 space-y-1">
              {/* Slot type badge */}
              <span
                className={
                  signup.slot?.slot_type === "orientation"
                    ? "inline-block text-xs font-medium px-2 py-0.5 rounded-full bg-blue-100 text-blue-700"
                    : "inline-block text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700"
                }
              >
                {signup.slot?.slot_type === "orientation"
                  ? "Orientation"
                  : "Period"}
              </span>

              <p className="text-sm font-medium text-gray-900">
                {formatDate(signup.slot?.date)}
              </p>
              <p className="text-sm text-gray-600">
                {formatTime(signup.slot?.start_time)} –{" "}
                {formatTime(signup.slot?.end_time)}
              </p>
              {signup.slot?.location && (
                <p className="text-sm text-gray-500">{signup.slot.location}</p>
              )}

              {/* Status badge — icon + label so color isn't the sole signal.
                  Phase 25 (WAIT-01): waitlisted rows carry a distinct orange
                  badge with their current FIFO position. */}
              {signup.status === "waitlisted" ? (
                <span
                  className="inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-orange-100 text-orange-700"
                  data-testid="waitlist-badge"
                >
                  <Clock size={12} aria-hidden="true" />
                  Waitlist #{signup.waitlist_position ?? "—"}
                </span>
              ) : (
                <span
                  className={
                    signup.status === "confirmed"
                      ? "inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700"
                      : "inline-flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700"
                  }
                >
                  {signup.status === "confirmed" ? (
                    <CheckCircle size={12} aria-hidden="true" />
                  ) : (
                    <Clock size={12} aria-hidden="true" />
                  )}
                  {signup.status === "confirmed" ? "Confirmed" : "Pending"}
                </span>
              )}
            </div>
          </div>
        </Card>
      ))}

      <Card className="p-4" data-testid="contact-notice">
        <p className="text-sm font-medium text-gray-900">
          Need to change or cancel a signup?
        </p>
        <p className="mt-1 text-sm text-gray-600">
          Schedule changes are coordinated with the SciTrek organizers —{" "}
          {data?.contact_email ? (
            <>
              email{" "}
              <a
                className="font-medium text-blue-700 underline"
                href={`mailto:${data.contact_email}`}
              >
                {data.contact_email}
              </a>{" "}
              and they&apos;ll take care of it.
            </>
          ) : (
            <>reply to your confirmation email and they&apos;ll take care of it.</>
          )}
        </p>
      </Card>

      {/* Phase 24 — reminder opt-out toggle (REM-03) */}
      <ReminderPreferencesCard manageToken={token} />
    </div>
  );
}
