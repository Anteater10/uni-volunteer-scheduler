# Server-Sent Events for LLM Streaming

> _Stub — to be filled in alongside the SSE endpoint implementation._

## Why this matters

LLMs generate text one token at a time. If the server waits for the
complete response before replying, the user stares at a spinner for 4–10
seconds. If the server streams tokens as they arrive, the UI starts
moving in 200–400ms and the perceived latency drops dramatically. The
absolute latency is unchanged — only the user's experience changes —
but for chat UIs that experience is everything.

## The intuition (to expand)

- TCP delivers bytes in order, but HTTP traditionally bundles them into
  one response. Streaming says: keep the connection open, flush bytes as
  the server has them, let the client read incrementally.
- SSE is just HTTP with `Content-Type: text/event-stream` and a parsing
  convention (`data: ...\n\n`). No special protocol, no handshake. Plain
  text over plain HTTP. The browser hands you `EventSource` to consume
  it.

## The mechanism (to expand)

- Server holds the connection, writes lines like `data: hello\n\n`,
  optionally `event: name\n` and `id: 42\n` for resumable streams.
- Client opens `new EventSource(url)` and listens. Browser auto-reconnects
  on disconnect (with the `Last-Event-ID` if you sent IDs).

## Why we chose it here (to expand)

- Streaming token-by-token is essential UX.
- One-way server→client only — we don't need bidirectional, so WebSocket
  is overkill. SSE wins on simplicity, proxy compatibility, and free
  reconnect semantics.

## What to read next

- HTML Living Standard, "Server-sent events" section.
- Anthropic + OpenAI streaming API references.
