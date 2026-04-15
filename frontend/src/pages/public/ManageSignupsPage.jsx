// src/pages/public/ManageSignupsPage.jsx
//
// Token-gated manage page for volunteers to view and cancel their signups.
// Can be rendered standalone at /signup/manage?token= or embedded by
// ConfirmSignupPage after a successful confirm (via tokenOverride prop).

import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api from "../../lib/api";
import { toast } from "../../state/toast";
import { Button, Card, Skeleton, EmptyState, Modal } from "../../components/ui";

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

function ErrorCard() {
  return (
    <Card className="max-w-md mx-auto mt-12 p-6 text-center">
      <h2 className="text-lg font-semibold text-gray-900 mb-2">
        Link expired or invalid
      </h2>
      <p className="text-gray-600">
        This link has expired or is invalid. Please check your email for a new
        link.
      </p>
    </Card>
  );
}

export default function ManageSignupsPage({ tokenOverride }) {
  const [searchParams] = useSearchParams();
  const token = tokenOverride || searchParams.get("token");

  const [signups, setSignups] = useState([]);
  const [cancelTarget, setCancelTarget] = useState(null); // signup_id
  const [cancelling, setCancelling] = useState(false);
  const [cancelAllOpen, setCancelAllOpen] = useState(false);
  const [cancellingAll, setCancellingAll] = useState(false);

  const { data, isLoading, error } = useQuery({
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
    return <ErrorCard />;
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
  // Token error state
  // ------------------------------------------------------------------
  if (error) {
    return <ErrorCard />;
  }

  // ------------------------------------------------------------------
  // Cancel single
  // ------------------------------------------------------------------
  async function handleCancelConfirm() {
    if (!cancelTarget) return;
    setCancelling(true);
    try {
      await api.public.cancelSignup(cancelTarget, token);
      setSignups((prev) => prev.filter((s) => s.signup_id !== cancelTarget));
      toast.success("Signup cancelled.");
    } catch (err) {
      if (err?.status === 403) {
        toast.error("You don't have permission to cancel this signup.");
      } else {
        toast.error(err?.message || "Failed to cancel signup.");
      }
    } finally {
      setCancelling(false);
      setCancelTarget(null);
    }
  }

  // ------------------------------------------------------------------
  // Cancel all
  // ------------------------------------------------------------------
  async function handleCancelAll() {
    setCancellingAll(true);
    const active = signups.filter((s) => s.status !== "cancelled");
    for (const s of active) {
      try {
        await api.public.cancelSignup(s.signup_id, token);
        setSignups((prev) => prev.filter((x) => x.signup_id !== s.signup_id));
      } catch (err) {
        toast.error(`Failed to cancel signup: ${err?.message || "Unknown error"}`);
        setCancellingAll(false);
        setCancelAllOpen(false);
        return; // stop on first failure
      }
    }
    setCancellingAll(false);
    setCancelAllOpen(false);
    toast.success("All signups cancelled.");
  }

  // ------------------------------------------------------------------
  // Empty state
  // ------------------------------------------------------------------
  if (signups.length === 0) {
    return (
      <div className="max-w-xl mx-auto mt-8 px-4">
        <EmptyState
          title="No upcoming signups"
          body="No upcoming signups found for this event."
        />
      </div>
    );
  }

  const activeCount = signups.filter((s) => s.status !== "cancelled").length;

  return (
    <div className="max-w-xl mx-auto mt-8 px-4 space-y-4">
      <h1 className="text-xl font-semibold text-gray-900">Your Signups</h1>

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

              {/* Status badge */}
              <span
                className={
                  signup.status === "confirmed"
                    ? "inline-block text-xs font-medium px-2 py-0.5 rounded-full bg-green-100 text-green-700"
                    : "inline-block text-xs font-medium px-2 py-0.5 rounded-full bg-yellow-100 text-yellow-700"
                }
              >
                {signup.status === "confirmed" ? "Confirmed" : "Pending"}
              </span>
            </div>

            <Button
              variant="danger"
              size="sm"
              onClick={() => setCancelTarget(signup.signup_id)}
              disabled={cancelling || cancellingAll}
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
            disabled={cancellingAll}
          >
            {cancellingAll ? "Cancelling..." : "Cancel all signups"}
          </Button>
        </div>
      )}

      {/* Cancel single modal */}
      <Modal
        open={!!cancelTarget}
        onClose={() => !cancelling && setCancelTarget(null)}
        title="Cancel this signup?"
      >
        <p className="text-sm text-gray-600 mb-4">
          This will remove your signup. You can sign up again if spots are
          available.
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            variant="ghost"
            onClick={() => setCancelTarget(null)}
            disabled={cancelling}
          >
            Never mind
          </Button>
          <Button
            variant="danger"
            onClick={handleCancelConfirm}
            disabled={cancelling}
          >
            {cancelling ? "Cancelling..." : "Yes, cancel"}
          </Button>
        </div>
      </Modal>

      {/* Cancel all modal */}
      <Modal
        open={cancelAllOpen}
        onClose={() => !cancellingAll && setCancelAllOpen(false)}
        title={`Cancel all ${activeCount} signups for this event?`}
      >
        <p className="text-sm text-gray-600 mb-4">
          This will cancel all your upcoming signups for this event.
        </p>
        <div className="flex gap-3 justify-end">
          <Button
            variant="ghost"
            onClick={() => setCancelAllOpen(false)}
            disabled={cancellingAll}
          >
            Never mind
          </Button>
          <Button
            variant="danger"
            onClick={handleCancelAll}
            disabled={cancellingAll}
          >
            {cancellingAll ? "Cancelling..." : "Yes, cancel all"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
