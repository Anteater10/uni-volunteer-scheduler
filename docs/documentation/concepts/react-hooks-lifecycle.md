# React Hooks and the Render Lifecycle — Reference

React hooks (`useState`, `useEffect`, `useMemo`, `useCallback`, `useRef`,
plus the rarer `useLayoutEffect`, `useReducer`, `useImperativeHandle`,
`useTransition`, `useDeferredValue`, `useId`) are the primitive API for
function components. They store per-instance state on the fiber as an
ordered linked list, and they participate in React's two-phase
render/commit lifecycle. Understanding the order constraint, batching
semantics, and Strict Mode double-invocation is mandatory for writing
correct React code.

## API surface

TypeScript signatures, taken from `@types/react`:

```ts
function useState<S>(
  initial: S | (() => S)
): [S, Dispatch<SetStateAction<S>>];

type Dispatch<A>           = (value: A) => void;
type SetStateAction<S>     = S | ((prev: S) => S);

function useEffect(
  effect: () => (void | (() => void)),
  deps?: ReadonlyArray<unknown>
): void;

function useLayoutEffect(
  effect: () => (void | (() => void)),
  deps?: ReadonlyArray<unknown>
): void;

function useMemo<T>(
  factory: () => T,
  deps: ReadonlyArray<unknown>
): T;

function useCallback<T extends (...args: any[]) => any>(
  callback: T,
  deps: ReadonlyArray<unknown>
): T;

function useRef<T>(initial: T): { current: T };
function useRef<T = undefined>(): { current: T | undefined };

function useReducer<R extends Reducer<any, any>>(
  reducer: R,
  initialState: ReducerState<R>,
  initializer?: undefined
): [ReducerState<R>, Dispatch<ReducerAction<R>>];

function useTransition(): [isPending: boolean, startTransition: (cb: () => void) => void];
function useDeferredValue<T>(value: T): T;
function useId(): string;
```

Notes:

- `useState`'s initial value can be a function — that function runs once
  on mount, lazily. Use this when the initial value is expensive
  (`useState(() => buildLookupTable())`).
- The setter from `useState` has a stable identity across renders — you
  don't need to put it in deps arrays.
- `useEffect` returning `undefined` (or any non-function) is fine; the
  cleanup is a no-op.
- `useMemo` and `useCallback` deps **must** be an array. Omitting deps
  is not supported (unlike `useEffect`, which treats no deps as "run
  every render"). React will warn.
- `useRef(initial)` only uses `initial` on the first render. Passing a
  new value later does nothing.

## Mental model

**Hooks live on the fiber.** Each rendered component has a fiber node;
each call to a hook is a slot in `fiber.memoizedState`, a linked list
that React walks in order on every render. The invariant: **the
sequence of hook calls must be identical across renders.** No
conditional hooks. No hooks in loops with a variable bound. No early
returns before hooks. The ESLint plugin
`eslint-plugin-react-hooks` enforces this statically.

**Renders are pure; effects run after commit.** The body of your
component should not perform side effects, mutate refs based on prop
values, or fire fetches. It computes JSX from props + state. Side
effects belong in `useEffect` (after paint) or `useLayoutEffect`
(after commit, before paint). React 18 Strict Mode runs the component
body twice in development to surface impure renders; it also mounts,
unmounts, and remounts every component to surface effects that aren't
cleanup-safe.

**State updates are async and batched.** Calling `setState(x)` doesn't
change `state` immediately — it enqueues an update and schedules a
re-render. Multiple updates in the same tick (event handler,
microtask, native event in React 18) collapse into one render. To
update based on the previous state, use the functional form:
`setState(prev => prev + 1)`.

## Usage in this codebase

| File | Hooks | What it demonstrates |
|---|---|---|
| `frontend/src/state/authContext.jsx` | `useState`, `useEffect`, `useMemo` | Provider pattern, memoized context value, mount-time fetch |
| `frontend/src/copilot/useCopilotStream.js` | `useState`, `useCallback`, `useRef` | Custom hook with imperative cleanup (`AbortController` in `useRef`) |
| `frontend/src/copilot/CopilotDrawer.jsx` | `useState`, `useEffect`, `useRef` | Local UI state + scroll-into-view via ref |
| `frontend/src/lib/useFocusTrap.js` | `useEffect` | Effect cleanup pattern — restore focus on unmount |
| `frontend/src/lib/useDocumentMeta.js` | `useEffect` | DOM-mutating effect with multiple deps |
| `frontend/src/components/architecture/FlowDiagram.jsx` | `useMemo` (x4) | Memoization for expensive derived data |
| `frontend/src/components/admin/DuplicateEventDrawer.jsx` | `useState` (x5), `useEffect`, `useMemo` | Drawer reset on `open` flip; conflict-set memo |
| `frontend/src/state/useAuth.js` | `useContext` | Custom hook wrapping context with a guard |

Patterns to lift from these files:

- **Stable context payload via `useMemo`** — see `authContext.jsx`.
  Without the memo, every consumer of `AuthContext` would re-render
  whenever `AuthProvider` itself re-rendered for any reason.
- **Mutable handle via `useRef`** — see `useCopilotStream.js`. The
  `AbortController` lives in `useRef` because mid-stream `cancel()`
  must read the *current* controller, not a stale closure, and
  writing it shouldn't trigger a re-render.
- **Effect cleanup that restores prior state** — see
  `useFocusTrap.js`. The cleanup function captures `previouslyFocused`
  from the same effect-run that attached the listener.
- **Reset-on-prop-change pattern** — see `DuplicateEventDrawer.jsx`.
  When a parent passes a new entity, an effect on `[open, entity?.id]`
  clears the form. Using the `.id` instead of the object avoids
  resetting on unrelated re-renders.

## Rules of hooks (enforced)

The two rules, taken verbatim from the React docs and the
`eslint-plugin-react-hooks` rule set:

1. **Only call hooks at the top level.** Don't call hooks inside
   loops, conditions, nested functions, or `try`/`catch`/`finally`
   blocks. The hook list on the fiber is positional; any conditional
   call shifts the list and corrupts subsequent reads.
2. **Only call hooks from React function components or other custom
   hooks.** Calling a hook from a regular utility function, an event
   handler, or a class component is an error — there's no current
   fiber to attach state to.

Custom hooks are functions whose name starts with `use` and which
call other hooks. The naming convention is what the linter looks for.
A custom hook is *not* a shared instance — every component that calls
`useFoo()` gets its own fiber slots. That's why two components using
`useAuth()` don't conflict: each has its own `useContext` slot
pointing at the same shared context value.

## Render and commit phases

A React update unfolds in two phases:

**Render phase (pure, interruptible).** React calls each affected
component function, walks its hook list, and produces a new fiber
tree. Concurrent React may abort and retry this phase if a higher-
priority update arrives. Because of that, your render function must
be a pure function of props + state — no side effects, no DOM reads,
no `Math.random()` based on the call count.

**Commit phase (synchronous, side-effectful).** Once the render phase
produces a tree React is happy with, React commits it to the DOM in
one synchronous pass. Within commit, React runs:

1. DOM mutations (insert/update/delete nodes).
2. `useLayoutEffect` cleanups from the previous commit.
3. `useLayoutEffect` setups for the new commit.
4. Yields to the browser (paint can happen).
5. Schedules passive effects.

Passive effects (`useEffect`) run shortly after paint, in a separate
task. This is why a `useEffect` that measures the DOM might see a
correct layout, but a brief visual flicker is possible — the paint
happened before the effect ran. Use `useLayoutEffect` if you need to
mutate the DOM before paint to avoid the flicker, at the cost of
blocking the main thread until the effect returns.

## Operational concerns

**Performance.**

- `useMemo` and `useCallback` are not free — they store a dep array
  and run an equality check every render. Use them when (a) the cached
  computation is more expensive than `Object.is` over the deps, or
  (b) the cached identity is consumed by a downstream memoized child or
  hook dep array.
- Re-renders cascade by default. To bound a re-render, wrap the child
  in `React.memo` and ensure its props are referentially stable.
- Context propagation does not respect `React.memo`. Any consumer of a
  context re-renders when the provider's `value` identity changes,
  even if the consumer is otherwise memoized.

**Debugging.**

- React DevTools → Profiler tab. Record a session, click a commit, see
  which components re-rendered and why. "Why did this render?" is
  available behind a setting.
- React DevTools → Components tab → click a component → the right
  panel shows each hook's current value and lets you edit `useState`
  values live.
- For stale-closure bugs, log `useRef`s. For dep-array bugs, log the
  effect body's `Date.now()` or a sequence number.

**Common production bugs.**

- *Stale closures in event handlers attached via `useEffect` with
  empty deps.* The handler captures the first render's state. Fix:
  functional setters or refs.
- *Memory leaks from unsubscribed listeners / un-aborted fetches.*
  Always return a cleanup from `useEffect`. In dev, Strict Mode's
  double-mount surfaces these as duplicate listeners or duplicate
  network requests.
- *Out-of-order async results.* Effect fires for prop A, then prop B,
  then prop C — but A's promise resolves last and overwrites state.
  Fix with an `AbortController` (`useCopilotStream.js` is the
  exemplar) or a `let cancelled = false` flag in the cleanup.
- *Infinite re-render loops.* Usually caused by setting state
  unconditionally in the component body, or by depending on an object
  literal in an effect's deps.
- *Strict Mode double-fetch.* In dev, `useEffect(() => {
  fetch(...); }, [])` fires twice. Either dedupe at the data layer
  (React Query handles this) or abort in cleanup.

## Glossary

- **Fiber** — React's internal node representing a component instance.
  Stores `memoizedState`, `pendingProps`, `child`, `sibling`, `return`.
- **Hook node** — One entry in the fiber's linked list of hook state.
- **Render phase** — React calls component functions and builds a new
  fiber tree. Must be pure and interruptible (Concurrent Mode).
- **Commit phase** — React applies the diff to the DOM and runs
  layout effects synchronously, then schedules passive effects.
- **Passive effect** — `useEffect` callback. Runs asynchronously after
  paint.
- **Layout effect** — `useLayoutEffect` callback. Runs synchronously
  after DOM mutation, before paint.
- **Dependency array** — The list React compares with `Object.is`
  to decide whether to re-run an effect or invalidate a memo.
- **Exhaustive deps** — ESLint rule
  (`react-hooks/exhaustive-deps`) requiring every closed-over variable
  to appear in the deps array.
- **Stale closure** — A function reading a variable captured from a
  previous render after the component re-rendered with a new value.
- **Functional updater** — `setState(prev => next)` form that reads
  the queued state instead of the captured closure value.
- **Automatic batching** — React 18 behavior of collapsing multiple
  `setState` calls in one tick into a single render, regardless of
  whether the originating event was React-managed.
- **Strict Mode** — Dev-only wrapper (`<React.StrictMode>`) that
  double-invokes render functions and effects to surface bugs.
- **Concurrent rendering** — Render work that can be paused, aborted,
  or restarted at a different priority. Enabled by
  `createRoot`, `useTransition`, `useDeferredValue`.
- **Hook dispatcher** — Internal React module that swaps the
  implementation of `useState` etc. based on whether we're in a
  mount, an update, or outside a render.
- **`Object.is`** — The equality used to compare dep array entries.
  Differs from `===` only for `NaN` and `-0` vs `+0`.
- **`useReducer`** — `useState` with a reducer; same fiber slot type,
  different ergonomics.
- **`useImperativeHandle`** — Customize what a parent sees on a
  forwarded ref. Rarely the right tool.
