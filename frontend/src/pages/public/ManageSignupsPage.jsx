// src/pages/public/ManageSignupsPage.jsx
//
// Token-gated manage page for volunteers to view and cancel their signups.
// Can be rendered standalone at /signup/manage?token= or embedded by
// ConfirmSignupPage after a successful confirm (via tokenOverride prop).
//
// Phase 15-05 polish:
// - Local ErrorCard deleted; both error branches now use the shared
//   ErrorState primitive with UI-SPEC network-error copy.
// - Empty state uses UI-SPEC "You haven't signed up for anything yet"
//   with a "View events" PRIMARY action navigating to /events.
// - Cancel-single + Cancel-all Modal copy aligned to UI-SPEC §Destructive
//   confirmations table EXACTLY (titles, body, button labels).
// - Toast spelling normalized to American "canceled" (one L).
// - Status badges carry a lucide icon (CheckCircle / Clock) alongside the
//   text label so color is not the sole signal.
// - Page heading uses PageHeader primitive for UI-SPEC Display typography.

import React, { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle, Clock } from "lucide-react";
import api from "../../lib/api";
import { toast } from "../../state/toast";
import {
  Button,
  Card,
  Skeleton,
  EmptyState,
  ErrorState,
  Modal,
  PageHeader,
} from "../../components/ui";

// Use the no-Z pattern from EventDetailPage to avoid UTC offset shifts in JSDOM
function formatTime(isoString) {
  if (!isoString) return "";
  const d = new Date(isoString);
  return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
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
  const [cancelTarget, setCancelTarget] = useState(null); // signup_id
  const [canceling, setCanceling] = useState(false);
  const [cancelAllOpen, setCancelAllOpen] = useState(false);
  const [cancelingAll, setCancelingAll] = useState(false);

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
          <Button variant="primary" onClick={() => navigate("/events")}>
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
  // Cancel single
  // ------------------------------------------------------------------
  async function handleCancelConfirm() {
    if (!cancelTarget) return;
    setCanceling(true);
    try {
      await api.public.cancelSignup(cancelTarget, token);
      setSignups((prev) => prev.filter((s) => s.signup_id !== cancelTarget));
      toast.success("Signup canceled.");
    } catch (err) {
      if (err?.status === 403) {
        toast.error("You don't have permission to cancel this signup.");
      } else {
        toast.error(err?.message || "Failed to cancel signup.");
      }
    } finally {
      setCanceling(false);
      setCancelTarget(null);
    }
  }

  // ------------------------------------------------------------------
  // Cancel all
  // ------------------------------------------------------------------
  async function handleCancelAll() {
    setCancelingAll(true);
    const active = signups.filter((s) => s.status !== "cancelled");
    for (const s of active) {
      try {
        await api.public.cancelSignup(s.signup_id, token);
        setSignups((prev) => prev.filter((x) => x.signup_id !== s.signup_id));
      } catch (err) {
        toast.error(`Failed to cancel signup: ${err?.message || "Unknown error"}`);
        setCancelingAll(false);
        setCancelAllOpen(false);
        return; // stop on first failure
      }
    }
    setCancelingAll(false);
    setCancelAllOpen(false);
    toast.success("All signups canceled.");
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
            <Button variant="primary" onClick={() => navigate("/events")}>
              View events
            </Button>
          }
        />
      </div>
    );
  }

  const activeCount = signups.filter((s) => s.status !== "cancelled").length;

  return (
    <div className="max-w-xl mx-auto mt-8 px-4 space-y-4">
      <PageHeader
        title={
          data?.volunteer_first_name
            ? `Signups for ${data.volunteer_first_name} ${data.volunteer_last_name}`
            : "Your signups"
        }
      />

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

              {/* Status badge — icon + label so color isn't the sole signal */}
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
            </div>

            <Button
              variant="danger"
              size="sm"
              onClick={() => setCancelTarget(signup.signup_id)}
              disabled={canceling || cancelingAll}
            >
              Cancel
            </Button>
          </div>
        </Card>
      ))}

      {activeCount >= 2 && (
        <div className="pt-2">
          <Button
            variant="danger"
            onClick={() => setCancelAllOpen(true)}
            disabled={cancelingAll}
          >
            {cancelingAll ? "Canceling all…" : "Cancel all signups"}
          </Button>
        </div>
      )}

      {/* Cancel single modal — UI-SPEC §Destructive confirmations row 1 */}
      <Modal
        open={!!cancelTarget}
        onClose={() => !canceling && setCancelTarget(null)}
        title="Cancel this signup?"
      >
        <p className="text-sm text-gray-600 mb-4">
          You'll lose your spot. If the event fills up, you may not get it back.
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            variant="secondary"
            onClick={() => setCancelTarget(null)}
            disabled={canceling}
          >
            Keep signup
          </Button>
          <Button
            variant="danger"
            onClick={handleCancelConfirm}
            disabled={canceling}
          >
            {canceling ? "Canceling…" : "Yes, cancel"}
          </Button>
        </div>
      </Modal>

      {/* Cancel all modal — UI-SPEC §Destructive confirmations row 2 */}
      <Modal
        open={cancelAllOpen}
        onClose={() => !cancelingAll && setCancelAllOpen(false)}
        title="Cancel all signups?"
      >
        <p className="text-sm text-gray-600 mb-4">
          You'll lose every spot you've reserved for this event. This can't be
          undone.
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            variant="secondary"
            onClick={() => setCancelAllOpen(false)}
            disabled={cancelingAll}
          >
            Keep my signups
          </Button>
          <Button
            variant="danger"
            onClick={handleCancelAll}
            disabled={cancelingAll}
          >
            {cancelingAll ? "Canceling all…" : "Yes, cancel all"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
