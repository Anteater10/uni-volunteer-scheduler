# Server-Sent Events for LLM Streaming

## Why this matters

LLMs generate text one token at a time. A 200-word answer takes a model
4–10 seconds to produce end-to-end. If we wait for the full response
before replying to the browser, the user stares at a spinner the entire
time. If we stream tokens out as they arrive, the user sees the first
word in 200–400ms and reads along while the rest is generated. The total
latency is identical — the model still takes 4–10 seconds — but the
**perceived** latency drops by an order of magnitude. For a chat UI,
perceived latency *is* the product.

## The intuition

HTTP usually works in turns: the client asks, the server thinks, the
server replies, the connection closes. That model breaks for streaming
because we want bytes flowing while the server is still thinking.

Three protocols give us bytes-as-they-arrive over the web:

1. **Long polling** — client opens a request, server holds it, replies,
   client immediately reopens. Cheap to add, but ugly: every chunk costs
   a fresh request, and the boundary between chunks is artificial.
2. **WebSocket** — the connection is upgraded from HTTP to a
   bidirectional binary frame protocol. Powerful, but heavyweight: it
   needs an `Upgrade` handshake, a different framing scheme, and many
   corporate proxies refuse the upgrade.
3. **Server-Sent Events (SSE)** — the server keeps the connection open,
   sets `Content-Type: text/event-stream`, and writes UTF-8 lines as
   it has them. The client consumes them with the browser-native
   `EventSource` (or, in our case, `fetch` + `ReadableStream`).

SSE is the smallest possible viable design. It is "HTTP, but the server
keeps writing." That smallness is the point.

## The mechanism

The wire format is dead simple. Each event is a block of lines
terminated by a blank line:

```
event: token
data: Hello

event: token
data:  world

event: done
data: {"message_id": "abc..."}

```

- `event:` names the event type. The default is `message`.
- `data:` is the payload. Multiple `data:` lines concatenate with
  newlines. We send one `data:` line per event with a JSON-encoded
  string so newlines and Unicode survive intact.
- The blank line terminates the event. **Two newlines, always.** Forget
  the second `\n` and the browser holds onto the chunk forever waiting
  for it.

The client opens a long-running GET (or in our case POST, via `fetch`)
and parses events as they arrive. If the connection drops,
`EventSource` will reconnect automatically and send a `Last-Event-ID`
header. That gives us free reconnect semantics — if we want them.

## The mechanism, in our codebase

`backend/app/copilot/router.py` defines:

```python
def _sse_format(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")
```

That four-line function is the entire wire protocol. The endpoint
returns a `StreamingResponse(_sse_stream(...), media_type="text/event-stream")`
and the generator yields these bytes as the OpenRouter SDK feeds them.

We use three event names:

- `token` — one chunk of assistant text. Body is a JSON-encoded string
  (so quotes/newlines survive the line-oriented format).
- `done` — terminal success. Body is `{"message_id": "<uuid>"}`. The
  client uses the message id to navigate to the persisted row if it
  wants to.
- `error` — terminal failure. Body is `{"error": "<exception class>", "message_id": "<uuid>"}`.
  We persist the error row first so the message id is always real.

Crucially, the assistant row is written to `copilot_messages` **inside
the generator**, after streaming finishes. Streaming and persistence
are entangled on purpose: the same code path that builds the user-visible
text also writes the row that ends up in our research dataset.

## Why we chose SSE over WebSocket here

| Constraint | SSE | WebSocket |
|---|---|---|
| One direction (server → client during a turn) | natural fit | overkill |
| Auto-reconnect | free | hand-rolled |
| Corporate proxy compatibility | plain HTTP, always works | Upgrade handshake often blocked |
| Browser API | `EventSource` (built-in) | `WebSocket` (built-in) |
| Backend complexity | one generator function | a separate connection lifecycle |
| Framing | text lines, easy to debug with curl | binary, harder to inspect |

For a single-turn LLM stream we don't need the client to push back
during generation. SSE wins on every axis except request body size — a
GET-only quirk we sidestep by returning the SSE response from a `POST`,
which `EventSource` doesn't support but `fetch` + a streaming reader
does. The frontend hook (`useCopilotStream`) does exactly that.

## What to read next

- [HTML Living Standard, "Server-sent events"](https://html.spec.whatwg.org/multipage/server-sent-events.html) — the actual spec. Short.
- [MDN: Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events) — practical examples.
- [OpenAI streaming reference](https://platform.openai.com/docs/api-reference/streaming) — what the upstream stream looks like before we re-emit it.
