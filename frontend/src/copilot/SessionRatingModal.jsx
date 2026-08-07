// Phase 35-01-E Task 18: 1-5 star session rating modal.
//
// Behaviour (per spec decisions §5 and resolved Q):
// - Opens when the drawer is being closed AND there has been at least
//   one assistant turn.
// - A comment is required when the value is 1 or 2 (low score). For 3+
//   the comment field is optional.
// - On submit the modal POSTs the rating, then invokes onSubmitted so
//   the caller can issue POST /sessions/{id}/close.
// - `fetcher` is an injectable hook for tests; defaults to window.fetch.
//
// K32 — the "no Skip button" decision is reversed, deliberately.
//
// The original spec said: no Skip, because response rate is a paper
// metric; the user must either submit a rating or click "Cancel close"
// to keep the drawer open. Both of those exits lead back into the app
// with the drawer still up. There was no way to close the copilot
// without rating it. Escape did nothing. And when the rating POST
// failed, `onSubmitted` was never called, so the one door that did lead
// out was locked by a server error the user could not do anything about.
//
// A survey you cannot decline is not a survey, and the response rate it
// produces is not a measurement — every reluctant user is either a
// coerced rating or someone who closed the browser tab. So there is now
// a "Close without rating" exit, always available, which also doubles as
// the way out of a failed submit. Submit stays the primary button and
// the modal still interrupts the close: the nudge remains, the trap is
// gone. Expect the response rate to drop; the number left is worth more.
import React from "react";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";
import useFocusTrap from "./useFocusTrap";

export default function SessionRatingModal({
  sessionId,
  open,
  onCancel,
  onDismiss,
  onSubmitted,
  fetcher,
}) {
  const f = fetcher || window.fetch.bind(window);
  const [value, setValue] = React.useState(0);
  const [comment, setComment] = React.useState("");
  const [submitting, setSubmitting] = React.useState(false);
  const [error, setError] = React.useState(null);
  const dialogRef = React.useRef(null);

  // Escape dismisses the topmost layer only, so it returns to the drawer
  // rather than closing everything: one Escape to back out of the rating,
  // a second on the drawer to leave. The early return lives below the
  // hooks because a conditional hook is not a hook.
  useFocusTrap(dialogRef, {
    active: !!open,
    onEscape: onCancel,
    restoreFocus: true,
  });

  if (!open) return null;
  const commentRequired = value > 0 && value <= 2;
  const canSubmit =
    value >= 1 && value <= 5 && (!commentRequired || comment.trim().length > 0);

  async function submit() {
    if (!canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const tok = authStorage.getToken();
      const resp = await f(`${COPILOT_BASE}/sessions/${sessionId}/rating`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({
          value,
          ...(comment.trim() ? { comment: comment.trim() } : {}),
        }),
      });
      if (!resp.ok && resp.status !== 201) {
        throw new Error(`HTTP ${resp.status}`);
      }
      onSubmitted?.();
    } catch (err) {
      setError(String(err));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      ref={dialogRef}
      role="dialog"
      aria-modal="true"
      aria-label="Rate this session"
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40"
    >
      <div className="bg-white rounded-lg shadow-lg p-6 w-[24rem]">
        <h3 className="font-semibold mb-2">How did this session go?</h3>
        <div
          className="flex gap-2 mb-3"
          role="radiogroup"
          aria-label="Star rating"
        >
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              type="button"
              role="radio"
              aria-checked={value === n}
              aria-label={`${n} star${n === 1 ? "" : "s"}`}
              onClick={() => setValue(n)}
              className={`w-10 h-10 rounded text-lg ${
                value >= n ? "bg-yellow-300" : "bg-gray-100"
              }`}
            >
              ★
            </button>
          ))}
        </div>
        {commentRequired && (
          <p className="text-xs text-red-600 mb-1">
            Comment required for 2 stars or fewer.
          </p>
        )}
        <textarea
          aria-label="Session rating comment"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder={
            commentRequired
              ? "Tell us what went wrong (required)"
              : "Optional comment"
          }
          className="w-full border rounded px-2 py-1 text-sm mb-3"
          rows={3}
          maxLength={1000}
        />
        {error && (
          <p role="alert" className="text-xs text-red-600 mb-2">
            {error} — your rating was not saved. You can retry, or close without
            rating.
          </p>
        )}
        <div className="flex items-center justify-between gap-2">
          {/* Never disabled, including mid-submit: a request that hangs is
              exactly when someone most needs the door to still open. */}
          <button
            type="button"
            onClick={onDismiss}
            className="text-xs text-gray-500 underline hover:text-gray-700"
          >
            Close without rating
          </button>
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onCancel}
              disabled={submitting}
              className="px-3 py-1 rounded border text-sm"
            >
              Cancel close
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit || submitting}
              className="px-3 py-1 rounded bg-indigo-600 text-white text-sm disabled:opacity-50"
            >
              Submit
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
