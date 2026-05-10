// Right-hand chat drawer. Opens a session lazily on first mount so a
// user who never opens the FAB never produces telemetry.
import React, { useEffect, useRef, useState } from "react";
import { X, Send, Loader2 } from "lucide-react";
import copilotApi from "./api";
import useCopilotStream from "./useCopilotStream";

export default function CopilotDrawer({ open, onClose }) {
  const [sessionId, setSessionId] = useState(null);
  const [messages, setMessages] = useState([]); // [{role, content}]
  const [input, setInput] = useState("");
  const [bootError, setBootError] = useState(null);
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
    onDone: ({ text }) => {
      setMessages((m) => [...m, { role: "assistant", content: text }]);
    },
    onError: (_err, info) => {
      if (info?.text) {
        setMessages((m) => [...m, { role: "assistant", content: info.text }]);
      }
    },
  });

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
            <MessageBubble key={i} role={m.role} content={m.content} />
          ))}
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
