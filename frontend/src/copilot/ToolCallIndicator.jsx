// Tiny inline indicator shown while a tool call is in flight. The
// drawer renders one of these per ``tool_call`` SSE event and removes it
// when the matching ``tool_result`` arrives (or when the turn ends).
import React from "react";
import { Loader2 } from "lucide-react";

export default function ToolCallIndicator({ tool, status = "running" }) {
  const label =
    status === "done"
      ? `ran ${tool}`
      : status === "error"
        ? `failed ${tool}`
        : `calling ${tool}…`;
  return (
    <div
      className="flex items-center gap-2 text-xs text-zinc-600 my-1"
      role="status"
      aria-label={label}
    >
      {status === "running" && (
        <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
      )}
      <span>{label}</span>
    </div>
  );
}
