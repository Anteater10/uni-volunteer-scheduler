# Server-Sent Events for Streaming LLM Responses

## Summary

Phase 30 streams assistant tokens to the client over Server-Sent Events
(SSE). SSE is a unidirectional server-to-client protocol layered over
HTTP, defined in the HTML Living Standard [HTML LS, §9.2]. We adopt
SSE rather than WebSocket on the basis of three constraints: (1) token
streaming is inherently unidirectional within a single conversational
turn; (2) SSE traverses corporate HTTP proxies without an `Upgrade`
handshake; and (3) the format is line-oriented UTF-8, allowing
inspection with standard tools (`curl -N`) and trivial generation from
a Python generator.

## Endpoint specification

- Method: `POST /api/v1/copilot/sessions/{session_id}/messages`
- Authentication: bearer token; role must be `admin` or `organizer`
- Feature flag: `COPILOT_ENABLED=true` (router returns 404 otherwise)
- Request body: `{ "content": "<user message>" }` (1–4000 chars)
- Response status: 200 on stream open
- Response headers: `Content-Type: text/event-stream`
- Response body: a sequence of SSE events terminated by either a `done`
  or an `error` event

The user message is persisted to `copilot_messages` *before* the stream
opens, so a stream that crashes mid-flight does not lose the user's
input.

## Event types

| Event | Body | Meaning |
|---|---|---|
| `token` | JSON-encoded string | One chunk of assistant text |
| `done` | `{"message_id": "<uuid>"}` | Terminal success; assistant row persisted |
| `error` | `{"error": "<class>", "message_id": "<uuid>"}` | Terminal failure; row persisted with `error` populated |

The wire format follows HTML LS §9.2: each event is a sequence of
`field: value\n` lines terminated by a single blank line. The server
emits exactly one `event:` and one `data:` line per event, both
required for compatibility with the EventSource specification.

## Persistence semantics

The assistant row is written to `copilot_messages` inside the streaming
generator, after all upstream tokens have been consumed (or an
exception has been caught). The row records:

- accumulated `content`
- `latency_ms`, `prompt_tokens`, `completion_tokens` (from the upstream
  usage chunk)
- `model_id` (the model that actually answered, post-fallback)
- `prompt_hash` (SHA-256 of the full chat history sent to the model)
- `response_hash` (SHA-256 of the assistant text, null on error)
- `error` (exception class name, null on success)

The terminal `done` or `error` event includes the persisted row's
`message_id`, allowing the client to round-trip to the canonical
record.

## Reconnection and resumption

We do not currently emit `id:` lines, and we do not implement
`Last-Event-ID` resumption. A dropped connection causes the client to
display the partial response and surface a "regenerate" affordance.
Justification: model calls are non-idempotent and incur cost; resuming
mid-stream would require the upstream API to support it, which neither
OpenAI nor OpenRouter currently does in a useful way. Resumption is
deferred to Phase 35 if the latency CDF analysis shows it is needed.

## Proxy compatibility

The endpoint sets no buffering hints (no `X-Accel-Buffering: no`) at
the application layer because the deployment topology is a single
uvicorn process behind no reverse proxy. When the project is deployed
behind nginx in a later milestone, that header (or
`proxy_buffering off` in the nginx config) will be required to defeat
upstream buffering of the response stream.

## Backpressure

The Python generator is synchronous and yields bytes as the upstream
SDK produces them. Starlette's `StreamingResponse` consumes the
generator under asyncio and writes to the client transport. Slow
clients exert backpressure naturally through the asyncio writer; the
generator pauses when the transport buffer is full. We have not
observed a case in which the generator blocks the request path, but no
explicit backpressure metric is yet recorded.

## References

- HTML Living Standard, "Server-sent events," §9.2 —
  https://html.spec.whatwg.org/multipage/server-sent-events.html (accessed 2026-05-08).
- MDN Web Docs, "Using server-sent events" —
  https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events (accessed 2026-05-08).
- OpenAI, "Streaming," API reference —
  https://platform.openai.com/docs/api-reference/streaming (accessed 2026-05-08).
- Starlette, `StreamingResponse` —
  https://www.starlette.io/responses/#streamingresponse (accessed 2026-05-08).
