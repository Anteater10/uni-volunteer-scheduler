# Lecture 34-03 — Why we need both an explicit close and an idle sweeper

## The intuitive story

When a user finishes chatting with the copilot, we want to "remember"
something about that conversation for next time. The simplest mental
model is: the user clicks "close" on the drawer, we run the profile
extractor, done. Why is this not enough?

## Why the frontend close signal is weak

In a browser app, "the user closed the drawer" is not a reliable
indicator that the conversation is actually over. Concretely:

1. **Drawer-close is not session-close.** The same drawer can be
   reopened. If the user collapses the copilot panel to look at
   something else and reopens it a minute later, treating the first
   collapse as the end of the session would split one logical
   conversation across two memory-extraction passes — duplicating work
   and possibly producing conflicting profile updates.

2. **The user closes the tab without warning.** `beforeunload` is best-
   effort: mobile browsers often skip it, background-tab kills skip it,
   and ad-blocker extensions sometimes intercept it. Even when it fires,
   you have a few milliseconds at most to ship an HTTP request before
   the page is torn down — `navigator.sendBeacon` is the only thing
   you can reliably use, and it doesn't give you a response so you
   can't observe success.

3. **Network drops happen.** A user on flaky wifi who walks out of
   range loses the chance to send the close signal. The session is
   genuinely ended (from their perspective), but the backend has no
   way to know.

4. **The app crashes.** A renderer crash, a JS error before the
   handler attached, a Service Worker that intercepted-then-died — any
   of these breaks the close signal silently.

5. **Multi-device:** the user opened the copilot on their laptop, then
   walked over to their iPad and opened the copilot there. Neither
   session emitted "close" because both are still "open" in the
   browser. But from the user's perspective the laptop session is over.

Any one of these failure modes is rare. Together they probably account
for 20–40% of sessions in a normal web app. We cannot ship a memory
system that loses a third of conversations.

## Why a server-side sweeper alone is also weak

You might say: forget the close signal entirely, just sweep every 5
minutes and close anything that's been idle 30+ minutes. Why bother
with the explicit endpoint?

Two reasons:

1. **Latency.** If we only have the sweeper, the user gets no memory
   updates for at least 30 minutes after they finish chatting. For a
   user who chats and then immediately wants to test "did it learn
   what I just told it?" that's a terrible UX.

2. **Confidence.** When the user explicitly says "I'm done" (via
   closing the drawer, or in the future an explicit "save this
   session" button), they are giving us a strong signal that the
   conversation is intentionally complete. We can extract right away
   and feel confident the result reflects what the user wanted to
   record. The sweeper's 30-minute heuristic is correct most of the
   time but is fundamentally guessing.

## The two-signal design

So we pair them:

- **Fast path:** explicit `POST /close` from the frontend. Low latency,
  high confidence. Fires immediately when we get a clean close.
- **Safety net:** Celery beat job `sweep_idle_sessions` every 5
  minutes. Catches everything the fast path missed. Bounded latency
  (≤35 min worst case).

Both paths funnel into the same `extract_profile_facts` task and both
go through the same idempotency guards (`closed_at IS NOT NULL`,
forthcoming `profile_extracted_at` check). The end-to-end behaviour is
"every session eventually gets extracted exactly once, and most get
extracted quickly."

## The deeper lesson: signals come in pairs

This is a recurring pattern in distributed/UI systems. Any signal that
travels across a network or depends on user action is unreliable
individually. The fix is rarely "make that one signal more reliable" —
it's "add a second, independent signal that catches what the first one
misses." Examples elsewhere in this codebase:

- **Email sending:** transactional path + retry queue.
- **Signup confirmation:** immediate magic-link click + daily expiry
  sweep.
- **Slot capacity:** application-level guard + DB unique constraint.

Each pair has a fast/strong-signal path for the happy case and a slow/
weak-signal path that converges anyway when the fast path fails. The
copilot session close is just another instance of the same pattern,
applied to memory hygiene.

## Why 30 minutes? Why 5 minutes?

Two numbers, both adjustable:

- **30-minute idle threshold:** long enough that genuine pauses don't
  truncate a real conversation. Empirically users walk away from a chat
  for 5–15 minutes routinely (lunch, call, meeting) and come back; 30
  is comfortably past that band.
- **5-minute beat cadence:** keeps end-to-end latency at ≤35 min for
  idle-closed sessions, while not flooding the beat scheduler with a
  tight loop. The sweep query is cheap (an indexed scan on
  `last_message_at, closed_at` — the migration in Plan 01 added the
  composite index `ix_copilot_sessions_idle_sweep`).

If we later find users are surprised by sessions closing on them mid-
thought, we can move the threshold to 60 minutes without changing any
code other than the `IDLE_TIMEOUT_MIN` constant. The architecture
doesn't bake the number in anywhere else.

## Check-in question

Why did we put the `last_message_at` update inside the **same transaction
as the user-message insert**, rather than after the streaming response
completes? What would go wrong if we updated `last_message_at` only on
clean stream completion?
