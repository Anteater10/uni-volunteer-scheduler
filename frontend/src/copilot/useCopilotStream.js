// Streaming hook for POST /api/v1/copilot/sessions/:id/messages.
//
// EventSource only speaks GET. The router expects a POST with a JSON
// body. We use fetch + ReadableStream and parse the SSE wire format
// ourselves: blank-line-delimited blocks of `event:` and `data:` lines.
//
// API shape:
//   const { send, streaming, error, partial } = useCopilotStream(sessionId, { onDone });
//   await send("hello"); // returns the persisted assistant message id
//
// Events emitted by the backend (see backend/app/copilot/router.py):
//   meta:  {"citations": [...], "retrieval_latency_ms": int, "rerank_latency_ms": int}
//          — Plan 32-06: emitted exactly once, before the first token. Strictly
//          additive — Phase 30 token/done/error parsing is unchanged.
//   token: JSON-encoded string chunk
//   done:  {"message_id": "<uuid>"}
//   error: {"error": "<class>", "message_id": "<uuid>"}
import { useCallback, useRef, useState } from "react";
import authStorage from "../lib/authStorage";
import { COPILOT_BASE } from "./api";

function parseSseChunk(buffer) {
  // Returns [events, remainingBuffer]. Each event = { event, data }.
  const events = [];
  let rest = buffer;
  while (true) {
    const sep = rest.indexOf("\n\n");
    if (sep === -1) break;
    const block = rest.slice(0, sep);
    rest = rest.slice(sep + 2);
    let eventName = "message";
    const dataLines = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      else if (line.startsWith("data:")) dataLines.push(line.slice(5).trimStart());
    }
    if (dataLines.length) events.push({ event: eventName, data: dataLines.join("\n") });
  }
  return [events, rest];
}

export function useCopilotStream(sessionId, { onDone, onError } = {}) {
  const [streaming, setStreaming] = useState(false);
  const [partial, setPartial] = useState("");
  const [error, setError] = useState(null);
  const [citations, setCitations] = useState([]);
  const [latencies, setLatencies] = useState({ retrieval: null, rerank: null });
  const abortRef = useRef(null);

  const send = useCallback(
    async (content) => {
      if (!sessionId) throw new Error("session not ready");
      setStreaming(true);
      setPartial("");
      setError(null);
      // Reset citations + latencies at the start of each turn — the latest
      // meta payload wins (RESEARCH §Pitfall 5).
      setCitations([]);
      setLatencies({ retrieval: null, rerank: null });

      const ac = new AbortController();
      abortRef.current = ac;

      let res;
      try {
        const tok = authStorage.getToken();
        res = await fetch(`${COPILOT_BASE}/sessions/${sessionId}/messages`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Accept: "text/event-stream",
            ...(tok ? { Authorization: `Bearer ${tok}` } : {}),
          },
          body: JSON.stringify({ content }),
          signal: ac.signal,
        });
      } catch (err) {
        setStreaming(false);
        setError(err);
        onError?.(err);
        throw err;
      }

      if (!res.ok || !res.body) {
        const err = new Error(`HTTP ${res?.status ?? "?"}`);
        err.status = res?.status;
        setStreaming(false);
        setError(err);
        onError?.(err);
        throw err;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assembled = "";
      let messageId = null;
      let streamError = null;

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let events;
          [events, buffer] = parseSseChunk(buffer);
          for (const ev of events) {
            if (ev.event === "meta") {
              // Plan 32-06: citations + retrieval/rerank latencies arrive
              // exactly once, before the first token. Strictly additive — the
              // Phase 30 invariant (token/done/error untouched) is preserved.
              try {
                const meta = JSON.parse(ev.data);
                setCitations(Array.isArray(meta.citations) ? meta.citations : []);
                setLatencies({
                  retrieval: meta.retrieval_latency_ms ?? null,
                  rerank: meta.rerank_latency_ms ?? null,
                });
              } catch {
                // malformed meta — ignore so the stream continues
              }
            } else if (ev.event === "token") {
              try {
                const chunk = JSON.parse(ev.data);
                assembled += chunk;
                setPartial(assembled);
              } catch {
                // malformed token chunk — skip
              }
            } else if (ev.event === "done") {
              try {
                messageId = JSON.parse(ev.data).message_id;
              } catch {
                // ignore
              }
            } else if (ev.event === "error") {
              try {
                const body = JSON.parse(ev.data);
                streamError = new Error(body.error || "stream_error");
                messageId = body.message_id || null;
              } catch {
                streamError = new Error("stream_error");
              }
            }
          }
        }
      } catch (err) {
        streamError = err;
      } finally {
        setStreaming(false);
        abortRef.current = null;
      }

      if (streamError) {
        setError(streamError);
        onError?.(streamError, { messageId, text: assembled });
        return { messageId, text: assembled, error: streamError };
      }

      onDone?.({ messageId, text: assembled });
      return { messageId, text: assembled, error: null };
    },
    [sessionId, onDone, onError],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { send, cancel, streaming, partial, error, citations, latencies };
}

export default useCopilotStream;
export { parseSseChunk };
