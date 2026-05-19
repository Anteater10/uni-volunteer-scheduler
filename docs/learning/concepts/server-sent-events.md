# Server-Sent Events (SSE)

A lecture on the `text/event-stream` protocol, written for general web/JS
interview prep. SSE shows up under "real-time", "push", "streaming", "chat
UIs", and "system design". You should be able to draw the wire format, write
both an `EventSource` consumer and a `fetch` + `ReadableStream` consumer, and
defend the choice of SSE over WebSockets in a system design round.

## Why this matters for interviews

Three angles come up:

1. **Practical front-end.** "Build a chat UI that streams tokens." If you reach
   for WebSockets, you'll spend the round explaining why you needed full
   duplex. If you reach for SSE, you get HTTP semantics, automatic reconnect,
   and a one-line API for free.
2. **Systems design.** "Design notifications for 100k concurrent users." SSE
   trades duplex for simplicity: it's one HTTP/1.1 connection per client,
   parses with a four-line state machine, and rides on every L7 load balancer
   that already knows HTTP.
3. **Debugging gotchas.** "Your stream works locally but not in prod." That's
   almost always nginx, Cloudflare, or AWS ALB buffering response bodies until
   the connection closes. Knowing this saves an interviewer half a round.

## The design choice

SSE is **server-to-client only**, **text-only**, over a normal HTTP/1.1
response with `Content-Type: text/event-stream` and chunked transfer encoding.
The browser's `EventSource` parses it into named events. It is roughly the
simplest possible "push" primitive you can build without leaving HTTP.

### When to pick SSE

- The client mostly reads. Updates, notifications, log tails, LLM tokens,
  metrics, build progress.
- You want HTTP semantics: cookies, headers, CORS, auth proxies, CDN, gzip,
  HTTP/2 multiplexing — all just work.
- You want automatic reconnect with a `Last-Event-ID` resume hint, written
  by the browser, free.

### When to pick WebSockets

- The client also writes a lot (collaborative cursors, multiplayer game,
  trading clients). WS is bidirectional and binary.
- You need sub-millisecond client-to-server latency for input events.
- The protocol on top of the bytes is your own (CBOR, protobuf,
  msgpack) and you want a single tunnel.

### When to pick HTTP/2 (or HTTP/3) streaming

- You control both ends and you can write a custom client. HTTP/2 streams
  are duplex, binary, and multiplex many "channels" on one TCP/QUIC
  connection. gRPC-Web and Vercel `Response` streaming use this.

### When to fall back to long-polling

- You're stuck behind a proxy that buffers `text/event-stream`. You hold a
  GET open until you have something to send, then return; the client
  immediately re-requests. Higher latency and more requests, but it works
  through anything that allows long-running responses.

| Feature | SSE | WebSocket | Long polling |
|---|---|---|---|
| Direction | server → client | duplex | server → client per request |
| Transport | HTTP/1.1 chunked or HTTP/2 stream | TCP + WS frame | HTTP request/response |
| Reconnect | automatic with `Last-Event-ID` | DIY | DIY (just re-request) |
| CORS | normal preflight rules | separate Origin handshake | normal preflight |
| Auth headers | not on `EventSource` (cookie only) | not on browser ctor | normal |
| Binary | no (text only) | yes | yes (via base64) |
| Load balancers | "any L7 LB works" | many LBs need sticky + special config | works on anything |
| Browser API | `EventSource` | `WebSocket` | none — write it yourself |

## How it works under the hood

The protocol is dead simple. Once you've read [the WhatWG spec][1] section on
the `event stream` interpretation, you can implement a parser in 20 lines of
JS.

### The wire format

The server sends UTF-8 text. Events are separated by **a blank line**
(two consecutive `\n`). Within an event, lines are field-name + colon +
optional space + value:

```
event: token
data: hello

event: token
data: world

event: done
data: {"message_id": "abc"}

```

Exactly four field names are defined:

- `data:` — the payload. Multiple `data:` lines in the same event are
  concatenated with `\n` between them. A bare `data:` is fine, the value is
  empty string.
- `event:` — names the event so consumers can route. Default is `"message"`.
- `id:` — sets the last event ID. On reconnect the browser sends this back
  as the `Last-Event-ID` header so the server can resume.
- `retry:` — integer ms. Tells the browser how long to wait before
  reconnecting after a drop.

Lines starting with `:` are comments (and a useful keepalive trick — see
"Common pitfalls").

### HTTP transport

The endpoint is just an HTTP GET (or POST, if you bring your own client)
that responds with:

```
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
Transfer-Encoding: chunked

```

The response stays open. The server `flush()`es each event as it produces it.
The TCP stream stays live; chunked encoding frames each flush so the client's
parser can find boundaries. On HTTP/2 it's a single open stream on a
multiplexed connection — no `Transfer-Encoding` header but the streaming
semantics are equivalent.

### The parser state machine

You're maintaining one piece of mutable state: a string buffer.

```js
function parseSseChunk(buffer) {
  const events = [];
  let rest = buffer;
  while (true) {
    const sep = rest.indexOf("\n\n");
    if (sep === -1) break;          // need more bytes
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
  return [events, rest];           // give the caller back the un-terminated tail
}
```

The critical part: **TCP segments do not respect event boundaries**. A single
`reader.read()` call may give you half of one event, or three full events plus
a half. You accumulate into the buffer, split on `\n\n`, and return the
un-terminated tail for the next iteration. Get this loop wrong and you'll see
"sometimes the last word is missing" bugs that look like LLM hallucinations
but are really parser bugs.

### `EventSource` does all this for you

```js
const es = new EventSource("/api/v1/feed");
es.addEventListener("token", (ev) => append(ev.data));
es.addEventListener("done", (ev) => finalize(JSON.parse(ev.data)));
es.onerror = () => { /* browser will retry automatically */ };
```

The browser handles the chunked decode, the parser state machine, the
reconnect timer, and the `Last-Event-ID` header. You give it a URL and named
event handlers.

The catch: `EventSource` only does GET, can't set custom headers (no `Authorization`),
and can't carry a request body. That's why custom-fetch SSE is so common in
LLM apps — the request body has the prompt.

## How this codebase uses it

This repo has one SSE stream: the copilot chat at
[`backend/app/copilot/router.py`](../../../backend/app/copilot/router.py)
and the matching browser consumer at
[`frontend/src/copilot/useCopilotStream.js`](../../../frontend/src/copilot/useCopilotStream.js).

### Backend: FastAPI `StreamingResponse`

The server side is `POST /api/v1/copilot/sessions/{session_id}/messages`. The
endpoint returns a `StreamingResponse` whose generator yields SSE-formatted
bytes:

```python
# backend/app/copilot/router.py
def _sse_format(event: str, data: str) -> bytes:
    return f"event: {event}\ndata: {data}\n\n".encode("utf-8")


def _sse_stream(db, sess, chat_messages, prompt_hash):
    accumulated: list[str] = []
    final_meta: dict = {}
    error_class: str | None = None
    try:
        for chunk, meta in llm.stream_completion(messages=chat_messages, ...):
            if meta:
                final_meta = meta
            elif chunk:
                accumulated.append(chunk)
                yield _sse_format("token", json.dumps(chunk))
    except Exception as exc:
        error_class = exc.__class__.__name__
    # persist assistant message + final event
    if error_class:
        yield _sse_format("error", json.dumps({"error": error_class, ...}))
    else:
        yield _sse_format("done", json.dumps({"message_id": str(assistant_msg.id)}))

return StreamingResponse(
    _sse_stream(db, sess, chat_messages, prompt_hash),
    media_type="text/event-stream",
)
```

Three named events: `token`, `done`, `error`. The router's docstring is the
spec for the wire format. Notice how `json.dumps(chunk)` is used even for the
token text — because tokens can contain literal `\n` characters and we don't
want them to look like SSE field separators. JSON encoding turns `\n` into
`\\n` so a 4-line LLM response still parses as one event per token.

### Frontend: fetch + `ReadableStream` + manual parser

EventSource can't carry a POST body, so the frontend reaches for `fetch` and
reads `response.body` as a stream:

```js
// frontend/src/copilot/useCopilotStream.js
res = await fetch(`${COPILOT_BASE}/sessions/${sessionId}/messages`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
    Authorization: `Bearer ${tok}`,
  },
  body: JSON.stringify({ content }),
  signal: ac.signal,
});

const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  let events;
  [events, buffer] = parseSseChunk(buffer);
  for (const ev of events) {
    if (ev.event === "token") {
      const chunk = JSON.parse(ev.data);
      assembled += chunk;
      setPartial(assembled);
    } else if (ev.event === "done") { ... }
    else if (ev.event === "error") { ... }
  }
}
```

Two details worth noticing:

- `TextDecoder("utf-8", { stream: true })` — `stream: true` tells the
  decoder that a multi-byte UTF-8 character might be split across two
  reads. Without this, an emoji in the LLM response can render as `��`.
- `AbortController` plumbed through `signal: ac.signal` — gives us a
  `cancel()` button that closes the connection cleanly rather than letting
  the LLM cost meter run.

### Wiring it into React

The hook exposes `send(content)` and a `partial` string that grows as tokens
arrive. The chat drawer (`frontend/src/copilot/CopilotDrawer.jsx`) renders
`partial` into a placeholder bubble while `streaming` is true, then commits
the final text to the messages array in `onDone`.

## Common pitfalls

### Proxies buffering the response body

The single most common production failure. nginx, Cloudflare, AWS ALB, and
most corporate proxies buffer `Content-Type: text/event-stream` responses,
trying to be helpful. Your stream works locally, fails in staging.

Fix: set the de-facto-standard hint header on the response:

```
X-Accel-Buffering: no
```

That covers nginx. For Cloudflare you also disable "Auto Minify" and set
`Cache-Control: no-cache, no-transform`. For ALB you set the target group
attribute `lb_cookie_stickiness` off and confirm the listener is HTTP/1.1+.

You can also send a comment line as a keepalive every ~15 seconds:

```
: keepalive\n\n
```

It's ignored by the spec, but it pushes bytes through proxies that close
idle connections.

### `EventSource` can't set headers

The browser's `EventSource` constructor only takes a URL and a `withCredentials`
option. You cannot set `Authorization: Bearer <jwt>`. The workarounds are:

1. Cookie auth — let the browser send the session cookie automatically.
2. Token in the URL query string (`?token=...`) — works but leaks the
   token into nginx access logs and the browser history.
3. Drop `EventSource` and use `fetch` + `ReadableStream` (what this repo does).

### CORS with credentials

If your stream is on a different origin and uses cookies:

- Client: `new EventSource(url, { withCredentials: true })`.
- Server: `Access-Control-Allow-Origin: <exact origin>` (not `*`) plus
  `Access-Control-Allow-Credentials: true`.

A `*` origin with credentials is a silent fail in every browser.

### Partial JSON in `data:` lines

If your event payload is JSON, you must put the entire JSON object in a
single `data:` line (or use multiple `data:` lines that concatenate with `\n`
into a valid JSON-with-embedded-newlines). A common mistake: pretty-printing
the JSON with `JSON.stringify(obj, null, 2)`, which puts each field on its
own line. The receiver sees multiple `data:` lines, joins them with `\n`, and
gets valid JSON — but only because the field separator and the embedded
newline happen to be the same character. The moment one of the values
contains `\n` itself, the parse breaks.

The robust pattern: always `JSON.stringify(obj)` without indentation, always
put the whole thing on one `data:` line.

### Reconnect storms

Default `EventSource` reconnect delay is browser-defined, usually ~3 seconds.
If your server is down and 10,000 clients try to reconnect, they all hit you
at once, then again three seconds later. Either:

- Send `retry: 30000` in your last event before a planned restart.
- Add jitter on the server: `retry: ${30000 + Math.random()*30000}`.

### One connection per tab eats your file descriptors

The browser's per-origin HTTP/1.1 connection limit is 6. On HTTP/2 it's
effectively unlimited (multiplexed). If you have many SSE streams (one per
component) on HTTP/1.1, you starve the rest of your app. Either move to
HTTP/2 (free if you're behind a CDN) or multiplex by sending an event-type
discriminator on a single stream.

## Interview Q&A

**Q (mid):** Why use SSE instead of WebSockets for an LLM chat UI?
**A:** The traffic is asymmetric — the client sends one short message, the
server streams a long response. WebSockets buys you bidirectional binary
framing that the LLM use case doesn't need, while charging you for it in
proxy compatibility, sticky sessions, and a hand-rolled reconnect/auth flow.
SSE rides on HTTP/1.1 or HTTP/2, parses with a 20-line state machine, and
browsers give you `EventSource` (or you reach for `fetch` + `ReadableStream`
when you need to POST a body, as this repo does).

**Q (mid):** Walk me through what happens when the network blips during an
SSE stream.
**A:** TCP keeps the connection until the OS or proxy decides it's dead;
once `EventSource` notices, it fires `onerror`, waits the `retry:` interval
(default ~3s), and reconnects with header `Last-Event-ID: <last id seen>`.
If the server kept event IDs and can resume from one, the client missed
nothing. If you hand-rolled SSE with `fetch`, you're responsible for that
reconnect + resume logic yourself — which is one reason teams choose
`EventSource` when they can.

**Q (mid):** Your SSE works locally but in production the user sees the
entire response appear at once after a long pause. What's happening?
**A:** A proxy is buffering. nginx, Cloudflare, an ALB, or a corporate
gateway is reading the full response into memory and forwarding it only
when the connection closes. Fix is `X-Accel-Buffering: no` plus
`Cache-Control: no-cache, no-transform` on the response, and disable
auto-minification / response buffering at every layer between the app and
the user. If it's `Connection: keep-alive` HTTP/1.0 between a hop, the
fundamental issue is that HTTP/1.0 doesn't support chunked encoding and
you need to upgrade the hop.

**Q (mid):** How would you build a chat UI that streams tokens?
**A:** Server endpoint returns `StreamingResponse` with media type
`text/event-stream`. For each token from the model emit
`event: token\ndata: <json-encoded chunk>\n\n`. End with
`event: done\ndata: <metadata>\n\n`. Client: open `fetch` with method POST,
read `response.body.getReader()`, decode with
`new TextDecoder("utf-8", { stream: true })`, accumulate into a buffer,
split on `\n\n`, parse each block. Push token data into React state to
render incrementally. Plumb `AbortController.signal` so the user can cancel.
On error/done, commit the accumulated string to the conversation history
and reset the partial-streaming state. This codebase's
`frontend/src/copilot/useCopilotStream.js` is exactly this pattern.

**Q (senior):** Design streaming notifications for 100k concurrent users.
**A:** SSE per user, fronted by an HTTP/2 reverse proxy so each TLS
connection multiplexes the streams. A pub/sub layer (Redis Streams,
Kafka, NATS) for fan-out. Each app server holds N open responses and
listens for relevant events on the bus, filtering by `user_id` to write
into the right open response. To scale horizontally, route by user ID
(consistent hashing) so each user lands on a known server. For resilience
include monotonic `id:` per event so reconnects can resume with
`Last-Event-ID`. Keepalive comment every 15s. Capacity-plan around
file-descriptor and per-process socket limits — Linux defaults bite you
around 1024 unless you `ulimit -n` and tune `net.core.somaxconn`. One
Go/Rust/Node server can hold tens of thousands of idle streams; with N
servers you're easily into the 100k+ range.

**Q (senior):** Why does this codebase use `fetch` + `ReadableStream`
instead of `EventSource`?
**A:** The endpoint is a POST with a JSON body containing the user's
message. `EventSource` only does GET with no body and only allows
cookie/URL auth. We use bearer-token auth in a header
(`Authorization: Bearer <jwt>`) and pass the message body as JSON, so we
need the full `fetch` API. The cost is we hand-roll the parser
(`parseSseChunk` in `useCopilotStream.js`) and we don't get free
reconnect with `Last-Event-ID`. Since each turn is a fresh stream that
the user kicks off, reconnect-resume isn't valuable here — losing the
connection should restart the turn, not resume mid-token.

**Q (senior):** How do you test an SSE endpoint?
**A:** Two layers. (1) Pure unit test of the parser — feed it crafted
byte sequences including split events, multi-line `data:` payloads,
embedded `\n` in JSON, and assert the event list is correct. The repo's
`parseSseChunk` is a pure function so this is one-liner tests. (2)
Integration test of the endpoint — use a streaming HTTP client (FastAPI's
`TestClient` supports it via `client.stream("POST", url)`) and consume
the bytes; assert event names, payload shapes, and that the assistant
message row exists in the DB after the stream ends. Mock the LLM client
to yield deterministic chunks.

**Q (senior):** Compare SSE to gRPC server streaming.
**A:** Both are server-streaming RPCs. gRPC server streams ride HTTP/2,
use protobuf binary framing, and give you generated clients with
back-pressure flow control via HTTP/2 window updates. SSE is text only,
human-readable on the wire (curl-able!), and works in every browser
without a generated client. gRPC wins for service-to-service or
mobile-native clients where you control both ends and want strong typing.
SSE wins for browser clients (gRPC-Web is workable but proxy-fragile)
and for ops debuggability — `curl -N` on an SSE endpoint is the fastest
production diagnostic tool in your toolbox.

## Further reading

- MDN: [Using server-sent events](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events)
- WhatWG HTML spec: [Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html)
- MDN: [`EventSource`](https://developer.mozilla.org/en-US/docs/Web/API/EventSource)
- WhatWG fetch streams: [`Response.body`](https://developer.mozilla.org/en-US/docs/Web/API/Response/body)
- FastAPI: [StreamingResponse](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- nginx: [`X-Accel-Buffering`](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering)
- OpenAI: [Streaming chat completions](https://platform.openai.com/docs/api-reference/streaming)

[1]: https://html.spec.whatwg.org/multipage/server-sent-events.html
