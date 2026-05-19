# Server-Sent Events — Reference

Operational reference for the SSE protocol as used in this repo. Pairs with
[`docs/learning/concepts/server-sent-events.md`](../../learning/concepts/server-sent-events.md)
which has the lecture-length explanation.

## TL;DR

- SSE is a one-way (server → client) HTTP/1.1 streaming format with media
  type `text/event-stream`.
- Wire format: groups of `field: value` lines, terminated by a blank line
  (`\n\n`). Defined fields are `data:`, `event:`, `id:`, `retry:`.
- Browser API: `EventSource` (GET only, no custom headers, automatic
  reconnect with `Last-Event-ID`).
- Alternate consumer: `fetch` + `response.body.getReader()` + hand-rolled
  parser, when you need POST, custom headers, or a request body.
- Used here for streaming LLM tokens from
  `POST /api/v1/copilot/sessions/{id}/messages` to the React chat drawer.

## Wire protocol

### Event grammar

```
stream      ::= event* EOF
event       ::= field+ "\n"
field       ::= name ":" SP? value "\n"
name        ::= "data" | "event" | "id" | "retry"
```

A blank line (two consecutive `\n`) terminates an event and triggers
dispatch on the consumer side.

### Concrete example (this repo's copilot stream)

The full byte sequence for a three-token reply, line endings shown literally:

```
event: token
data: "Hi"

event: token
data: " there"

event: token
data: "!"

event: done
data: {"message_id": "0c1f...e2"}

```

Notes on what you're seeing:

- `event:` names the channel. Three different names are in use: `token`,
  `done`, `error`. Default name when omitted is `"message"`.
- `data:` values are JSON-encoded even when they're "just a string". This
  lets the payload contain literal `\n` characters (`"line 1\\nline 2"`) without
  colliding with the SSE field-separator newline.
- The blank line between events is mandatory. Without it, lines accumulate
  into the same event and dispatch never happens.
- Trailing blank line at end of stream is conventional but not required;
  the consumer dispatches whenever it sees `\n\n`, and connection close
  triggers a final flush.

### HTTP response headers

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache, no-transform
Connection: keep-alive
X-Accel-Buffering: no
Transfer-Encoding: chunked
```

`X-Accel-Buffering: no` is the nginx convention for "do not buffer this
response." Other proxies (Cloudflare, ALB) have their own knobs but this
header is widely respected as a hint.

### Reserved fields beyond `data:` and `event:`

`id: <token>` — sets the **last event ID**. The browser stashes this
internally and sends it back on automatic reconnect via
`Last-Event-ID: <token>` so servers can resume from a known point. This
repo doesn't use `id:` because each turn is a fresh stream.

`retry: <integer ms>` — instructs the consumer to wait this many
milliseconds before reconnecting after a drop. Default in browsers is
~3 seconds.

A line starting with `:` is a comment, useful for keepalives over
buffering proxies:

```
: ping

```

## API surface

### Browser: `EventSource`

```js
const es = new EventSource("/api/v1/feed");
es.addEventListener("message", (ev) => { /* default event */ });
es.addEventListener("token", (ev) => { /* custom event */ });
es.onerror = () => { /* browser will reconnect automatically */ };
es.close(); // teardown
```

Constraints:

- GET only. No `method`, no `body`.
- No custom request headers. Cookie auth only, or token in query string.
- Origin must match or CORS preflight must allow it; with cookies,
  pass `{ withCredentials: true }` and respond with an exact
  `Access-Control-Allow-Origin`.

### Browser: `fetch` + `ReadableStream`

```js
const res = await fetch(url, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
    Authorization: `Bearer ${token}`,
  },
  body: JSON.stringify({ ... }),
  signal: abortController.signal,
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  // split on \n\n, parse events, dispatch
}
```

Key details:

- `TextDecoder("utf-8", { stream: true })` handles UTF-8 characters split
  across chunks (mostly relevant for emoji and CJK).
- `AbortController` is the only way to cancel a streaming `fetch` mid-flight.
- You write your own reconnect logic. Pattern: catch the loop exit, if it
  wasn't an explicit abort, sleep with backoff + jitter, and reissue.

### Server: FastAPI `StreamingResponse`

```python
from fastapi.responses import StreamingResponse

def _sse_format(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")

def event_generator() -> Iterator[bytes]:
    for item in source():
        yield _sse_format("token", json.dumps(item))
    yield _sse_format("done", json.dumps({"ok": True}))

@router.post("/stream")
def stream():
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

FastAPI/Starlette flushes each yielded `bytes` to the wire immediately, so
the generator's iteration pace is the user's perceived latency.

## Usage in this codebase

| Layer | File | Role |
|---|---|---|
| Server endpoint | `backend/app/copilot/router.py` | `POST /api/v1/copilot/sessions/{id}/messages` returns `StreamingResponse` |
| Server formatter | `backend/app/copilot/router.py` — `_sse_format`, `_sse_stream` | Builds the byte stream and persists the assistant row at end |
| Browser parser | `frontend/src/copilot/useCopilotStream.js` — `parseSseChunk` | Splits buffer on `\n\n`, extracts `event:` / `data:` pairs |
| Browser consumer | `frontend/src/copilot/useCopilotStream.js` — `useCopilotStream` | React hook exposing `send`, `partial`, `streaming`, `error`, `cancel` |
| UI | `frontend/src/copilot/CopilotDrawer.jsx` | Renders `partial` as a streaming bubble, commits to history on `done` |

### Event names used

| Event | Data shape | Meaning |
|---|---|---|
| `token` | JSON-encoded string | One chunk of assistant text. Concatenate to assemble the reply. |
| `done` | `{"message_id": "<uuid>"}` | Stream complete. Assistant row written to `copilot_messages`. |
| `error` | `{"error": "<class>", "message_id": "<uuid>"}` | LLM call failed mid-stream. Assistant row written with `error` field set. |

### Why POST and not GET

The user's message is a freeform string up to 4000 chars. Putting it in a
query string would (a) fail at proxies with URL length limits and (b)
leak the message into access logs. POST with JSON body sidesteps both.
The cost is we can't use `EventSource` and have to hand-roll the parser.

## Operational concerns

### Proxy buffering

Most HTTP intermediaries default to buffering response bodies. SSE only
works if every hop between the app and the user flushes immediately.

- **nginx**: `proxy_buffering off` on the relevant location, or send the
  `X-Accel-Buffering: no` response header (less invasive).
- **Cloudflare**: disable "Auto Minify" for JS/HTML on the route; SSE
  works on Free tier but be aware of the 100-second proxy timeout on
  Free/Pro plans.
- **AWS ALB / Application Load Balancer**: enable HTTP/2, set the idle
  timeout high enough to cover the longest expected stream.
- **Corporate / VPN proxies**: often un-fixable. Fall back to long-polling
  for those users (rare in this app's audience but a real consideration).

### Reconnect storms

If a deploy restarts the server, every `EventSource` reconnects within
~3 seconds. To avoid the thundering herd:

- Send `retry: <jittered ms>` in the last event before shutdown.
- Have a load balancer spread the reconnects across replicas.
- On the server, accept connections behind a small connection-rate token
  bucket and gracefully reject with HTTP 503; clients will wait `retry:`
  and try again.

### Connection limits

- HTTP/1.1: browsers cap at 6 connections per origin. Each SSE stream
  takes one. Move to HTTP/2 (single multiplexed connection) if you have
  more than a few simultaneous streams per tab.
- Server side: file descriptors. Linux defaults of 1024 are not enough
  for any serious SSE deployment. Set `ulimit -n` and tune
  `net.core.somaxconn`. Stack pick matters: Python/sync workers hold one
  thread per stream; async workers (uvicorn, asyncio) hold ~one coroutine.

### Cost tracking (LLM-specific)

This codebase's SSE stream wraps an LLM call that costs real money per
token. The end-of-stream `done` event carries `message_id`; the
`copilot_messages` row stores `prompt_tokens`, `completion_tokens`,
`latency_ms`, and `model_id` so spend can be reconstructed by joining
on the session. If the user aborts the stream (closes the tab, hits
cancel), the assistant row is still written from the partial accumulation,
and the OpenRouter usage metadata may or may not be present depending on
how far through the stream we got.

### Tracing and observability

A streaming response is one HTTP request from the load balancer's point
of view, so request-level logging captures only the open and close. To
debug a partial stream:

- Log on each yielded event (sampled in production).
- Log the count of accumulated tokens and total latency at the `done` or
  `error` yield.
- Plumb a trace ID into the response headers and through to the LLM
  client so the OpenRouter dashboard can be cross-referenced.

This repo does the second pattern: see the `assistant_msg = models.CopilotMessage(...)`
construction in `_sse_stream`, which persists prompt/completion token
counts, latency, model id, and error class.

## Glossary

- **Chunked transfer encoding** — HTTP/1.1 mechanism for sending a
  response body without knowing the total length up front. Each chunk is
  prefixed with its hex length, terminated with `\r\n`, and the response
  ends with a zero-length chunk.
- **`EventSource`** — Browser API for consuming SSE. Constructor takes a
  URL, exposes `addEventListener`, handles reconnect automatically.
- **Keepalive** — A comment line (`: ...\n\n`) or empty event sent
  periodically to keep proxies from closing an idle connection.
- **Last-Event-ID** — HTTP header the browser sends on automatic reconnect,
  containing the last `id:` value seen. Used by the server to resume from
  a known point.
- **`Last-Event-ID` resume** — Pattern where the server uses the header
  value to skip events the client has already seen.
- **Long-polling** — Fallback technique: client makes a GET that the server
  holds open until it has something to send, then returns; client immediately
  reissues. Works through any proxy.
- **Multiplexing (HTTP/2)** — Multiple logical streams share one TCP/TLS
  connection, eliminating the per-origin connection limit.
- **`retry:` field** — SSE field instructing the consumer how long to wait
  before reconnecting after a drop, in integer milliseconds.
- **`StreamingResponse`** — FastAPI/Starlette response class that takes an
  iterator/async iterator of `bytes` and flushes each yield to the wire.
- **`X-Accel-Buffering: no`** — Response header originally invented by
  nginx, now respected by many proxies, that disables response body
  buffering for this response only.
