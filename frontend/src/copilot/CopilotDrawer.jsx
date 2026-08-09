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
import MessageRatingButtons from "./MessageRatingButtons";
import MarkdownMessage from "./MarkdownMessage";
import SessionRatingModal from "./SessionRatingModal";
import useFocusTrap from "./useFocusTrap";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";

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
  // Phase 35-01-E Task 18: rating modal intercepts the drawer close path.
  const [ratingOpen, setRatingOpen] = useState(false);
  const scrollRef = useRef(null);
  const asideRef = useRef(null);

  // Drawer close intercept (Phase 35-01-E Task 18). If at least one
  // assistant turn has happened in this session, open the rating modal
  // instead of closing immediately. The modal's "Cancel close" button
  // calls back into `setRatingOpen(false)`; "Submit" calls
  // `closeAndDismiss()` which posts to /sessions/{id}/close and then
  // invokes the original `onClose` callback to actually dismiss the drawer.
  function requestClose() {
    const hasAssistant = messages.some((m) => m.role === "assistant");
    if (hasAssistant && sessionId) {
      setRatingOpen(true);
      return;
    }
    void closeAndDismiss();
  }

  async function closeAndDismiss() {
    setRatingOpen(false);
    if (sessionId) {
      try {
        const tok = authStorage.getToken();
        await fetch(`${COPILOT_BASE}/sessions/${sessionId}/close`, {
          method: "POST",
          credentials: "include",
          headers: tok ? { Authorization: `Bearer ${tok}` } : {},
        });
      } catch {
        // best-effort close — surface drawer dismissal regardless
      }
    }
    onClose?.();
  }

  // K32. Focus restore is keyed on `open` rather than left to the trap:
  // the trap deactivates every time the rating modal opens, and restoring
  // focus to the FAB at that moment would fling the user out of the dialog
  // they just opened. It has to be declared ABOVE useFocusTrap — effects
  // run in declaration order, and the trap moves focus into the drawer on
  // activation, so capturing later would record the drawer's own close
  // button as the thing to go back to.
  useEffect(() => {
    if (!open) return undefined;
    const opener = document.activeElement;
    return () => {
      if (opener && document.contains(opener) && opener.focus) opener.focus();
    };
  }, [open]);

  // The drawer announced itself as a dialog and then behaved like a div:
  // Tab walked out into the page behind it and Escape did nothing. The
  // trap stands down while an inner layer is up — the rating modal runs
  // its own, and the citation panel renders outside this <aside>, so
  // trapping through it would make its own close button unreachable.
  useFocusTrap(asideRef, {
    active: open && !ratingOpen && !activeCitation,
    onEscape: requestClose,
  });

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
    onDone: ({ id, text, citations }) => {
      // Snapshot citations at the moment the turn completes so each assistant
      // bubble carries its own citation set (later turns won't overwrite).
      // Only push an assistant bubble when there's actual text — otherwise
      // a confirmation-paused turn would surface an empty bubble.
      // Phase 35-01-D Task 15: `id` arrives via `event: message_persisted`
      // so the bubble carries a stable `data-message-id` for rating UI
      // (which ships in 35-01-E).
      if (text) {
        setMessages((m) => [
          ...m,
          {
            id: id || null,
            role: "assistant",
            content: text,
            citations: citations || [],
          },
        ]);
      }
    },
    onError: (_err, info) => {
      if (info?.text) {
        setMessages((m) => [
          ...m,
          {
            id: info?.id || null,
            role: "assistant",
            content: info.text,
            citations: info.citations || [],
          },
        ]);
      }
    },
    onToolCall: ({ call_id, tool }) => {
      setToolCalls((cs) => ({ ...cs, [call_id]: { tool, status: "running" } }));
    },
    onToolResult: ({ call_id, error }) => {
      // K28: a failed call is still a result — the model gets the error back
      // and retries. Don't label it "ran"; the indicator has had a "failed"
      // state all along and nothing was ever sending it.
      setToolCalls((cs) => {
        if (!cs[call_id]) return cs;
        return {
          ...cs,
          [call_id]: { ...cs[call_id], status: error ? "error" : "done" },
        };
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
      const outcome = await copilotApi.confirmCall(callId, approved);
      setPendingConfirmations((p) => {
        const next = { ...p };
        delete next[callId];
        return next;
      });
      // K25: this response used to be discarded, so approving an action
      // deleted the card and said nothing at all — the user had no way to
      // tell whether 47 emails had gone out or nothing had happened. The
      // server now closes out the paused turn and hands back the assistant's
      // reply; show it as an ordinary bubble.
      if (approved && outcome?.message?.content) {
        setMessages((m) => [
          ...m,
          {
            id: outcome.message.id,
            role: "assistant",
            content: outcome.message.content,
            citations: [],
          },
        ]);
      } else if (approved) {
        // The write landed and is audited, but the model could not be
        // reached to describe it. Silence would read as "nothing happened".
        setMessages((m) => [
          ...m,
          {
            role: "assistant",
            content: "Done — that action has been carried out.",
            citations: [],
          },
        ]);
      }
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
        onClick={requestClose}
        aria-hidden="true"
      />
      {/* Width: 28rem was set when replies were a sentence or two. A
          capability list or a roster table wraps every line at that width,
          which is what makes a long answer unreadable. Grow with the
          viewport and stop at 44rem — past that the measure gets too long
          to scan, and the page behind the drawer stops being visible
          enough to work alongside. */}
      <aside
        ref={asideRef}
        role="dialog"
        aria-modal="true"
        aria-label="SciTrek Copilot"
        className="fixed right-0 top-0 bottom-0 w-full sm:w-[32rem] lg:w-[38rem] xl:w-[44rem] bg-white shadow-xl z-50 flex flex-col"
      >
        <header className="flex items-center justify-between px-4 py-3 border-b">
          <div>
            <h2 className="font-semibold">SciTrek Copilot</h2>
            {/* This line has now been wrong twice by outliving the build.
                It said "no live data access yet" until grounded retrieval
                shipped, then "can't see live rosters or signups" until the
                agent loop was turned on (2026-08-07) and it could. It reads
                live data and proposes changes you approve first — the
                approval step is the part worth saying out loud, because it
                is what makes asking it to move someone safe. */}
            <p className="text-xs text-gray-500">
              Answers from the SciTrek knowledge base and live rosters, with
              sources. Any change it makes waits for your approval.
            </p>
          </div>
          <button
            type="button"
            onClick={requestClose}
            aria-label="Close copilot"
            className="p-2 rounded hover:bg-gray-100"
          >
            <X className="w-5 h-5" />
          </button>
        </header>

        <div
          ref={scrollRef}
          className="flex-1 overflow-y-auto px-4 py-3 space-y-3"
        >
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
              <MessageBubble
                role={m.role}
                content={m.content}
                messageId={m.id}
              />
              {m.role === "assistant" && m.id && (
                <MessageRatingButtons messageId={m.id} />
              )}
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
            <ToolCallIndicator
              key={cid}
              tool={info.tool}
              status={info.status}
            />
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
            <p className="text-sm text-red-600">
              Stream failed: {error.message}
            </p>
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
      {sessionId && (
        <SessionRatingModal
          sessionId={sessionId}
          open={ratingOpen}
          onCancel={() => setRatingOpen(false)}
          onDismiss={closeAndDismiss}
          onSubmitted={closeAndDismiss}
        />
      )}
    </>
  );
}

function MessageBubble({ role, content, messageId = null, streaming = false }) {
  const isUser = role === "user";
  // Phase 35-01-D Task 15: stamp the persisted assistant message id onto
  // the bubble so the rating UI (35-01-E) can target it directly. User
  // bubbles never carry an id — only the assistant's `copilot_messages`
  // row is rate-able.
  const stamp = !isUser && messageId ? { "data-message-id": messageId } : {};
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        {...stamp}
        className={`max-w-[85%] rounded-lg px-3.5 py-2.5 text-[0.9375rem] leading-relaxed ${
          isUser
            ? "bg-indigo-600 text-white whitespace-pre-wrap"
            : "bg-gray-100 text-gray-900"
        }`}
      >
        {/* Only the assistant's text is parsed as Markdown. A user who
            types `**` or starts a line with `-` means those characters,
            and reinterpreting their message as formatting would quietly
            change what they said. */}
        {isUser ? content : <MarkdownMessage>{content}</MarkdownMessage>}
        {streaming && <span className="ml-1 animate-pulse">▋</span>}
      </div>
    </div>
  );
}
