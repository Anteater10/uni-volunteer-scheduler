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
//
// 2026-07-29 sweep remediation, Finding #1: the confirm endpoint can resolve
// (HTTP 200) with `confirmed: false` — the token was legitimately consumed
// but didn't confirm anything. This used to be indistinguishable from a real
// success (the resolved value was ignored entirely), so e.g. a promoted
// volunteer clicking their original batch link was told their spot was
// confirmed when it was not.
//
// Follow-up: `confirmed: false` is reachable for more than one reason (a
// promoted seat needing its own promotion link, but also a signup that
// landed straight on the waitlist because its slot was full) — the backend
// always sends a `message` tailored to which one happened, so this page
// must render that verbatim rather than assuming/hardcoding promotion copy.

import React, { useState, useEffect } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api from "../../lib/api";
import { Button, Skeleton, ErrorState } from "../../components/ui";
import ManageSignupsPage from "./ManageSignupsPage";

// State machine: confirming | confirmed | not_confirmed | error
export default function ConfirmSignupPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token");
  const [state, setState] = useState("confirming");
  const [notConfirmedMessage, setNotConfirmedMessage] = useState("");

  useEffect(() => {
    if (!token) {
      setState("error");
      return;
    }
    api.public
      .confirmSignup(token)
      .then((result) => {
        if (result && result.confirmed === false) {
          // Generic fallback only — the backend sends a reason-specific
          // `message` for every zero-flip case (promotion_pending,
          // waitlisted, already_resolved, ...), so this must not assume any
          // one of them.
          setNotConfirmedMessage(
            result.message || "There's nothing to confirm for this link."
          );
          setState("not_confirmed");
        } else {
          setState("confirmed");
        }
      })
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
    // most common case; use it as the default. TTL matches
    // SIGNUP_CONFIRM_TTL (14 days) in magic_link_service.py.
    return (
      <ErrorState
        title="This link has expired"
        body="Magic links are good for 14 days. Open the event again and re-submit your signup to get a new one."
        action={
          <Button variant="primary" onClick={() => navigate("/volunteer")}>
            Back to events
          </Button>
        }
      />
    );
  }

  if (state === "not_confirmed") {
    // The token was legitimately consumed but scoped away from confirming
    // anything (promotion-pending seat, original batch link) — do not
    // render the success banner or the manage view for a seat that isn't
    // actually confirmed.
    return (
      <ErrorState
        title="Nothing to confirm"
        body={notConfirmedMessage}
        action={
          <Button variant="primary" onClick={() => navigate("/volunteer")}>
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
