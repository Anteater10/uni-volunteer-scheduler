# React Context API — Reference

The Context API (`React.createContext` + `<Ctx.Provider>` +
`useContext`) is the built-in mechanism for sharing values across a
component tree without prop drilling. It is a *transport*, not a state
store: there is no selector, no middleware, and every consumer
re-renders whenever the provider's `value` identity changes. Use it
for low-frequency, broad-fanout state (auth, theme, locale). Reach for
a store library (Redux/Zustand/Jotai) or a server-state library
(React Query) for higher-frequency state or remote data.

## API surface

```ts
function createContext<T>(defaultValue: T): Context<T>;

interface Context<T> {
  Provider: ProviderExoticComponent<ProviderProps<T>>;
  Consumer: ExoticComponent<ConsumerProps<T>>;
  displayName?: string;
}

interface ProviderProps<T> {
  value: T;
  children?: ReactNode;
}

function useContext<T>(context: Context<T>): T;

// React 18.3+ — Suspense-aware reader, callable conditionally
function use<T>(context: Context<T>): T;
```

Notes:

- `defaultValue` is what consumers see when no Provider is mounted
  above them. It is **not** an initial state. A Provider's `value`
  replaces the default, not extends it.
- The `Consumer` render-prop component (`<Ctx.Consumer>{v => ...}</Ctx.Consumer>`)
  predates `useContext`. New code should always use `useContext`.
- Context values are compared with `Object.is`. Equal values cause no
  re-render.
- `Context.displayName` controls how the context appears in React
  DevTools — useful when you have several anonymous contexts.

## Mental model

**A context is a channel.** `createContext` declares the channel.
`<Provider value={x}>` pushes a value onto the channel for the
subtree rendered inside it. `useContext` reads the current value on
the channel from any descendant. Each consumer fiber registers as a
dependent on its first read; React re-renders every dependent fiber
whenever the channel's value changes by `Object.is`.

**Key invariants:**

1. Every consumer re-renders on `value` change, regardless of
   `React.memo` on the consumer's props.
2. `value` identity matters — `value={{ x }}` creates a new object
   every render. Memoize the value or accept the fan-out.
3. The Provider can be nested: an inner Provider shadows an outer one
   for its subtree. Sibling Providers don't see each other.
4. Server Components and Client Components see different contexts.
   Server Components cannot read a context that was set by a Client
   Component Provider.

**When to use Context:**

- Client state that is read in many places but written rarely.
- Identity, theme, locale, feature flags, current tenant.
- Dependency injection of services (logger, analytics) into a tree.

**When to reach for something else:**

- High-frequency updates → Zustand, Jotai, Valtio.
- Server data → React Query, SWR, RSC + cache.
- Complex reducers with middleware/devtools → Redux Toolkit.
- A single value that only one subtree uses → just lift state up.

## Usage in this codebase

| File | Role |
|---|---|
| `frontend/src/state/AuthContext.js` | The context object — `createContext(null)` |
| `frontend/src/state/authContext.jsx` | The Provider — wraps app with auth state + memoized value |
| `frontend/src/state/useAuth.js` | Consumer hook — throws if Provider missing |
| `frontend/src/main.jsx` | Provider stack at root: QueryClient, Router, Auth, StrictMode |
| `frontend/src/components/Layout.jsx` | Consumer — reads `useAuth()` for nav rendering |
| `frontend/src/components/ProtectedRoute.jsx` | Consumer — gates routes on `isAuthed` + `role` |
| `frontend/src/copilot/CopilotFab.jsx` | Consumer — hides Copilot trigger when unauthed |
| `frontend/src/pages/admin/AdminLayout.jsx` | Consumer + uses Outlet context for nested routes |

The repo deliberately uses Context only for the auth session. Every
other piece of "global state" lives elsewhere:

- **Server data** (events, users, modules, broadcasts) → React Query
  (`@tanstack/react-query`).
- **URL state** (filters, current event) → React Router params and
  search params.
- **Per-page UI state** (drawer open, form fields) → local
  `useState`.

This stratification keeps re-renders local. Editing an event detail
doesn't re-render the entire authed tree, because the event detail
isn't in Context.

The Provider value is memoized:

```jsx
const value = useMemo(
  () => ({ user, initializing, isAuthed: !!user,
           role: user?.role || null,
           reloadMe, login, register, logout }),
  [user, initializing]
);
```

The consumer hook guards against missing Provider:

```jsx
export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
```

## Provider patterns

**Single Provider per concern.** Define one context per logical
concern: auth, theme, locale, feature flags. Don't bundle.

**Co-locate Provider and consumer hook.** Standard layout:

```
src/state/
  AuthContext.js          ← createContext + default
  authContext.jsx         ← AuthProvider component
  useAuth.js              ← useContext wrapper hook
```

The context object lives in its own file so the Provider and the
hook can both import it without circular dependencies. The hook
adds a Provider-missing guard so consumers don't have to null-check.

**Memoize the value.** Always:

```jsx
const value = useMemo(() => ({ x, y, setX, setY }), [x, y]);
return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
```

Setters from `useState` are stable, so they don't need to be in
the deps array.

**Split state and dispatch.** For larger contexts, isolate the
reducer's dispatch (stable) from its state (changing):

```jsx
const [state, dispatch] = useReducer(reducer, initial);
return (
  <StateCtx.Provider value={state}>
    <DispatchCtx.Provider value={dispatch}>
      {children}
    </DispatchCtx.Provider>
  </StateCtx.Provider>
);
```

Components that only need `dispatch` never re-render. Components
that need both subscribe to both.

**Set `displayName`** for DevTools clarity:

```jsx
export const AuthContext = createContext(null);
AuthContext.displayName = "Auth";
```

## Re-render rules

A consumer of a context re-renders when:

1. The provider's `value` prop changes by `Object.is`.
2. The consumer's own parent re-renders and React re-renders it as
   part of normal reconciliation (the standard prop/state path).

A consumer does **not** re-render when:

1. The provider re-renders but `value` is referentially equal.
2. A sibling consumer re-renders.
3. The consumer is wrapped in `React.memo` *and* its parent's
   re-render didn't change its props — *unless* the context value
   changed, which bypasses the memo.

The last bullet is the most common source of confusion. `React.memo`
guards against parent-driven re-renders, not context-driven ones.

## Operational concerns

**Performance.**

- Profile with React DevTools → Profiler. A context change shows up as
  every consumer flashing in the commit view.
- If you see a context update re-rendering hundreds of components,
  either (a) split the context into smaller pieces, (b) move to a
  store with selectors, or (c) introduce
  `use-context-selector` for the hottest consumers.
- Don't put React Query results in Context. React Query already does
  this — its hooks subscribe to a shared cache and only re-render
  consumers whose specific query changed.

**Debugging.**

- Set `Context.displayName = "Auth"` so DevTools shows a name instead
  of `Context.Provider`.
- Inspect a context's value in DevTools → Components → click the
  Provider node → right panel shows the current `value`.
- For "why did this component re-render?", enable the highlight-update
  setting in DevTools. Context-driven re-renders show up just like
  prop-driven ones.

**Testing.**

- Components that call `useAuth()` need an `AuthProvider` in tests,
  or you mock the hook. This repo uses both patterns — see
  `frontend/src/pages/admin/__tests__/AdminLayout.test.jsx` for the
  mock approach.
- For Provider tests, render the Provider with a known value and
  assert children behavior:
  ```jsx
  render(
    <AuthContext.Provider value={{ user: { role: 'admin' }, isAuthed: true }}>
      <ComponentUnderTest />
    </AuthContext.Provider>
  );
  ```

**Common production bugs.**

- *New object literal in `value` causes everything to re-render.*
  Add `useMemo`.
- *Context bundles auth + theme + locale + sidebar state.* Split
  contexts.
- *Hook throws "must be used inside Provider" in storybook/tests.*
  Provide a Provider in the story setup, or expose a `MockAuthProvider`
  helper.
- *Server data in Context goes stale.* Replace with React Query.
- *Re-rendering a list of 500 rows on every theme toggle.* Either
  memoize each row with `React.memo` and pull theme inside the row
  (no help — context still re-renders), or pass theme as a CSS
  variable / class on a root element so React doesn't need to
  re-render at all.

## Glossary

- **Provider** — Component that pushes a value onto a context's
  channel for its subtree.
- **Consumer** — A component that calls `useContext(Ctx)` or renders
  `<Ctx.Consumer>`. Re-renders on every value change.
- **`defaultValue`** — Argument to `createContext`. Used only when no
  Provider is mounted above the consumer.
- **Prop drilling** — Passing a prop through intermediate components
  that don't use it, just to reach a deeper descendant. Context's
  primary motivation.
- **Fan-out re-render** — When one context update re-renders many
  consumers because the provider value changed by reference.
- **Selector** — A function that picks a slice of state. Stores
  (Zustand, Redux) support selectors; raw Context does not.
- **Split state/dispatch** — Pattern of putting state in one context
  and the dispatch/setters in another so components that only
  trigger updates don't re-render on state changes.
- **`use-context-selector`** — Third-party library that adds
  selector-based subscription to React Context, avoiding fan-out
  re-renders.
- **`useSyncExternalStore`** — React 18 hook for subscribing to
  external stores with concurrent-mode safety. The lower-level API
  most store libraries are built on.
- **Server state** — Data owned by a server (lists, records, search
  results). Should live in a server-state cache (React Query, SWR),
  not Context.
- **Client state** — Data owned by the client (auth identity, theme,
  draft form input). Context is appropriate for the slow-changing
  subset of this.
- **`Object.is`** — Equality React uses to compare a context's old
  and new value. Differs from `===` only on `NaN` and `±0`.
- **`Context.displayName`** — Optional string that controls how the
  context shows up in React DevTools. Set it.
