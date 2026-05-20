# 06 — Citation chips on the frontend (Plan 32-06)

> Two-folder rule pair: see also
> `docs/documentation/32-rag-retrieval/06-citation-chips-frontend.md`
> for the publication-style writeup.

## Why this lecture exists

Phase 32 added a hybrid retrieval pipeline behind the copilot. The model now
has actual sources to ground its answer in. But the user can't see any of that
— the chat drawer just streams text, identical to Phase 30. This plan closes
the loop: render small chips below each assistant message, click one, see the
exact source chunk that was retrieved.

This is the first time in v1.4 we touch the SSE wire format from the
frontend in an additive way. The lesson worth internalising is **how to add a
new event branch to a streaming parser without disturbing the existing ones**.

## Concept 1 — The SSE meta event in React

Phase 30 taught us that EventSource only speaks GET, so the copilot stream is
parsed by hand using `fetch + ReadableStream + parseSseChunk`. The dispatcher
loop looked like:

```js
if (ev.event === "token") { /* accumulate */ }
else if (ev.event === "done") { /* finalize */ }
else if (ev.event === "error") { /* surface */ }
```

Plan 32-04 (backend) added a single new event named `meta` that arrives
**exactly once, before the first `token`**. Adding a new branch is a
two-line change in concept:

```js
} else if (ev.event === "meta") {
  const meta = JSON.parse(ev.data);
  turnCitations = Array.isArray(meta.citations) ? meta.citations : [];
  setCitations(turnCitations);
  setLatencies({ retrieval: meta.retrieval_latency_ms, rerank: meta.rerank_latency_ms });
}
```

The subtlety is that React state is asynchronous. By the time
`onDone({ text, citations })` fires (synchronously, inside `send`), the React
reconciler hasn't yet flushed the `setCitations` call. If we only relied on
the hook's `citations` state when assembling the next message bubble we'd
read the **previous** turn's value. The fix: keep a local `turnCitations`
variable inside `send`, and pass it directly through the `onDone` payload.
State is the **view layer**; the loop-local variable is the **truth**.

## Concept 2 — Why a side panel beats inline expansion

The team considered two click-through styles:

1. **Inline expansion** — clicking a chip injects the full source content
   below the message.
2. **Side-panel modal** — clicking a chip opens a right-hand panel that
   overlays the chat (RESEARCH §Pattern 6 + Open Q #1).

We picked the side panel for three reasons:

- **Mobile width.** The drawer already occupies the full width on `sm:`. An
  inline expansion would push the message stream around aggressively and the
  user would lose their place. A modal panel slides over it and the chat
  scrolls underneath, preserving context.
- **Focus management.** A panel has a single, predictable "Close" affordance.
  Inline expansion would need a per-chip toggle, multiplying focus traps.
- **One source at a time.** The RAG paper warns that showing all sources at
  once invites cherry-picking. A modal forces one source into the spotlight,
  matching the cognitive task ("did the model actually use this?").

## Concept 3 — Honest copy

`docs/learning/32-rag-retrieval/04-sse-meta-event.md` covered this at the
wire level, but it matters at the UI level too. The header is
**"Source consulted"**, not "Source cited". RESEARCH §Pitfall 7 calls this
out: retrieval citations are not the same as generation grounding. The chips
mean *we showed these chunks to the model* — they do not mean *the model
used these chunks*. Phase 33 (tool calls) will close that gap. Until then, we
phrase it honestly so volunteer users don't take chip-equals-truth as gospel.

## Concept 4 — Accessibility wiring

A `<span>` styled as a chip is not a button. We add:

- `role="button"` — assistive tech announces it as clickable.
- `tabIndex={0}` — it enters the keyboard tab order.
- `onKeyDown` for Enter and Space — keyboard activates just like the mouse.
- `aria-label="Citation {N}: {filename}"` — screen-reader users hear the
  index and the file, not the truncated visible text.

The chip group itself is a `role="list"` with
`aria-label="Sources consulted"` so screen readers can navigate the
citations as a group. We did not pick `<ul>/<li>` markup because Tailwind's
default list styling would fight the `flex gap-2 overflow-x-auto` layout.

## Concept 5 — Per-message citation snapshot

The hook tracks the **current turn's** citations as React state — but each
assistant message bubble carries its **own** snapshot at the moment the turn
completed. If a user sends two messages in a row, the first bubble still
shows the first turn's chips even after the hook's `citations` state has
been replaced by turn 2's payload. This is why the drawer captures
`citations` from the `onDone({ citations })` payload and stores it on the
message object:

```js
setMessages((m) => [...m, { role: "assistant", content: text, citations }]);
```

Without this, the chips for turn 1 would either disappear or — worse —
silently swap to turn 2's citation set, decoupling the chips from the text
above them.

## Check-in

If you can explain the following in one sentence each, this lecture stuck:

1. Why does the meta event handler need a local variable (`turnCitations`)
   in addition to React state?
2. What does "Source consulted" mean that "Source cited" doesn't?
3. Why is the chip a `<span role="button" tabIndex={0}>` instead of a real
   `<button>`?

Next plan: 32-07 — RAGAS offline harness (parallel work, no UI impact).
