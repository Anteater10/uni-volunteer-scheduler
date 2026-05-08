# Server-Sent Events for Streaming LLM Responses

> _Stub — to be filled in alongside the SSE endpoint implementation._

## Summary

Phase 30 streams assistant tokens to the client over Server-Sent Events
(SSE). SSE is a unidirectional server-to-client protocol layered over
HTTP, defined in the HTML Living Standard. We adopt SSE rather than
WebSocket on the basis of three constraints: token streaming is
inherently unidirectional within a turn; SSE traverses corporate HTTP
proxies without upgrade handshakes; and `EventSource` provides automatic
reconnection with `Last-Event-ID` resumption at no implementation cost.

## Endpoint specification

- Method: `POST /api/v1/copilot/sessions/{session_id}/messages`
- Request body: `{ "content": "<user message>" }`
- Response: `Content-Type: text/event-stream`
- Event types: `message` (token chunk), `done` (terminal), `error`
  (recoverable or terminal failure)

## Reconnection and idempotency

To be specified once the implementation is in place.

## Proxy compatibility

To be specified once the implementation is in place.

## References

- HTML Living Standard, "Server-sent events" — to be cited at fill-in.
- OpenAI streaming reference — to be cited at fill-in.
