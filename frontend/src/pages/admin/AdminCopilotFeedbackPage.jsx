// Phase 35-01-E Task 19: admin page surfacing copilot human-feedback aggregates.
//
// Two sections:
//   1. Weekly aggregates table (ISO week, thumbs-up rate, session rating avg,
//      message + session counts) — fed by GET /copilot/admin/feedback/weekly.
//   2. Bottom-quartile messages drill-down — fed by GET
//      /copilot/admin/feedback/bottom-messages. Each item expands to show the
//      prior user turn and assistant reply for triage.
//
// `fetcher` is an injectable hook for tests; defaults to window.fetch. The page
// keeps its own loading and error state and does not pull in tanstack/query
// because the admin feedback view is a leaf and we want to mirror the
// MessageRatingButtons / SessionRatingModal fetcher-injection pattern shipped
// in Tasks 17 + 18.
import React from "react";
import authStorage from "../../lib/authStorage";
import { COPILOT_BASE } from "../../copilot/api";
import { useAdminPageTitle } from "./AdminLayout";

export default function AdminCopilotFeedbackPage({ fetcher }) {
  const f = fetcher || window.fetch.bind(window);
  useAdminPageTitle("Copilot feedback");
  const [weekly, setWeekly] = React.useState(null);
  const [bottom, setBottom] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [expanded, setExpanded] = React.useState(null);

  React.useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const tok = authStorage.getToken();
        const headers = tok ? { Authorization: `Bearer ${tok}` } : {};
        const [w, b] = await Promise.all([
          f(`${COPILOT_BASE}/admin/feedback/weekly`, {
            headers,
            credentials: "include",
          }),
          f(`${COPILOT_BASE}/admin/feedback/bottom-messages`, {
            headers,
            credentials: "include",
          }),
        ]);
        if (!w.ok) throw new Error(`weekly HTTP ${w.status}`);
        if (!b.ok) throw new Error(`bottom HTTP ${b.status}`);
        const wj = await w.json();
        const bj = await b.json();
        if (!cancelled) {
          setWeekly(wj.weeks || []);
          setBottom(bj.messages || []);
        }
      } catch (err) {
        if (!cancelled) setError(String(err));
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [f]);

  if (error) {
    return (
      <p role="alert" className="text-sm text-red-600">
        {error}
      </p>
    );
  }
  if (weekly === null || bottom === null) {
    return <p className="text-sm text-gray-500">Loading…</p>;
  }

  return (
    <div className="space-y-6">
      <section>
        <h2 className="font-semibold mb-2">Weekly feedback</h2>
        {weekly.length === 0 ? (
          <p className="text-sm text-gray-500">No ratings recorded yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm" data-testid="weekly-table">
              <thead className="text-left text-xs uppercase text-gray-500">
                <tr>
                  <th className="py-2 pr-4">ISO week</th>
                  <th className="py-2 pr-4">Thumbs-up rate</th>
                  <th className="py-2 pr-4">Avg session rating</th>
                  <th className="py-2 pr-4">Messages rated</th>
                  <th className="py-2 pr-4">Sessions rated</th>
                </tr>
              </thead>
              <tbody>
                {weekly.map((w) => (
                  <tr key={w.iso_week} className="border-t border-gray-100">
                    <td className="py-2 pr-4 font-mono">{w.iso_week}</td>
                    <td className="py-2 pr-4">
                      {w.thumbs_up_rate == null
                        ? "—"
                        : `${Math.round(w.thumbs_up_rate * 100)}%`}
                    </td>
                    <td className="py-2 pr-4">
                      {w.session_rating_avg == null
                        ? "—"
                        : w.session_rating_avg.toFixed(2)}
                    </td>
                    <td className="py-2 pr-4">{w.n_messages}</td>
                    <td className="py-2 pr-4">{w.n_sessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2 className="font-semibold mb-2">Bottom-quartile messages</h2>
        {bottom.length === 0 ? (
          <p className="text-sm text-gray-500">No thumbs-down ratings yet.</p>
        ) : (
          <ul className="space-y-2">
            {bottom.map((m) => (
              <li
                key={m.message_id}
                className="border rounded p-2"
                data-testid="bottom-message"
              >
                <button
                  type="button"
                  onClick={() =>
                    setExpanded(expanded === m.message_id ? null : m.message_id)
                  }
                  aria-expanded={expanded === m.message_id}
                  className="text-left text-sm w-full"
                >
                  <div className="font-mono text-xs text-gray-500">
                    {new Date(m.rated_at).toLocaleString()} — {m.rater_role} —
                    model: {m.model_id || "?"}
                  </div>
                  <div className="text-sm italic">"{m.comment}"</div>
                </button>
                {expanded === m.message_id && (
                  <div className="mt-2 text-xs space-y-1">
                    {m.prior_user_text && (
                      <div>
                        <strong>Prior user turn:</strong> {m.prior_user_text}
                      </div>
                    )}
                    <div>
                      <strong>Assistant reply:</strong> {m.assistant_text}
                    </div>
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
