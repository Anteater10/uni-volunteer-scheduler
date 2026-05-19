# The React Context API

The Context API is React's built-in answer to prop drilling. It's also
one of the most over-used and over-blamed primitives in the ecosystem —
candidates routinely either reach for it as a global state library
(painful) or refuse to use it on the grounds that "Context is slow"
(superstition). This lecture is about getting the trade-offs right.
You should walk out able to answer "why not just use Context?" and
"why not Redux?" in the same conversation.

## The design choice

Before Context (or before it was a stable public API in 16.3), passing
data deep into a component tree meant **prop drilling**: every
intermediate component had to declare and forward a prop it didn't
care about.

```jsx
// Prop drilling — Page has no business knowing about `user`,
// it just forwards it.
<App user={user}>
  <Page user={user}>
    <Header user={user}>
      <Avatar user={user} />
    </Header>
  </Page>
</App>
```

This works fine for one or two levels. It becomes hostile at five or
six, especially during refactors when a new dependency means
threading a prop through ten files.

The alternatives in 2026 are:

1. **React Context** — built-in, no extra library, zero-config.
2. **A store library** — Redux (Toolkit), Zustand, Jotai, Recoil,
   Valtio, MobX. Each exposes a subscribable store; components
   selectively read slices and only re-render when their slice changes.
3. **A server state library** — React Query, SWR, Apollo. Not really
   "state management" — they cache and synchronize remote data, but
   they replace a huge fraction of what people used to put in
   Context.
4. **Just lifting state up** — sometimes the right answer is to
   move state to a closer common ancestor and accept the drilling.

React Context picks a deliberate trade-off: every consumer subscribes
to the entire provider value. There's no selector. When the provider's
`value` changes by reference, every consumer re-renders. This is
fine for low-frequency, broad-fanout data (auth state, theme, locale).
It's a footgun for high-frequency or large-object state (a typing
indicator, a complex form). The library ecosystem exists precisely
because Context isn't trying to be a store.

Pros of Context: no dependency, no boilerplate, integrates with
Suspense and Server Components, easy to test. Cons: no selector
support (without `useSyncExternalStore` gymnastics), fan-out
re-renders, no devtools, no middleware story.

## How it works under the hood

`createContext(defaultValue)` returns an object with two fields:
`Provider` and `Consumer`. Internally each context has a unique
identifier. The fiber tree maintains a "context stack" per context —
when React walks down and encounters a `<MyCtx.Provider value={v}>`,
it pushes `v` onto that context's stack. When it walks back up
(commit phase, sibling traversal), it pops.

`useContext(MyCtx)` does two things at the consumer:

1. Reads the current top of the context's stack.
2. Registers the consumer fiber as a dependent. When the context's
   value changes by `Object.is`, React schedules a re-render on every
   dependent fiber.

Crucially, `React.memo` does **not** prevent context-triggered
re-renders. The memo only short-circuits when *props* are
referentially equal. Context updates bypass the prop comparison and
re-render the consumer regardless.

The "fan-out re-render" problem follows from this design. If your
provider's value is `{ user, setUser, theme, setTheme, locale,
setLocale }` and you change locale, every component that reads
anything from this context re-renders, even ones that only care
about `user`. The standard mitigation is to split contexts:

```jsx
<UserContext.Provider value={userPayload}>
  <ThemeContext.Provider value={themePayload}>
    <LocaleContext.Provider value={localePayload}>
      <App />
    </LocaleContext.Provider>
  </ThemeContext.Provider>
</UserContext.Provider>
```

A second standard pattern is to **split state and dispatch**:

```jsx
<StateContext.Provider value={state}>
  <DispatchContext.Provider value={dispatch}>
    {children}
  </DispatchContext.Provider>
</StateContext.Provider>
```

Components that only need `dispatch` (which is stable across renders)
never re-render when state changes. Components that need both opt in.

React 18 added the experimental `use(Context)` hook, which works the
same as `useContext` but is also callable inside `if` blocks — it's a
suspense-aware reader. Not widely deployed yet.

## How this codebase uses it

### 1. `frontend/src/state/AuthContext.js` — the context object itself

The cleanest possible declaration:

```jsx
import { createContext } from "react";
export const AuthContext = createContext(null);
```

`null` is the default value — what consumers see if no Provider is
mounted above them. The codebase deliberately uses `null` rather than
a "fake" auth object, because the custom hook (next file) treats
`null` as "Provider missing" and throws. This is the canonical
pattern: a context object lives in its own file so the Provider and
the consumer hook can import it without circular references.

### 2. `frontend/src/state/useAuth.js` — the consumer hook

```jsx
import { useContext } from "react";
import { AuthContext } from "./AuthContext";

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
```

This is a textbook *protected consumer*: the hook throws if a
Provider isn't mounted. The benefit is that downstream code can
treat the return type as non-null without optional chaining
everywhere. The cost is that tests need to either wrap components in
`AuthProvider` or mock the hook.

### 3. `frontend/src/state/authContext.jsx` — the Provider

```jsx
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [initializing, setInitializing] = useState(true);

  // ... reloadMe / login / register / logout ...

  const value = useMemo(
    () => ({ user, initializing, isAuthed: !!user,
             role: user?.role || null,
             reloadMe, login, register, logout }),
    [user, initializing]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
```

Two important details. First, the `value` is wrapped in `useMemo`.
Without it, every render of `AuthProvider` would create a new object,
and every `useAuth()` consumer would re-render. Second, `login`,
`register`, `logout` are functions defined inline in the component
body — they close over `setUser` (stable) and `api` (module-level,
stable), so they're safe to leave out of the deps array, though a
stricter codebase would wrap them in `useCallback`.

### 4. `frontend/src/main.jsx` — Provider composition at the root

```jsx
<React.StrictMode>
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  </QueryClientProvider>
</React.StrictMode>
```

The provider stack at the root: React Query (server state),
React Router (routing context), Auth (app state), Strict Mode for
dev. Note how this codebase splits *server state* (React Query) from
*app state* (Auth context). Server state — the list of events, the
current user's profile — lives in React Query's cache, not in
Context. Context only holds the *identity-and-session* state.

### 5. Consumers — `Layout.jsx`, `ProtectedRoute.jsx`, page components

```jsx
// frontend/src/components/ProtectedRoute.jsx (sketch)
const { isAuthed, initializing, role } = useAuth();
if (initializing) return <Spinner />;
if (!isAuthed) return <Navigate to="/login" replace />;
```

Most consumers destructure the few fields they need. The destructure
doesn't change re-render behavior — they still re-render whenever
`value` changes — but it documents intent and makes the dependency
explicit for code review.

## Common pitfalls

**Forgetting `useMemo` on the Provider value.**

```jsx
// Bug — new object every render → every consumer re-renders
return <Ctx.Provider value={{ user, login }}>{children}</Ctx.Provider>;
```

In code review, any inline `value={{...}}` on a Provider is a smell
unless the component itself never re-renders.

**Using Context for high-frequency state.**

A mouse-position context, a typing indicator, a scroll-position
context — these will re-render every consumer on every update. The
correct tool is `useSyncExternalStore` with a store you can
selector-subscribe to, or a library like Zustand. Context is for
identity, theme, locale, feature flags — slow-changing, broad-fanout.

**Putting too many concerns in one context.**

```jsx
const value = { user, theme, locale, sidebarOpen, modalStack, toasts };
```

Splitting this into separate contexts (or moving most of it to a
store) limits the re-render blast radius.

**Throwing in the consumer with no fallback for tests.**

```jsx
if (!ctx) throw new Error("missing provider");
```

Great in production, painful in tests. Either wrap test renders in
the provider, or accept `null` and document the fallback.

**Confusing `defaultValue` with "initial value".** The default is
what consumers see when *no Provider* is mounted. It is not an
initial state. Setting `createContext({ user: null })` does not give
you a user — it gives anything outside a Provider an object with
`user: null`.

**Assuming `React.memo` blocks context re-renders.** It doesn't. The
consumer re-renders on context change even if its props are the
same. If you need to dodge that, use a selector hook
(`useContextSelector` from the `use-context-selector` library) or
move to a store.

In code review, watch for: Providers without `useMemo`, contexts
that bundle stable and unstable state together, consumers in tight
render loops (lists with hundreds of items each calling
`useContext`), and contexts that should really be React Query
queries.

## Interview Q&A

**Q (junior):** What problem does the Context API solve?

A: Prop drilling — the need to pass data through layers of
components that don't use it themselves, just to reach a descendant
that does. Context lets the descendant read directly from a value
provided higher in the tree, without intermediate components knowing
about it. The canonical examples are the current user, the theme,
and the locale.

```jsx
const ThemeCtx = createContext('light');
function App() {
  return <ThemeCtx.Provider value="dark"><Page /></ThemeCtx.Provider>;
}
function DeepChild() {
  const theme = useContext(ThemeCtx);
  return <div className={theme}>...</div>;
}
```

**Q (junior):** Why is the Provider's `value` usually wrapped in
`useMemo`?

A: Because every `useContext` consumer re-renders whenever the
provider's `value` changes by reference (`Object.is`). If you write
`<Ctx.Provider value={{ a, b }}>`, you create a new object literal
each time the provider re-renders, and *all* consumers re-render even
when `a` and `b` are unchanged. Wrapping in `useMemo` stabilizes the
identity:

```jsx
const value = useMemo(() => ({ a, b }), [a, b]);
return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
```

**Q (mid):** When would you choose Redux or Zustand over Context?

A: Three signals push me toward a store. (1) **Selector support** —
when many consumers need different slices of one big state object
and I want each to re-render only for its slice. Context doesn't
have selectors; stores do. (2) **High update frequency** — typing
indicators, animations, a drag handle's position. Context's
fan-out re-render makes this expensive. (3) **Middleware / devtools
/ persistence** — Redux DevTools, time-travel, persist middleware,
RTK Query. Context has none of these. If I have a single stable
value that changes rarely and is read across many components (auth,
theme), Context is the right tool and adding a store is overkill.

**Q (mid):** What's the difference between Context and server-state
libraries like React Query?

A: They solve different problems. Context is a transport for
*client-owned* values — auth identity, UI preferences, feature
flags. React Query is a *cache* for values that live on a server —
the list of events, a user's profile, a search result. React Query
handles fetching, caching, deduping, background revalidation, stale
time, and pagination. Putting server data in Context is a common
anti-pattern that ends with you reimplementing React Query badly. In
this codebase, `AuthContext` carries the session identity, while
`/api/v1/events` results live in React Query.

**Q (mid):** How do you avoid re-rendering every consumer when the
provider's state changes?

A: Three techniques, in order of effort. (1) **Split contexts** —
move unrelated state into separate Providers so consumers of one
don't re-render when the other changes. (2) **Split state and
dispatch** — put state in one context and `dispatch`/setters
(which are stable) in another. Components that only need to
*trigger* changes never re-render. (3) **Use a selector library**
(`use-context-selector`) or move to a store with selector support.
The library forks React's internal subscription model to let you
pass a function that picks a slice.

**Q (mid):** What's the `defaultValue` argument to `createContext`
for?

A: It's the value `useContext` returns when there is *no Provider*
of that context anywhere above the consumer in the tree. It's not
an initial value — mounting a Provider with `value={something}`
doesn't inherit from the default; it replaces it. The default is
mostly useful for testing in isolation (you can render a component
without wrapping it in a Provider) and for components that
legitimately work standalone, like a "headless" component that
falls back to sensible defaults when no Provider is configured.

**Q (senior):** Walk me through what happens at the fiber level when a
context value changes.

A: The Provider component re-renders with a new `value`. React
compares the new `value` to the previous one using `Object.is`. If
they're equal, nothing happens. If they're not, React schedules a
re-render on every fiber that registered as a consumer of this
context. The consumer list is maintained as React walks the tree —
when `useContext(Ctx)` runs during a fiber's render, React records
that fiber on `Ctx`'s consumer list. When the value changes, React
iterates that list and marks each consumer fiber with a pending
update. On the next render pass, React re-renders each consumer
even if its parents didn't re-render. This is why `React.memo`
doesn't help — the consumer is re-rendered by the context channel,
not by its parent's diff.

**Q (senior):** How would you implement `useContextSelector` and why
isn't it in React core?

A: The trick is to subscribe to the context with a *selector*
function and bail out of the re-render when the selected slice is
referentially equal to the previous one. A sketch:

```jsx
function useContextSelector(Ctx, selector) {
  const value = useContext(Ctx);
  const selected = selector(value);
  const ref = useRef(selected);
  // Force a re-render only when the selected slice changed
  const [, forceRender] = useReducer(c => c + 1, 0);
  useEffect(() => {
    if (!Object.is(ref.current, selected)) {
      ref.current = selected;
      forceRender();
    }
  });
  return ref.current;
}
```

This naive version still re-renders on every context change before
bailing — the real implementation
(`use-context-selector`) intercepts at a lower level by reading the
fiber's context dependencies directly and short-circuiting before
the render commits. It's not in React core because the React team
prefers context-splitting as the official answer and is wary of an
API that encourages putting too much in one context. Server
Components and the new `use(Context)` API are the React team's
direction instead.

**Q (senior):** When does Context NOT solve prop drilling?

A: When the data is *server data*. If you find yourself prop-
drilling `events` from a parent that fetched it down to a grandchild
that displays it, the answer is usually "the grandchild should
fetch (or `useQuery`) it itself," not "wrap it in a Context." React
Query and friends dedupe parallel calls and cache results — the
grandchild's `useQuery(['events'])` will hit the same cache entry
the parent did, with no extra request. Context for server data
creates a coupling that's worse than the prop drilling it
replaced. Context for client state — identity, theme, locale —
remains the right tool.

## Further reading

- React docs — `createContext`:
  <https://react.dev/reference/react/createContext>
- React docs — Passing Data Deeply with Context:
  <https://react.dev/learn/passing-data-deeply-with-context>
- "Before You memo()" by Dan Abramov:
  <https://overreacted.io/before-you-memo/>
- `use-context-selector` (subscription-based selector for Context):
  <https://github.com/dai-shi/use-context-selector>
