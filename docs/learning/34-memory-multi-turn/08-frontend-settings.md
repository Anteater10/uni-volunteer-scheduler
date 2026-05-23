# 34-08 — Frontend settings section (learning lecture)

This lecture walks through the design choices behind the copilot memory
settings panel. By the end you should understand why the component is
shaped the way it is, what the REST contract assumes, and how the
confirmation flow protects the user from accidental data loss.

## The problem

Phase 34 introduced a long-term profile blob the model uses across
sessions. Two facts about that blob are uncomfortable:

1. It is **opaque** — written by an LLM, in free-form English, behind the
   scenes after every session closes. The user has no idea what it says.
2. It is **persistent** — it carries forward to every new conversation,
   so a single bad extraction can colour every future answer.

Without user-visible control, the feature would feel like a black box.
The spec (section 8) makes the trade explicit: the user must be able to
see exactly what the copilot has learned, and clear it whenever they
want.

## What "settings section" means here

We deliberately did **not** add a new top-level route. The volunteer
scheduler has a small navigation surface and the existing `/profile`
page already groups read-only identity and the destructive Log out
button. The memory panel slots between those two sections — it is part
of "your account" rather than a separate destination.

Cost of a new route: extra link in nav, extra mental model for the
user, extra Playwright path. Benefit: zero — the panel is short and
the audience is the same as the rest of the profile page.

## Walking the component code

`CopilotMemorySettings.jsx` is a single function component with five
pieces of local state:

- `profile` — last response from `GET /copilot/profile`.
- `loading` — true between fire-and-resolve of the GET.
- `error` — last error message, displayed inline.
- `confirmOpen` — controls the Modal.
- `deleting` — true between fire-and-resolve of the DELETE.

`fetchProfile` is wrapped in `useCallback` so the effect's dependency
array stays stable across renders. `useEffect` calls it once on mount.

The render path uses an `isEmpty` boolean computed from `profile_text`.
We treat whitespace-only as empty because the extractor's contract says
"return the empty string if no stable facts found", but defending
against future drift (e.g. it returns `" "` instead of `""`) is cheap.

## Why pre-with-whitespace-pre-wrap

The extractor output is short English paragraphs. If we render it in a
plain `<p>`, line breaks collapse and the layout looks like one
runaway sentence. If we render it in a `<pre>` without
`whitespace-pre-wrap`, long lines blow out the card and force
horizontal scroll on phones.

`<pre>` + `whitespace-pre-wrap` is the sweet spot: paragraphs render,
long lines wrap, monospace font signals "this is content the model
generated, not UI copy".

## Why a real modal, not window.confirm

`window.confirm` is faster to wire but it loses focus-trap, looks
out-of-place against the design system, and is not stylable. The app
already ships a `Modal` primitive with proper a11y (focus trap, ESC
to close, aria-modal). Re-using it costs three extra lines.

The modal has two buttons. The destructive one is labelled "Forget"
(not "Confirm") so the verb tells you what's about to happen. The
secondary one is "Cancel". Both are disabled while the DELETE is in
flight to prevent the user double-clicking and dispatching two
requests.

## Test mocking pattern

Vitest + Testing Library + a `vi.fn()` `global.fetch` is the pattern
used by every other copilot test in this folder. Each test queues
responses with `mockResolvedValueOnce`, so the order of fetches is
checked implicitly: if the component fires a request in the wrong
order, the test crashes.

For the Forget flow we queue **three** responses — initial GET, the
DELETE, then the refetch GET — and then assert exactly three fetch
calls happened. That assertion catches two regressions cheaply:

1. The component fires DELETE without confirmation (would still pass
   "empty state appears" but blow up the fetch-count assertion).
2. The component skips the refetch and just clears state in-memory
   (same — fetch count would drop to two).

The cancel test queues only the initial GET and asserts the count is
one. If a future refactor accidentally fires DELETE on cancel, the
test breaks loudly.

## Check-in

If you can answer these you've internalised the lecture:

- Why does the component refetch after DELETE instead of clearing
  state locally? (Hint: who else might have written to the row?)
- What would change if `getProfile()` returned a 404 when the row
  doesn't exist? (Hint: it doesn't — the router synthesises a zero
  version response — but the component would need extra error
  handling if it did.)
- Why is the Forget button disabled in the empty state instead of
  hidden?
