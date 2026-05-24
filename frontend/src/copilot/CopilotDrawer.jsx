// Right-hand chat drawer. Opens a session lazily on first mount so a
// user who never opens the FAB never produces telemetry.
import React, { useEffect, useRef, useState } from "react";
import { X, Send, Loader2 } from "lucide-react";
import copilotApi from "./api";
import useCopilotStream from "./useCopilotStream";
import CitationChip from "./CitationChip";
import CitationPanel from "./CitationPanel";
import ConfirmationCard from "./ConfirmationCard";
import ToolCallIndicator from "./ToolCallIndicator";

const MAX_CHIPS = 5; // RESEARCH §Open Q #2 — show top-5, horizontal scroll if narrow

export default function CopilotDrawer({ open, onClose }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]); // [{role, content, citations?}]
  const [input, setInput] = useState("");
  const [bootError, setBootError] = useState(null);
  const [activeCitation, setActiveCitation] = useState(null);
  // Active tool calls keyed by call_id; flipped to status: 'done' when
  // the matching tool_result arrives, removed at turn end.
  const [toolCalls, setToolCalls] = useState({}); // { [call_id]: { tool, status } }
  // Outstanding confirmation cards keyed by call_id.
  const [pendingConfirmations, setPendingConfirmations] = useState({});
  // Tracks which confirmation buttons are currently posting.
  const [confirmInFlight, setConfirmInFlight] = useState({});
  const [confirmError, setConfirmError] = useState(null);
  const scrollRef = useRef(null);

  // Lazy session creation when the drawer first opens.
  useEffect(() => {
    if (!open || sessionId) return;
    let cancelled = false;
    (async () => {
      try {
        const sess = await copilotApi.createSession();
        if (cancelled) return;
        setSessionId(sess.id);
      } catch (err) {
        if (!cancelled) setBootError(err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, sessionId]);

  const { send, streaming, partial, error } = useCopilotStream(sessionId, {
    onDone: ({ text, citations }) => {
      // Snapshot citations at the moment the turn completes so each assistant
      // bubble carries its own citation set (later turns won't overwrite).
      // Only push an assistant bubble when there's actual text — otherwise
      // a confirmation-paused turn would surface an empty bubble.
      if (text) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: text, citations: citations || [] },
        ]);
      }
    },
    onError: (_err, info) => {
      if (info?.text) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: info.text, citations: info.citations || [] },
        ]);
      }
    },
    onToolCall: ({ call_id, tool }) => {
      setToolCalls((cs) => ({ ...cs, [call_id]: { tool, status: "running" } }));
    },
    onToolResult: ({ call_id }) => {
      setToolCalls((cs) => {
        if (!cs[call_id]) return cs;
        return { ...cs, [call_id]: { ...cs[call_id], status: "done" } };
      });
    },
    onConfirmationRequest: ({ call_id, tool, args, preview }) => {
      setPendingConfirmations((p) => ({
        ...p,
        [call_id]: { tool, args, preview },
      }));
    },
  });

  async function decide(callId, approved) {
    setConfirmInFlight((m) => ({ ...m, [callId]: true }));
    setConfirmError(null);
    try {
      await copilotApi.confirmCall(callId, approved);
      setPendingConfirmations((p) => {
        const next = { ...p };
        delete next[callId];
        return next;
      });
    } catch (err) {
      setConfirmError(err);
    } finally {
      setConfirmInFlight((m) => {
        const next = { ...m };
        delete next[callId];
        return next;
      });
    }
  }

  // Auto-scroll on new content.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, partial]);

  async function onSubmit(e) {
    e.preventDefault();
    const content = input.trim();
    if (!content || streaming || !sessionId) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content }]);
    setToolCalls({});
    setConfirmError(null);
    try {
      await send(content);
    } catch {
      // hook already records error state
    }
  }

  if (!open) return null;

  return (
    <>
      <div
        className="fixed inset-0 bg-black/30 z-40"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside
        role="dialog"
        aria-label="SciTrek Copilot"
        className="fixed right-0 top-0 bottom-0 w-full sm:w-[28rem] bg-white shadow-xl z-50 flex flex-col"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b">
          <div>
            <h2 className="font-semibold">SciTrek Copilot</h2>
            <p className="text-xs text-gray-500">Beta — no live data access yet.</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close copilot"
            className="p-2 rounded hover:bg-gray-100"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {bootError && (
            <p className="text-sm text-red-600">
              Could not start a copilot session: {bootError.message}
            </p>
          )}
          {!bootError && !sessionId && (
            <p className="text-sm text-gray-500 flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Starting session…
            </p>
          )}
          {messages.map((m, i) => (
            <React.Fragment key={i}>
              <MessageBubble role={m.role} content={m.content} />
              {m.role === "assistant" &&
                Array.isArray(m.citations) &&
                m.citations.length > 0 && (
                  <div
                    role="list"
                    aria-label="Sources consulted"
                    className="flex gap-2 overflow-x-auto mt-1 mb-1 pb-1"
                  >
                    {m.citations.slice(0, MAX_CHIPS).map((c, idx) => (
                      <CitationChip
                        key={c.chunk_id || idx}
                        index={idx + 1}
                        citation={c}
                        onClick={() => setActiveCitation(c.chunk_id)}
                      />
                    ))}
                  </div>
                )}
            </React.Fragment>
          ))}
          {Object.entries(toolCalls).map(([cid, info]) => (
            <ToolCallIndicator key={cid} tool={info.tool} status={info.status} />
          ))}
          {Object.entries(pendingConfirmations).map(([cid, info]) => (
            <ConfirmationCard
              key={cid}
              tool={info.tool}
              args={info.args}
              preview={info.preview}
              disabled={!!confirmInFlight[cid]}
              onApprove={() => decide(cid, true)}
              onReject={() => decide(cid, false)}
            />
          ))}
          {confirmError && (
            <p className="text-sm text-red-600">
              Confirmation failed: {confirmError.message}
            </p>
          )}
          {streaming && partial && (
            <MessageBubble role="assistant" content={partial} streaming />
          )}
          {error && !streaming && (
            <p className="text-sm text-red-600">Stream failed: {error.message}</p>
          )}
        </div>

        <form onSubmit={onSubmit} className="border-t p-3 flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask the copilot…"
            disabled={!sessionId || streaming}
            aria-label="Message"
            className="flex-1 border rounded px-3 py-2 text-sm focus:outline-none focus:ring focus:ring-indigo-200"
            maxLength={4000}
          />
          <button
            type="submit"
            disabled={!sessionId || streaming || !input.trim()}
            aria-label="Send message"
            className="px-3 py-2 rounded bg-indigo-600 text-white text-sm disabled:opacity-50 flex items-center gap-1"
          >
            {streaming ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
          </button>
        </form>
      </aside>
      {activeCitation && (
        <CitationPanel
          chunkId={activeCitation}
          onClose={() => setActiveCitation(null)}
        />
      )}
    </>
  );
}

function MessageBubble({ role, content, streaming = false }) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded px-3 py-2 text-sm whitespace-pre-wrap ${
          isUser ? "bg-indigo-600 text-white" : "bg-gray-100 text-gray-900"
        }`}
      >
        {content}
        {streaming && <span className="ml-1 animate-pulse">▋</span>}
      </div>
    </div>
  );
}
