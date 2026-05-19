# React Router: Nested Routes, Outlets, and Protected Routes

This is a lecture for interview prep on React Router v6/v7. The objective is to be able to whiteboard a route tree, explain how URL matching turns into a rendered component, and justify the ProtectedRoute pattern against the obvious alternatives. The codebase we work in (uni-volunteer-scheduler) uses `react-router-dom@7.11`, but everything below applies to v6+ since v7 in non-framework mode is essentially v6 with the marketing rename.

If you can answer "what renders when I navigate to `/admin/users` and the user is not signed in?" in 90 seconds with a coherent walkthrough of route ranking, layout routes, the `<Outlet />`, the gating component, and `<Navigate replace>`, you have passed the React Router portion of the interview.

## The design choice

React Router is a **declarative** routing library. You describe a tree of routes as JSX, the library walks the tree against the current URL, picks the best match, and renders the corresponding component. The alternative is **imperative** routing (the original 2014-era React Router 1.x, or hand-rolled `window.location` switches) where you write `if (path === '/users') return <Users />` and chain it.

Declarative routing wins because:

1. **Composition.** A `<Route>` can render a layout that itself contains an `<Outlet />`. The child route fills the outlet. You get nested layouts for free.
2. **Inspectability.** The whole route map is one file (in this codebase, `frontend/src/App.jsx`). You can read it like a sitemap.
3. **Code-splitting boundaries.** Each `<Route element={...} />` is a natural lazy-load point. With `React.lazy` + `<Suspense>`, you split the bundle on URL.
4. **Cross-cutting concerns become wrapper routes.** Auth, role-gating, layout chrome — all expressed as parent routes whose `element` wraps an `<Outlet />`.

### Alternatives worth naming in interviews

- **Next.js App Router.** File-system routing. `app/admin/users/page.jsx` is the route. Cross-cutting layouts are `layout.jsx` files. Server Components are first-class. The mental model is similar (nested layouts, outlets) but the routes come from the directory tree, and there is a server component / client component split. If the interviewer asks "why not Next?" the honest answer is: Next is the right call for new product greenfield in 2026, but React Router still wins for SPAs that don't want a server, embedded dashboards, Electron, and React Native Web.
- **TanStack Router.** Type-safe params, file-based routing, integrates with TanStack Query. Newer, less battle-tested in interviews.
- **Wouter.** ~2kb hooks-only router. Good for embedded widgets. No data loaders.
- **Hand-rolled.** A `useState` for the path and a `switch`. Fine for a 3-page demo, falls apart the moment you need nested layouts or back-button behaviour.

### Pros and cons of React Router

Pros: huge ecosystem, stable mental model since v6, supports data loaders (v6.4+) for the "remix-style" data router, works in SPA mode without a server, well-typed in v7.

Cons: the v5 → v6 → v7 churn ate a lot of community trust; data loaders are great but only if you use `createBrowserRouter` (the new API), and the older `<BrowserRouter>` + `<Routes>` API you see in this codebase does not give you loaders. So most teams who adopted React Router pre-2023 are running an older mental model than the docs assume.

## How it works under the hood

### Step 1: history

`react-router-dom` wraps the browser History API (`pushState`, `replaceState`, `popstate`). The `<BrowserRouter>` at the top of `main.jsx` subscribes to history changes and exposes a `location` object via context. When you call `useNavigate()` and invoke `nav("/admin")`, that is `history.pushState` plus a notification to subscribers. When the user clicks the back button, that is `popstate`.

A second variant, `<HashRouter>`, uses `#/admin` URLs and the `hashchange` event. Useful for static hosts that can't rewrite arbitrary paths to `index.html`. A third, `<MemoryRouter>`, holds the location in memory only — that is what tests use.

### Step 2: route ranking and matching

When `location.pathname` changes, the router walks the route tree, generates every leaf path by concatenating parent segments, and ranks the candidates. The ranking algorithm is roughly:

1. Static segments (`/admin/users`) outrank dynamic segments (`/admin/:id`).
2. Dynamic segments outrank splats (`/admin/*`).
3. Longer specific paths outrank shorter ones.
4. The first equally-ranked match wins (so order matters when two paths have the same rank — but the ranker handles most ambiguity, you rarely fight it).

This is why you can write `<Route path="events" />` and `<Route path="events/:eventId" />` as siblings and not worry about ordering: the static-vs-dynamic ranking handles it.

### Step 3: rendering the matched chain

Matching does not produce a single component — it produces a **chain** from the root layout down to the leaf. The router renders the chain by:

```
<RootLayout>
  <Outlet>           // renders the next level
    <AdminLayout>
      <Outlet>       // renders the next level
        <UsersAdminPage />
      </Outlet>
    </AdminLayout>
  </Outlet>
</RootLayout>
```

Every parent route with an `element` that renders an `<Outlet />` is a **layout route**. It contributes wrapper UI (sidebars, headers, modals) without owning the leaf URL. The leaf's URL is the concatenation of every `path` from the root to the leaf.

A route with no `path` at all (just `<Route element={<ProtectedRoute />}>...children</Route>`) is a **pathless layout route** — it contributes wrapping behaviour (in our case, auth gating) without consuming any URL segment. This is how `ProtectedRoute` slots into the tree without adding a `/protected/` prefix.

### Step 4: hooks read from context

`useLocation()`, `useNavigate()`, `useParams()`, `useSearchParams()`, and `useMatches()` all read from the same React context the router provides. `useParams()` returns the dynamic segments from the matched route only (so a leaf at `/admin/events/:eventId` sees `{ eventId: "abc" }`).

### Data loaders (v6.4+) — know this exists

If you call `createBrowserRouter` instead of using `<BrowserRouter>` + `<Routes>`, every route can declare a `loader` function. The router calls loaders **in parallel** before rendering the matched route, waterfall-free. The leaf component reads data via `useLoaderData()`. This solves the "render-fetch-render" waterfall you get from `useEffect`-based fetching.

This codebase does **not** use loaders — it uses TanStack Query inside components. That is fine, but it is a v6.0-style architecture, not the v6.4+ "data router" architecture. In an interview, say: "we use the declarative router with TanStack Query for data; the v6.4 data router with loaders is an alternative that pushes data fetching into the route definition for parallel prefetch and back-button cache."

### A note on v7 vs v6

`react-router-dom@7` (this codebase) ships in two modes. The "framework mode" is essentially Remix — it adds server-side rendering, file-based routing, and treats your route tree as a build artifact. The "library mode" is what we use here: identical to v6 in practice. The `<BrowserRouter>` + `<Routes>` API works, hooks work, layout routes work. The interview-relevant differences from v6 are mostly cosmetic: types are tighter, a few deprecated APIs were removed. If someone asks "what changed in v7," the honest answer is: "library mode is a renamed v6.4+ with some cleanup; framework mode is Remix folded in."

## How this codebase uses it

The whole route tree lives in one file.

```jsx
// frontend/src/App.jsx
<Routes>
  <Route path="/" element={<Layout />}>
    <Route index element={<RootRoute />} />
    <Route path="login" element={<LoginPage />} />

    {/* Public participant routes (no auth) */}
    <Route path="volunteer" element={<EventsBrowsePage />} />
    <Route path="volunteer/events/:eventId" element={<EventDetailPage />} />

    {/* Legacy redirects */}
    <Route path="events" element={<RedirectEventsToVolunteer />} />
    <Route path="events/:eventId" element={<RedirectEventDetailToVolunteer />} />

    {/* Pathless layout route — wraps children in auth check */}
    <Route element={<ProtectedRoute roles={["organizer", "admin"]} />}>
      <Route path="notifications" element={<NotificationsPage />} />
      <Route path="profile" element={<ProfilePage />} />
    </Route>

    {/* Nested admin shell with another layout */}
    <Route element={<ProtectedRoute roles={["admin", "organizer"]} />}>
      <Route path="admin" element={<AdminLayout />}>
        <Route index element={<AdminIndexRoute />} />
        <Route path="events" element={<EventsSection />} />
        <Route path="events/:eventId" element={<AdminEventPage />} />
        {/* Admin-only nested inside organizer-or-admin */}
        <Route element={<ProtectedRoute roles={["admin"]} />}>
          <Route path="users" element={<UsersAdminPage />} />
          <Route path="audit-logs" element={<AuditLogsPage />} />
        </Route>
      </Route>
    </Route>

    <Route path="*" element={<NotFoundPage />} />
  </Route>
</Routes>
```

Note the **doubly-nested gating**: an outer `ProtectedRoute roles={["admin", "organizer"]}` lets both roles into the admin shell, but `/admin/users` lives inside a second `ProtectedRoute roles={["admin"]}` that excludes organizers. The two checks compose.

### The gating component itself

```jsx
// frontend/src/components/ProtectedRoute.jsx
import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "../state/useAuth";

export default function ProtectedRoute({ roles = null, children }) {
  const { initializing, isAuthed, role } = useAuth();

  if (initializing) return <div style={{ padding: 16 }}>Loading…</div>;
  if (!isAuthed) return <Navigate to="/login" replace />;

  if (roles && Array.isArray(roles) && roles.length > 0 && !roles.includes(role)) {
    return (
      <div style={{ padding: 16 }}>
        <h2>Forbidden</h2>
        <p>Your account does not have access to this page.</p>
      </div>
    );
  }

  if (children) return children;
  return <Outlet />;
}
```

Three things to call out:

1. **The `initializing` guard.** Without this, on first paint `isAuthed` is `false` (the token hasn't been hydrated from localStorage yet) and the user is bounced to `/login` even though they have a valid session. The `initializing` flag from the auth context blocks the redirect until hydration finishes. This is the single most common bug in real-world ProtectedRoute implementations.
2. **`<Navigate to="/login" replace />`.** The `replace` prop calls `history.replaceState`, not `pushState`. If you forget it, the back button from `/login` returns you to the protected URL, which redirects you back to `/login`, which... you get the idea. `replace` breaks the loop.
3. **Dual usage.** The component supports both `<ProtectedRoute><Child /></ProtectedRoute>` (wrapper form) and `<Route element={<ProtectedRoute />}><Route .../></Route>` (layout form). The `children ? children : <Outlet />` branch handles both.

### The outer Layout uses `useLocation`

```jsx
// frontend/src/components/Layout.jsx
const { pathname } = useLocation();
const isAdminRoute = pathname.startsWith("/admin");
const isOrganizerRoute = pathname.startsWith("/organizer");
const isParticipantRoute =
  pathname === "/" ||
  pathname.startsWith("/volunteer") ||
  pathname.startsWith("/events") ||
  ...
```

Layout reads the location to decide whether to show the admin sidebar, the participant bottom-nav, or nothing. This is fine but slightly smelly — a more "router-native" approach would be to put the participant routes and admin routes under different layout routes, so the layout component itself differs by URL. The current codebase uses one `<Layout>` for everything and branches inside. Both work.

### `useNavigate` for post-action redirects

```jsx
// frontend/src/pages/LoginPage.jsx
const nav = useNavigate();
async function onSubmit(e) {
  await login(email.trim(), password);
  nav("/admin");
}
```

`useNavigate` is the imperative escape hatch. You use it after a side-effect (login, save, delete) when you want to send the user somewhere new. Inside JSX you'd use `<Link>` or `<Navigate>`.

### `useSearchParams` for filter state

```jsx
// frontend/src/pages/AuditLogsPage.jsx
const [searchParams, setSearchParams] = useSearchParams();
const page = Math.max(1, parseInt(searchParams.get("page") || "1", 10) || 1);
const q = searchParams.get("q") || "";

function setPage(n) {
  const next = new URLSearchParams(searchParams);
  next.set("page", String(n));
  setSearchParams(next);
}
```

The pattern: filter state lives in the URL, not in `useState`. Benefits — deep-linkable filtered views, browser back/forward navigates between filter sets, refresh preserves filters. `useSearchParams` wraps the URL `?query=` portion in a React-style `[value, setter]` tuple.

### Active link styling via `NavLink`

```jsx
// frontend/src/pages/admin/AdminLayout.jsx
<NavLink
  to={to}
  end={end}
  className={({ isActive }) =>
    isActive ? "bg-slate-700 text-white" : "text-slate-300 hover:bg-slate-800"
  }
>
  {label}
</NavLink>
```

`NavLink` is `<Link>` with an `isActive` flag. The `end` prop means "active only when the URL is exactly this, not a prefix" — important for the "Overview" link at `/admin` because otherwise it would be active on `/admin/users` too.

## Common pitfalls

**1. Redirect loops in `ProtectedRoute`.** If `/login` itself is rendered inside a `ProtectedRoute` (because you forgot to lift it out), an unauthenticated user gets bounced to `/login`, which itself triggers the redirect, which bounces them again. Symptoms: blank page, infinite history entries, browser warning. Fix: keep auth-required and auth-not-required routes as sibling subtrees; never put `/login` under the protected subtree.

**2. Missing `replace`.** Without `<Navigate to="/login" replace />`, every unauthorized visit pushes a history entry. User clicks back, goes to the protected URL, redirects to `/login`, history fills up. Always `replace` on redirects.

**3. Hydration race on first paint.** Auth state isn't synchronously available — you read it from localStorage or a `/me` endpoint. If `ProtectedRoute` checks `isAuthed` before hydration, every refresh of a protected URL bounces the user to login. Fix: an `initializing` boolean from the auth provider that blocks rendering until the first auth check resolves.

**4. `useParams` returns strings.** A route `/events/:eventId` gives you `eventId: "42"`, not `42`. `eventId === 42` is `false`. If your API expects a number, coerce.

**5. Forgetting `<Outlet />` in a layout.** A layout route renders, but the child route doesn't appear. Fix: layout components must render `<Outlet />` somewhere in their JSX, otherwise the matched child has nowhere to go.

**6. Stale `useNavigate` in closures.** The `navigate` function is stable across renders, but if you capture it in a `useEffect` with the wrong deps you can still trip yourself up. Symptom: navigation works once and then stops. Usually a missing dep array fix.

**7. `<Link to="/foo">` vs `<a href="/foo">`.** An `<a>` tag triggers a full-page reload, losing all React state. Always use `<Link>` for internal navigation. Use `<a>` only for external URLs or download links.

**8. `index` vs `path=""`.** `<Route index element={...} />` matches when the parent path matches exactly with nothing after. `<Route path="" element={...} />` is similar but subtly different in nested scenarios. Prefer `index` — it is what the docs use and what mental-model-wise corresponds to "the home of this section."

**9. Wildcard `*` placement.** `<Route path="*" element={<NotFoundPage />} />` must be a sibling of your other routes at the same level, not nested inside one of them. If you nest it under `/admin`, you only get a 404 for `/admin/whatever`, not for `/whatever`.

**10. Memoizing `<Routes>` blocks updates.** Don't wrap your `<Routes>` element in `React.memo`. The router needs to re-render on location change; memo with no deps blocks that.

**11. Trailing slashes.** `/admin` and `/admin/` may or may not match depending on configuration. v6 treats them as equivalent for matching but the URL the user sees differs. Don't write code that depends on the trailing slash. If you need a canonical form, redirect.

**12. Layout components reading params from above.** `useParams` returns params from the **matched leaf**, not the level where you call it. If your `<AdminLayout>` is at `/admin` and the leaf is `/admin/events/:eventId`, calling `useParams()` inside `AdminLayout` does give you `eventId` — the hook walks the matched chain. But if you call it in `<Layout>` (the outer one above admin), you get an empty object because `Layout` is not in the route subtree that owns the param. Subtle, easy to miss in tests.

**13. State leak across route transitions.** Components above an `<Outlet />` don't unmount when the leaf changes. If `AdminLayout` holds a `useState` for "active section," that state survives navigation across `/admin/users` → `/admin/events`. Usually desired; sometimes a bug. If you need a clean slate per leaf, key the leaf component on the route key.

## Interview Q&A

**Q (junior): What is the difference between `<Link>` and `<a>`?**

`<a href="/foo">` causes the browser to do a full HTTP navigation — the whole React app unmounts, the next page reloads from scratch. `<Link to="/foo">` calls into the History API, updates the URL without a reload, and lets React Router swap the matched components. Use `<Link>` for any in-app navigation. Use `<a>` for external URLs or when you actually want a hard reload (e.g. logging out and clearing all client state cleanly).

**Q (junior): What does `<Outlet />` do?**

It is the placeholder where a layout route renders its matched child. If you have a `<Route element={<AdminLayout />}>` with nested routes inside it, `AdminLayout` must render `<Outlet />` somewhere in its JSX. When the URL matches a child route, the child component is rendered into that slot. Without `<Outlet />`, the layout displays but the child is invisible.

**Q (mid): Walk me through what happens when a logged-out user visits `/admin/users` in this app.**

The router matches `/admin/users` against the tree. The matched chain is: root `<Layout>` → pathless `<ProtectedRoute roles={["admin","organizer"]}>` → `<Route path="admin" element={<AdminLayout>}>` → pathless `<ProtectedRoute roles={["admin"]}>` → leaf `<UsersAdminPage>`.

Rendering starts top-down. `<Layout>` renders chrome and an `<Outlet>`. The outer `<ProtectedRoute>` reads `useAuth()`, sees `initializing: true`, returns a "Loading…" div, and renders nothing else this paint. Auth hydration completes, `isAuthed` becomes `false`, the component returns `<Navigate to="/login" replace />`. The router catches that, replaces the history entry, re-runs matching against `/login`, finds the `LoginPage` route, renders it inside `<Layout>`. The user sees the login page. Back button does not re-trigger the loop because the history entry was replaced, not pushed.

**Q (mid): Why is the `replace` prop on `<Navigate>` important?**

Without it, every unauthorized visit pushes a new history entry pointing at `/login`. Hit back, return to the protected URL, redirect again, push another entry. You get a redirect loop in the back button. `replace` calls `history.replaceState` instead of `pushState`, so the protected URL doesn't appear in history at all. Back button from `/login` goes wherever the user was before they tried the protected page.

**Q (mid): When would you use `useNavigate` vs `<Navigate>` vs `<Link>`?**

`<Link>` is the default — declarative in-JSX navigation rendered as an anchor. Use it for nav menus, breadcrumbs, anything clickable that goes elsewhere. `<Navigate>` is a component that triggers navigation on render — use it for redirects (route guards, post-condition redirects). `useNavigate` is the imperative hook — use it inside event handlers and effects, after a side-effect like a form submit or a delete. As a rule, if you're inside JSX rendering, use `<Link>` or `<Navigate>`. If you're inside a callback, use `useNavigate`.

**Q (senior): What is route ranking and when does it bite you?**

Route ranking is how the matcher picks one route when multiple could match. Static segments outrank dynamic, dynamic outranks splat, longer specific paths outrank shorter ones. It bites you when you have a dynamic segment that should be a reserved word — for example `<Route path=":userId">` and `<Route path="new">` as siblings. Ranking handles it correctly (the static `new` wins for `/new`), but if you wrote it the old way as `<Route path=":userId">` with `userId === "new"` as a sentinel, you'd build a buggy app. The other place it bites: you define two dynamic routes at the same rank and rely on order. Don't rely on order; make one more specific than the other.

**Q (senior): Compare ProtectedRoute as a layout route vs as a wrapper around individual page components. Which is better and why?**

Layout-route form is the v6+ idiom and it scales better. Three reasons. First, you check auth once at the boundary, not once per child component — fewer places to forget the check. Second, you can compose checks: outer `ProtectedRoute roles=["admin","organizer"]` enclosing inner `ProtectedRoute roles=["admin"]` gives you a nested gate that mirrors your URL structure. Third, the check sits in the route tree, so reviewing `App.jsx` answers "which routes are gated by what?" in one read. The wrapper form (`<ProtectedRoute><Page/></ProtectedRoute>`) is fine for a single one-off but invites the bug "oh, this page isn't wrapped, we shipped a public admin route." This codebase supports both via the `children ? children : <Outlet />` switch but uses the layout form in `App.jsx`.

**Q (senior): The codebase uses `<BrowserRouter>` + `<Routes>`. The v6.4+ API exposes `createBrowserRouter` with route-level loaders. What is the trade-off?**

Loaders move data fetching into the route definition. The router invokes all loaders in the matched chain **in parallel** before rendering any component. Benefits: no waterfall (you don't render Page A, then have Page A fire a fetch, then render a spinner), back-button restores from a route-scoped cache, code-split routes get their data ready by the time the chunk arrives.

Trade-offs: you lose the colocation of "data and component live in the same file" — your loader is in the route definition. You gain a parallel fetch story but you give up some of React's render-as-you-fetch composability. And in practice if you already use TanStack Query (this codebase does), the query cache gives you most of what loaders give you, minus the parallel preload. So the answer is "loaders are great for greenfield apps without a separate data layer; if you already have TanStack Query, the gain is marginal and the migration cost is real."

**Q (senior): The codebase has a `Layout` component that reads `useLocation()` and branches on `pathname.startsWith("/admin")`. What's the alternative and why might it be better?**

Alternative: split the layout into two layout routes. One `<Route element={<ParticipantLayout />}>` wrapping participant URLs, one `<Route element={<AdminLayout />}>` wrapping admin URLs. The router picks which layout to render based on URL — no `pathname.startsWith` logic anywhere.

Why it might be better: cleaner separation of concerns, no risk of "I added a new admin route but forgot to update the `startsWith` check in Layout," and each layout has access to its own context (admin sidebar state vs participant filter state) without leaking.

Why this codebase doesn't do it: history. The single-layout approach was simpler when there were only two pages. As the surface grew, the conditional logic accumulated. Refactoring to dual-layouts now is a real change with real test fallout — it's a fair "what would you change here?" question.

**Q (senior): How would you implement a "remember intended destination after login" flow?**

When `ProtectedRoute` redirects an unauthenticated user, pass the current location in `<Navigate>` state:

```jsx
const location = useLocation();
return <Navigate to="/login" replace state={{ from: location }} />;
```

On the login page, after a successful login, read it back and navigate there:

```jsx
const location = useLocation();
const from = location.state?.from?.pathname || "/admin";
nav(from, { replace: true });
```

Why `state` and not a query string? Because the intended URL can contain its own query string and you don't want to nest URL-encoding. Why `replace` after login? Because `/login` shouldn't sit in the back history. Pitfall: you must validate `from` before navigating — never blindly redirect to a user-supplied URL or you have an open redirect vulnerability.

## Further reading

- React Router docs — https://reactrouter.com/
- React Router v6.4 data router — https://reactrouter.com/en/main/routers/picking-a-router
- React Router v7 release notes — https://reactrouter.com/upgrading/v6
- History API on MDN — https://developer.mozilla.org/en-US/docs/Web/API/History_API
- Kent C. Dodds, "Authenticated Routes with React Router" — https://kentcdodds.com/blog/authentication-in-react-applications
