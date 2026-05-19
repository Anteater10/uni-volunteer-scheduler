# React Hooks and the Render Lifecycle

Hooks are the dominant React API now — every modern React job interview will probe
your understanding of `useState`, `useEffect`, `useMemo`, `useCallback`, `useRef`,
and the rendering model that ties them together. Most candidates can spell the
function signatures; far fewer can answer "why does my effect run twice in
development?" or "why does this `setInterval` see a stale value?". This lecture
is the version of that conversation I want to have on a whiteboard.

## The design choice

Before hooks landed in React 16.8 (2019), there were two ways to express state
and side effects in React:

1. **Class components** with `this.state`, `this.setState`, and lifecycle
   methods like `componentDidMount`, `componentDidUpdate`, and
   `componentWillUnmount`.
2. **Higher-order components and render props** to share behavior across
   components — `withRouter`, `withFormik`, `<Mouse render={({x,y}) => ...} />`.

Both approaches were painful in different ways. Classes forced you to think
about `this` binding, split related logic across unrelated lifecycle methods
(a subscription was set up in `componentDidMount`, cleaned up in
`componentWillUnmount`, and re-synced in `componentDidUpdate` — three
methods for one concern), and could not be cleanly composed. Higher-order
components produced "wrapper hell" — components nested inside five layers
of HOCs that each forwarded props differently.

Hooks made functions first-class state-bearing components. The trade-off
was that they introduced a runtime invariant that doesn't exist in any other
mainstream framework: **hooks must be called in the same order every render**.
That constraint is the price of letting React identify "which `useState` is
this" without you giving it a name.

Other frameworks made different choices:

- **Vue 3 (Composition API)** uses Proxy-based reactive objects. You can call
  `ref()` and `reactive()` anywhere — order doesn't matter because the value
  is tracked by reference, not by call sequence.
- **SolidJS, Svelte 5 (runes), Preact Signals** use *signals*: fine-grained
  reactive primitives where updating a value re-runs only the closures that
  read it, with no virtual-DOM diff in between.
- **MobX / RxJS** push you toward observables: explicit streams of values
  that you subscribe to.

React stuck with the "re-run the whole component function on every state
change, then diff" model. Hooks are the data structure that survives across
those re-runs. Pros: predictable mental model (the component is "just a
function of props and state"), excellent debugging story, no compiler
required. Cons: the order constraint, easy-to-create stale closures, and a
lot of `useMemo`/`useCallback` ceremony that newer compilers (the React
Compiler / "React Forget") are now trying to eliminate.

## How it works under the hood

Each component instance is backed by a **fiber node** inside React's
reconciler. When the component function runs, React sets a global "current
dispatcher" pointing at that fiber and then invokes the function. As the
function calls `useState`, `useRef`, `useEffect`, React walks a linked list
attached to the fiber:

```
fiber.memoizedState
  → hook { state: 0, queue: ... }      ← useState(0)
  → next: hook { state: { current } } ← useRef(null)
  → next: hook { effect: { create, destroy, deps } } ← useEffect(...)
  → next: hook { state: cachedValue, deps } ← useMemo(...)
  → next: null
```

On the first render, React appends a new hook node for each call. On every
subsequent render, React walks the same list in order and *reads* state out
of each node. This is why the rules of hooks exist:

1. **Only call hooks at the top level.** No `if`, no `for`, no early
   `return` before a hook. If you skipped a hook on render N+1, the list
   would be off by one and your `useState` would suddenly read the
   `useRef`'s value.
2. **Only call hooks from React functions** (components or other hooks).
   Outside of a render, there is no current fiber, so the dispatcher
   throws.

`useState` returns `[value, setter]`. The setter does *not* mutate
`value` — it enqueues an update into the fiber's `queue` and schedules a
re-render. On the next render React drains the queue and computes the new
state. This is why `setCount(count + 1)` called twice in a row only
increments once: both calls captured the same `count` closure.

```jsx
// Wrong — both reads see the same `count`
setCount(count + 1)
setCount(count + 1)

// Right — functional form reads the latest queued state
setCount(c => c + 1)
setCount(c => c + 1)
```

React 18 introduced **automatic batching**: multiple state updates inside
the same tick (event handler, promise microtask, timeout, native event) are
batched into a single re-render. Before 18, only React-managed event
handlers batched.

`useEffect` does not run during render. After React commits the DOM, it
schedules effects asynchronously. The cleanup function from the previous
render runs *before* the new effect. So a parent re-rendering with new
props causes:

```
render → commit DOM → run previous cleanup → run new effect
```

`useLayoutEffect` is the same but synchronous — it runs after the DOM is
mutated but before the browser paints. Use it for measurements where a
flash of the wrong layout would be visible.

`useMemo(fn, deps)` and `useCallback(fn, deps)` are caches keyed by the
dependency array, stored on the hook node. If deps are referentially equal
to last render's deps, React returns the cached value. They are
**performance hints, not guarantees** — React reserves the right to
discard the cache (for example, when a memo-suspends and unmounts).

`useRef(initial)` returns the same object `{ current: ... }` for the
lifetime of the component. Writing to `ref.current` does *not* schedule a
re-render. Refs are how you store mutable data that should survive across
renders without affecting render output.

**Strict Mode** in React 18+ deliberately mounts every component twice in
development: mount, unmount, mount again. The point is to surface effects
that aren't safe to re-run — subscriptions you forgot to clean up,
fetches you fire without an `AbortController`. The fix is always to write
the cleanup function correctly, not to silence the double-invocation.

## How this codebase uses it

### 1. `frontend/src/state/authContext.jsx` — `useState`, `useEffect`, `useMemo`

The auth provider is a textbook example of hook composition:

```jsx
const [user, setUser] = useState(null);
const [initializing, setInitializing] = useState(true);

useEffect(() => {
  (async () => {
    const tok = authStorage.getToken();
    if (tok) await reloadMe();
    setInitializing(false);
  })();
}, []);

const value = useMemo(
  () => ({ user, initializing, isAuthed: !!user, role: user?.role || null,
           reloadMe, login, register, logout }),
  [user, initializing]
);
```

Three things to notice. First, the empty-deps `useEffect` runs once after
mount — under Strict Mode it runs twice in development, but because the
async IIFE is idempotent (calling `/me` twice returns the same user), no
bug surfaces. Second, the `useMemo` is necessary because `value` is the
Context payload — recreating it on every render would force every
`useContext(AuthContext)` consumer to re-render. Third, `login`/`logout`
are *not* in the deps array. That's a latent footgun (they could close
over stale `setUser`) but in this case they close over only stable
references, so it works.

### 2. `frontend/src/copilot/useCopilotStream.js` — `useCallback`, `useRef`

The SSE streaming hook is the most interesting hook in the repo:

```jsx
const [streaming, setStreaming] = useState(false);
const [partial, setPartial] = useState("");
const [error, setError] = useState(null);
const abortRef = useRef(null);

const send = useCallback(async (content) => {
  // ... open fetch with AbortController, read SSE stream, update state ...
  const ac = new AbortController();
  abortRef.current = ac;
  // ...
}, [sessionId, onDone, onError]);

const cancel = useCallback(() => {
  abortRef.current?.abort();
}, []);
```

`abortRef` is the canonical use of `useRef` — a mutable handle that has to
survive across renders but must not trigger one when written to. If
`abortRef` were `useState`, calling `setAbortRef(ac)` mid-stream would
re-render the component for no visible reason. `useCallback` on `send`
matters because consumers of this hook pass `send` into other effects;
recreating it every render would invalidate those effects.

### 3. `frontend/src/lib/useFocusTrap.js` — `useEffect` with cleanup

Focus trapping for modals demonstrates the mount/unmount cleanup pattern:

```jsx
useEffect(() => {
  if (!active) return;
  const container = ref?.current;
  if (!container) return;
  const previouslyFocused = document.activeElement;
  // ... focus first focusable, attach keydown listener ...
  container.addEventListener('keydown', handleKeyDown);
  return () => {
    container.removeEventListener('keydown', handleKeyDown);
    if (previouslyFocused?.focus) previouslyFocused.focus();
  };
}, [ref, active]);
```

The cleanup function does two things: detach the listener and restore
focus to whatever element was focused before the modal opened. Without
the cleanup, every modal close would leak a `keydown` listener and the
focus would dangle on a removed DOM node.

### 4. `frontend/src/components/architecture/FlowDiagram.jsx` — `useMemo` for expensive derivation

The architecture diagram derives edges, indexes nodes, and computes
selection state, all memoized:

```jsx
const edges = useMemo(() => deriveEdges(FLOWS), []);
const nodeIndex = useMemo(() => /* build Map */, []);
const { width, height } = useMemo(() => diagramSize(NODES), []);
const { selectedNodes, selectedEdges, stepNumberByEdge } = useMemo(() => {
  // ... compute selection from focusNode / hoverEdge ...
}, [focusNode, hoverEdge, edges, nodeIndex]);
```

This is `useMemo` as cache invalidation. `deriveEdges` is pure and only
depends on the static `FLOWS` constant, so its deps are `[]`. The
selection block depends on hover/focus state and recomputes only when
those change.

### 5. `frontend/src/components/admin/DuplicateEventDrawer.jsx` — `useState` + `useEffect` reset pattern

When a drawer opens with a new source event, all its internal form state
must reset:

```jsx
React.useEffect(() => {
  if (!open) return;
  setSelectedWeeks([]);
  setTargetYear(sourceYear);
  setTargetQuarter(sourceQuarter);
  setSkipConflicts(true);
  setSubmitError("");
}, [open, sourceEvent?.id, sourceYear, sourceQuarter]);
```

Note the `sourceEvent?.id` in the deps array — not `sourceEvent`
itself. If the parent passes a new object literal each render, depending
on the object would reset every render. Depending on the stable `id`
resets only when the actual event changes.

## Common pitfalls

**Stale closures.** The classic interview trap:

```jsx
function Counter() {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setCount(count + 1), 1000);
    return () => clearInterval(id);
  }, []); // ← bug: empty deps means count is forever 0
  return <div>{count}</div>;
}
```

The interval closure captures `count` from the first render. Forever 0.
Fixes: use the functional setter `setCount(c => c + 1)`, or put `count`
in the deps array (which restarts the interval each tick — usually
wrong), or pull the timer logic into a `useRef`.

**Missing deps.** The exhaustive-deps ESLint rule
(`react-hooks/exhaustive-deps`) catches this. Don't disable it without a
written justification — when you disable it, you are promising that the
referenced variable cannot change, and that promise is rarely true a
year later.

**Infinite re-render.** Calling `setState` unconditionally inside the
component body (not inside an event handler or effect) re-runs the
component, which calls `setState` again, forever. Same thing happens if
your effect's deps include an object/array literal:

```jsx
useEffect(() => {/* ... */}, [{ a: 1 }]); // new object each render → infinite
```

**Effect race conditions.** Sequential fetches in an effect with a
changing dep can land out of order:

```jsx
useEffect(() => {
  fetch(`/api/users/${id}`).then(setUser);
}, [id]);
```

If `id` changes from 1 → 2 → 3 quickly and the response for 2 arrives
last, you'll display user 2 when the latest request was for 3. Fix with
an `AbortController` or an "ignore" flag in cleanup:

```jsx
useEffect(() => {
  let cancelled = false;
  fetch(`/api/users/${id}`).then(u => { if (!cancelled) setUser(u); });
  return () => { cancelled = true; };
}, [id]);
```

**Strict Mode surprise.** In dev, components mount → unmount → remount.
Anything not idempotent (e.g., "create a new session on every mount")
will appear to run twice. The right answer is almost always to dedupe at
the data layer, not to fight Strict Mode.

In code review, scan for: empty deps arrays with closure-captured props,
object/array literals in deps, missing cleanup in effects that attach
listeners or open subscriptions, and `useState` being used where
`useRef` would be correct.

## Interview Q&A

**Q (junior):** What's the difference between `useState` and `useRef`?

A: Both let a function component persist a value across renders. The
difference is what they do when you write to them. `useState` queues a
re-render and the new value shows up on the *next* render. `useRef`
gives you a mutable container (`{ current: ... }`) — writing to
`ref.current` is invisible to React; no re-render. Use `useState` for
anything the UI displays. Use `useRef` for timers, DOM nodes, abort
controllers, "previous value" tracking — anything where a re-render
would be wasteful or wrong.

```jsx
const inputRef = useRef(null);
useEffect(() => { inputRef.current?.focus(); }, []);
return <input ref={inputRef} />;
```

**Q (junior):** Why must hooks be called at the top level of a component?

A: React identifies which hook is which by *call order*, not by name. It
stores hooks as a linked list on the fiber, and every render walks that
list in sequence. If you wrapped a `useState` in an `if`, then on the
render where the condition was false you'd skip a node, and the *next*
hook would read the wrong slot. The ESLint plugin
`react-hooks/rules-of-hooks` catches conditional calls. The fix is
always to lift the condition inside the hook, e.g.,
`useEffect(() => { if (!enabled) return; ... }, [enabled])`.

**Q (mid):** Explain how `useEffect`'s dependency array works and what
"exhaustive deps" means.

A: The deps array is a memoization key. React compares each entry with
`Object.is` against the previous render's deps. If every entry matches,
React skips the cleanup-and-rerun. If any entry differs, React runs the
previous cleanup and the new effect. "Exhaustive deps" is the ESLint
rule that insists every variable the effect closes over from the
component scope appears in the array. The reason is that without it the
effect will run with stale closures: the function body will read the
old value of a prop or state. Disabling the rule is a last resort —
better fixes are pulling stable values out (constants, refs) or moving
work outside the effect.

**Q (mid):** Why does my `useEffect` run twice in development?

A: React 18 Strict Mode deliberately double-invokes effects — mount,
unmount, remount — to surface effects that aren't safe to re-run.
The double-invocation only happens in development. The right response
is to make the effect idempotent: clean up subscriptions, abort fetches,
dedupe at the data layer. If you can't make it idempotent, the work
probably doesn't belong in `useEffect` — it might belong in an event
handler or a route loader.

**Q (mid):** When would you reach for `useMemo` vs. `useCallback`?

A: They're nearly identical. `useMemo(fn, deps)` caches the *return*
value of `fn`. `useCallback(fn, deps)` caches the function itself. You
reach for them in two cases: (1) the computation is expensive and you
don't want to redo it every render, or (2) the value is a *referential
identity* that gets passed into a memoized child or another hook's
dep array, where a new object each render would defeat the
memoization. Don't sprinkle them everywhere — they have a cost too
(comparing deps, storing the cache). The React Compiler aims to remove
the need for them entirely.

**Q (mid):** What is a stale closure and how do you fix it?

A: A stale closure is when a function captures a variable from a
previous render and continues to read the old value even after the
component has re-rendered with a new one. Most common in `useEffect`
and `setInterval` with an empty deps array. Fix paths: (1) use the
functional updater `setX(prev => ...)` which doesn't depend on the
captured value; (2) put the captured variable in the effect's deps so
the closure is recreated; (3) stash the latest value in a ref and read
`ref.current` inside the closure.

```jsx
const latestCount = useRef(count);
useEffect(() => { latestCount.current = count; });
useEffect(() => {
  const id = setInterval(() => console.log(latestCount.current), 1000);
  return () => clearInterval(id);
}, []);
```

**Q (senior):** Walk me through what happens between `setState` being
called and the screen updating.

A: `setState` enqueues an update into the fiber's update queue and
calls `scheduleUpdateOnFiber`. React 18's scheduler decides a priority
(default for events, transition for `startTransition`, etc.) and queues
a microtask or task to flush. Inside the flush, React begins the
*render phase*: starting at the root, it walks fibers, calling each
component function whose state changed (or whose ancestor re-rendered).
During render, each `useState` reads from the queue and computes the
new state. After the render phase produces a new fiber tree, React
enters the *commit phase*: it diffs against the previous tree and
applies the minimum DOM mutations, runs `useLayoutEffect` cleanups and
effects synchronously, then schedules `useEffect` cleanups and effects
asynchronously (typically in a `MessageChannel` task) so they run after
paint. Multiple `setState` calls in the same tick are batched into one
render. Concurrent features like `useTransition` let lower-priority
renders be interrupted by higher-priority ones.

**Q (senior):** How would you implement a basic `useMemo` from scratch?

A: You'd need somewhere to store last deps and last value per call
site. React uses the fiber's hook list; in a toy implementation you can
use a module-level counter that resets each render. Sketch:

```jsx
let currentFiber = null;
let hookIndex = 0;

function useMemo(fn, deps) {
  const hook = currentFiber.hooks[hookIndex] ?? {};
  const same = hook.deps && hook.deps.length === deps.length &&
               hook.deps.every((d, i) => Object.is(d, deps[i]));
  const value = same ? hook.value : fn();
  currentFiber.hooks[hookIndex] = { value, deps };
  hookIndex++;
  return value;
}
```

The real implementation lives in React's `ReactFiberHooks` module and
handles concurrent mode, suspended renders, and the on-render
dispatcher swap. But the core mechanic is: linked list slot, compare
deps, return cached or recompute.

**Q (senior):** Why is the `value` prop of a Context provider usually
wrapped in `useMemo`, but most other props aren't?

A: Because every consumer of a context re-renders whenever the
provider's `value` changes by reference. If you write
`<Ctx.Provider value={{ a, b }}>`, you create a new object every
parent render, and every `useContext(Ctx)` consumer re-renders even if
`a` and `b` are referentially the same. `useMemo` stabilizes the
identity. Regular props don't have this problem because (a) the
child is usually `React.memo` or doesn't care, and (b) prop
comparisons happen per-child, not via a fan-out subscription. The
broader lesson: anywhere an identity is *shared* (context, store
selectors, dep arrays), you must stabilize.

## Further reading

- React docs: <https://react.dev/reference/react/hooks>
- "A Complete Guide to useEffect" by Dan Abramov:
  <https://overreacted.io/a-complete-guide-to-useeffect/>
- "Why Do Hooks Rely on Call Order?" by Dan Abramov:
  <https://overreacted.io/why-do-hooks-rely-on-call-order/>
- React source — `packages/react-reconciler/src/ReactFiberHooks.js`:
  <https://github.com/facebook/react/blob/main/packages/react-reconciler/src/ReactFiberHooks.js>
