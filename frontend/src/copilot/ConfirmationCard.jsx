// Inline card that prompts the operator to confirm or reject a parked
// write tool call surfaced by the copilot agent loop. The drawer renders
// one of these for every ``confirmation_request`` SSE event; Approve /
// Reject buttons POST the decision to /api/v1/copilot/confirm/{call_id}.
import React from "react";

export default function ConfirmationCard({
  tool,
  args,
  preview,
  onApprove,
  onReject,
  disabled = false,
}) {
  return (
    <div
      className="rounded-md border border-amber-300 bg-amber-50 p-3 my-2"
      role="group"
      aria-label={`Confirm action ${tool}`}
    >
      <div className="text-sm font-medium text-amber-900">
        Confirm action: <code>{tool}</code>
      </div>
      <pre className="text-xs my-2 bg-white p-2 rounded overflow-x-auto">
        {JSON.stringify(args, null, 2)}
      </pre>
      {preview && <p className="text-sm text-amber-900">{preview}</p>}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={onApprove}
          disabled={disabled}
          className="px-3 py-1 rounded bg-emerald-600 text-white text-sm disabled:opacity-50"
        >
          Confirm
        </button>
        <button
          type="button"
          onClick={onReject}
          disabled={disabled}
          className="px-3 py-1 rounded bg-zinc-300 text-zinc-800 text-sm disabled:opacity-50"
        >
          Reject
        </button>
      </div>
    </div>
  );
}
