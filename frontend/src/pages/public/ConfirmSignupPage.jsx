// src/pages/public/ConfirmSignupPage.jsx
//
// Entry point from the confirmation email link (/signup/confirm?token=...).
// Calls the confirm endpoint then renders the manage view INLINE (no redirect).
// Per locked decision 1: inline render after confirm succeeds.
//
// Phase 15-05 polish:
// - Loading: Skeleton stack wrapped in aria-busy/aria-live region (replaces
//   the raw page-level spinner banned by RESEARCH §Anti-Patterns).
// - Error: shared ErrorState primitive with UI-SPEC magic-link-expired copy
//   and a "Back to events" PRIMARY button.
// - Success: green confirmation banner kept; ManageSignupsPage still embedded.
//   PART-13 surface B (Add-to-Calendar) inside SignupSuccessCard is wired in
//   the component itself, but the confirm response does not currently return
//   event + slot, so the calendar button stays gated until the backend
//   payload is extended (out of scope per D-14 — api.js read-only).

import React, { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api from "../../lib/api";
import { Button, Skeleton, ErrorState } from "../../components/ui";
import ManageSignupsPage from "./ManageSignupsPage";

// State machine: confirming | confirmed | error
export default function ConfirmSignupPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token");
  const [state, setState] = useState("confirming");

  useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }
    api.public
      .confirmSignup(token)
      .then(() => setState("confirmed"))
      .catch(() => setState("error"));
  }, [token]);

  if (state === "confirming") {
    return (
      <div
        aria-busy="true"
        aria-live="polite"
        className="max-w-md mx-auto mt-12 space-y-3 px-4"
      >
        <Skeleton className="h-8 rounded-xl" />
        <Skeleton className="h-16 rounded-xl" />
        <Skeleton className="h-10 rounded-xl" />
      </div>
    );
  }

  if (state === "error") {
    // The current state machine collapses expired vs invalid into a single
    // "error" branch. Per UI-SPEC §Error states, the expired copy is the
    // most common case (24h TTL); use it as the default.
    return (
      <ErrorState
        title="This link has expired"
        body="Magic links are good for 24 hours. Open the event again and re-submit your signup to get a new one."
        action={
          <Button variant="primary" onClick={() => navigate("/events")}>
            Back to events
          </Button>
        }
      />
    );
  }

  // confirmed — render manage view inline with same token
  return (
    <div>
      <div className="max-w-xl mx-auto mt-6 px-4">
        <div className="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
          <p className="text-green-800 font-medium text-sm">
            Your signup is confirmed! You can manage or cancel your signups
            below.
          </p>
        </div>
      </div>
      <ManageSignupsPage tokenOverride={token} />
    </div>
  );
}
