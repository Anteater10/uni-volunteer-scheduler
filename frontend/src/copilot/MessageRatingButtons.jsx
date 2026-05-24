// Phase 35-01-E Task 17: per-message thumbs up/down rating buttons.
//
// Behaviour (per spec decisions §4 and resolved Q):
// - Thumbs-up persists immediately on click — no confirmation step.
// - Thumbs-down opens an inline textarea; submission requires a non-empty
//   comment. The POST only fires when the user clicks "Submit".
// - Ratings are mutable on the server: clicking the opposite rating
//   overwrites the prior one (the endpoint upserts by message_id+rater).
// - Renders nothing when `messageId` is null/undefined — the persisted
//   id only arrives after the SSE `message_persisted` event (35-01-D).
//
// `fetcher` is an injectable hook for tests; defaults to window.fetch.
import React from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";

export default function MessageRatingButtons({ messageId, fetcher }) {
  const f = fetcher || window.fetch.bind(window);
  const [state, setState] = React.useState({
    active: null, // 'up' | 'down' | null
    showComment: false,
    comment: "",
    submitting: false,
    error: null,
  });

  if (!messageId) return null;

  async function submit(value, comment) {
    setState((s) => ({ ...s, submitting: true, error: null }));
    try {
      const tok = authStorage.getToken();
      const resp = await f(`${COPILOT_BASE}/messages/${messageId}/rating`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify({ value, ...(comment ? { comment } : {}) }),
      });
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      setState({
        active: value,
        showComment: false,
        comment: "",
        submitting: false,
        error: null,
      });
    } catch (err) {
      setState((s) => ({ ...s, submitting: false, error: String(err) }));
    }
  }

  function onUp() {
    submit("up", null);
  }

  function onDown() {
    // Clearing `active` keeps both buttons un-pressed until the comment
    // is submitted — the prior rating (if any) is only overwritten on
    // successful POST, matching the server's upsert semantics.
    setState((s) => ({ ...s, showComment: true, active: null }));
  }

  function onSubmitDown() {
    if (!state.comment.trim()) return;
    submit("down", state.comment.trim());
  }

  return (
    <div className="flex flex-col gap-1 mt-1 pl-1">
      <div className="flex gap-2">
        <button
          type="button"
          aria-label="Thumbs up"
          aria-pressed={state.active === "up"}
          onClick={onUp}
          disabled={state.submitting}
          className={`p-1 rounded ${state.active === "up" ? "bg-green-100" : "hover:bg-gray-100"}`}
        >
          <ThumbsUp className="w-4 h-4" />
        </button>
        <button
          type="button"
          aria-label="Thumbs down"
          aria-pressed={state.active === "down"}
          onClick={onDown}
          disabled={state.submitting}
          className={`p-1 rounded ${state.active === "down" ? "bg-red-100" : "hover:bg-gray-100"}`}
        >
          <ThumbsDown className="w-4 h-4" />
        </button>
      </div>
      {state.showComment && (
        <div className="flex flex-col gap-1 mt-1">
          <textarea
            aria-label="Comment for thumbs-down rating"
            value={state.comment}
            onChange={(e) =>
              setState((s) => ({ ...s, comment: e.target.value }))
            }
            placeholder="Tell us what went wrong (required)"
            className="border rounded px-2 py-1 text-xs"
            rows={2}
            maxLength={1000}
          />
          <button
            type="button"
            onClick={onSubmitDown}
            disabled={!state.comment.trim() || state.submitting}
            className="self-end px-2 py-1 rounded bg-indigo-600 text-white text-xs disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      )}
      {state.error && (
        <p role="alert" className="text-xs text-red-600">
          {state.error}
        </p>
      )}
    </div>
  );
}
