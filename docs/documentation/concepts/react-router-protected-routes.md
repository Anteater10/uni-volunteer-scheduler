# React Router & Protected Routes — Reference

## TL;DR

React Router is a declarative routing library for SPAs. A `<Routes>` element contains a tree of `<Route>` elements; each route can render a layout component that includes `<Outlet />`, into which the router renders the matched child. Pathless layout routes (no `path` prop) wrap children in cross-cutting behaviour without consuming a URL segment — this is the mechanism used to implement protected/authenticated routes. The router exposes hooks (`useNavigate`, `useLocation`, `useParams`, `useSearchParams`) and components (`<Link>`, `<NavLink>`, `<Navigate>`) for navigation and state inspection.

This codebase uses `react-router-dom@7.11` in the v6-style declarative `<BrowserRouter>` + `<Routes>` configuration. It does **not** use the v6.4+ `createBrowserRouter` data router — data fetching is handled by TanStack Query inside route components.

## API surface

### Top-level setup

```tsx
import { BrowserRouter } from "react-router-dom";

// main.jsx
<BrowserRouter>
  <App />
</BrowserRouter>
```

`<BrowserRouter>` provides the History API context. Alternatives: `<HashRouter>` (hash-based URLs, no server config needed), `<MemoryRouter>` (in-memory history, used by tests).

### Routes and Route

```tsx
import { Routes, Route } from "react-router-dom";

<Routes>
  <Route path="/" element={<Layout />}>
    <Route index element={<HomePage />} />
    <Route path="login" element={<LoginPage />} />
    <Route element={<AuthGate />}>
      <Route path="admin" element={<AdminLayout />}>
        <Route path="users" element={<UsersPage />} />
      </Route>
    </Route>
    <Route path="*" element={<NotFoundPage />} />
  </Route>
</Routes>
```

- `path` — URL segment for this level. Omit for pathless layout routes.
- `element` — React element rendered when this route is in the matched chain.
- `index` — boolean; this route matches when the parent matches exactly with nothing after.

### Hooks

```ts
function useNavigate(): NavigateFunction;
//   NavigateFunction = (to: string | number, options?: { replace?: boolean; state?: unknown }) => void

function useLocation(): {
  pathname: string;
  search: string;
  hash: string;
  state: unknown;
  key: string;
};

function useParams<T extends Record<string, string>>(): Partial<T>;
//   All values are strings. Coerce manually for numbers.

function useSearchParams(): [URLSearchParams, (next: URLSearchParams | Record<string, string>, opts?: { replace?: boolean }) => void];
```

### Navigation components

```tsx
<Link to="/admin/users">Users</Link>
<NavLink to="/admin" end className={({ isActive }) => isActive ? "active" : ""}>Overview</NavLink>
<Navigate to="/login" replace state={{ from: location }} />
<Outlet />            // placeholder for child route
<Outlet context={...} />   // optional context passed to useOutletContext()
```

### ProtectedRoute (this codebase)

```tsx
type Role = "admin" | "organizer" | "participant";

interface ProtectedRouteProps {
  roles?: Role[] | null;   // null = any authenticated user
  children?: React.ReactNode;
}

function ProtectedRoute(props: ProtectedRouteProps): JSX.Element;
```

Behaviour:

1. If `useAuth().initializing` — render loading placeholder.
2. If not authenticated — render `<Navigate to="/login" replace />`.
3. If `roles` is supplied and user's role is not in it — render Forbidden message.
4. If `children` was provided — render children (wrapper form).
5. Otherwise — render `<Outlet />` (layout-route form).

## Mental model

**The route tree is a sitemap.** Read top-down, each `<Route>` describes one URL slot. Parent paths concatenate with child paths to form the full URL.

**Layout routes wrap, leaf routes render.** A route is a layout route if its `element` includes `<Outlet />`. The matched child renders into the outlet. A route is a leaf if no further child route matches.

**Pathless routes are pure wrappers.** A `<Route>` with no `path` doesn't consume URL segments — it just inserts wrapping behaviour into the matched chain. This is how `ProtectedRoute` works: it wraps without renaming URLs.

**Matching produces a chain, not a single match.** The router walks from the root to the most specific leaf and renders every `element` it crosses, each rendering its `<Outlet />` to nest the next level.

**Static beats dynamic beats splat.** Sibling routes are ranked by specificity, not declaration order.

**Auth must survive first paint.** Auth state hydrates asynchronously (from localStorage, from a `/me` request). The auth provider must expose an `initializing` flag; `ProtectedRoute` must gate on it. Without this, every refresh of a protected URL bounces the user to login during the hydration window.

**Redirects must `replace`.** Any auth redirect must use `<Navigate replace />` (or `nav(to, { replace: true })`) or the back button creates a redirect loop.

**Filter state belongs in the URL.** Use `useSearchParams` for paging, search, filter chips. The URL becomes shareable and back-button works as users expect.

## Usage in this codebase

### `frontend/src/main.jsx`

Wires `<BrowserRouter>` at the root, inside `<QueryClientProvider>` and outside `<AuthProvider>` so auth context can see location if it wants to.

### `frontend/src/App.jsx`

The entire route map. Highlights:

- One `<Layout>` parent wraps the whole app. Header, footer, toast host, and copilot FAB live here.
- Participant routes (`/volunteer`, `/volunteer/events/:eventId`, `/signup/confirm`, etc.) are siblings of admin routes and are **not** wrapped in `ProtectedRoute`.
- Two layers of `ProtectedRoute` wrap the admin shell: the outer layer admits admins + organizers into `/admin/*`; the inner layer restricts `/admin/users`, `/admin/audit-logs`, `/admin/exports`, `/admin/orientation-credits`, `/admin/architecture` to admins only.
- Several `Redirect*` helper components convert legacy URLs (`/events/:id` → `/volunteer/events/:id`, `/organize/events/:id/roster` → `/organizer/events/:id/roster`) into `<Navigate replace>` calls so old email links don't 404.
- A `RootRoute` component renders `LoginPage` for signed-out visitors at `/` and redirects to `/admin` for admins/organizers.

### `frontend/src/components/ProtectedRoute.jsx`

Twenty-six lines. Implements the three-state guard (initializing / unauthed / forbidden) and supports both wrapper-and-layout usage via the `children ? children : <Outlet />` switch.

### `frontend/src/components/Layout.jsx`

Reads `useLocation()` to branch its chrome (admin sidebar vs participant bottom-nav vs minimal header). Renders `<Outlet />` for the matched child. Uses `<Link>` for the brand link and the menu items.

### `frontend/src/pages/admin/AdminLayout.jsx`

The nested layout for `/admin/*`. Renders a sidebar of `<NavLink>` items, the admin top bar, and `<Outlet />` for the matched section (Overview, Events, Users, etc.). Uses `useNavigate()` to redirect on sign-out. Filters the nav-item list by role so organizers don't see admin-only links.

### `frontend/src/pages/LoginPage.jsx`

Uses `useNavigate()` after `login()` succeeds, redirecting to `/admin`. Does not currently honour a "from" location in `<Navigate>` state — users who hit a protected URL while logged out land on `/admin` after login, not their original target.

### `frontend/src/pages/AuditLogsPage.jsx`

Canonical `useSearchParams` example. All filter state (`page`, `q`, `kind`, `actor_id`, `from_date`, `to_date`, `preset`) is mirrored in the URL. Filters are deep-linkable; refresh preserves them; browser back navigates between filter combinations.

### `frontend/src/pages/public/EventsBrowsePage.jsx`

Uses `useSearchParams` to hold the selected week (`quarter`, `year`, `week`). Falls back to a `useQuery`-loaded "current week" when the params are missing.

### `frontend/src/pages/SetPasswordPage.jsx`

Reads a magic-link token from the URL with `useSearchParams`. Uses `useNavigate` to redirect to `/login` on success.

## Operational concerns

### React Devtools Components panel

Inspecting a rendered tree reveals the matched chain: `Router > Routes > Route > Layout > Outlet > Route > ProtectedRoute > Outlet > AdminLayout > Outlet > UsersAdminPage`. Useful when you suspect a layout route is missing or a guard is wrapping the wrong subtree.

### Performance

Route components are not memoized by the router. Re-renders cascade from the matched root down. If a parent layout reads `useLocation` and re-renders on every path change, every child re-renders too. Mitigate with `React.memo` on heavy leaf components, or by reading location only inside the components that actually need it (don't lift `useLocation` into a top-level layout if a sub-component is the real consumer).

Code-split routes via `React.lazy`:

```jsx
const AdminLayout = React.lazy(() => import("./pages/admin/AdminLayout"));
<Suspense fallback={<Spinner />}>
  <Routes>...</Routes>
</Suspense>
```

This codebase does not currently split admin routes from participant routes — the participant bundle includes the admin tree. A future optimization.

### Common bugs

- **Blank screen after a refresh on a protected URL.** Almost always the `initializing` guard is missing or the auth provider's hydration races the first render. Add `if (initializing) return <Spinner />;` in `ProtectedRoute`.
- **Back-button redirect loop.** Missing `replace` on `<Navigate>` or `nav()`.
- **404 on direct URL load but works after in-app nav.** The server isn't rewriting unknown paths to `index.html`. For Vite + most static hosts, add a SPA-fallback rewrite rule.
- **`useParams` returns `undefined` for an existing segment.** The hook is called from a component above the matched route — params are scoped to the matched chain.
- **Two routes both match.** Check ranking. If both are dynamic at the same level, make one more specific (`/users/me` static beats `/users/:id` dynamic).
- **`NavLink` is always active.** Missing `end` prop. Without `end`, `to="/admin"` is active on `/admin/users` because it is a prefix match.

### Testing

Wrap test renders in `<MemoryRouter initialEntries={[...]}>`:

```jsx
import { MemoryRouter } from "react-router-dom";
render(
  <MemoryRouter initialEntries={["/admin/users"]}>
    <App />
  </MemoryRouter>
);
```

For Playwright (this codebase's `e2e/` directory), navigate via `page.goto("/admin/users")` and assert on rendered content. The History API works the same in headless browsers.

## Glossary

- **Layout route** — A `<Route>` whose `element` renders `<Outlet />`. Wraps children in shared UI.
- **Pathless route** — A `<Route>` with no `path` prop. Adds wrapping behaviour to the matched chain without consuming a URL segment.
- **Index route** — A `<Route index>` that matches when the parent path matches exactly. The "home page" of a section.
- **Outlet** — Placeholder element rendered by a layout, into which the matched child renders.
- **Matched chain** — The ordered sequence of routes from root to leaf that the router renders for a given URL.
- **Route ranking** — The algorithm that picks one route when multiple could match: static > dynamic > splat, longer specific paths win.
- **History API** — Browser API (`pushState`, `replaceState`, `popstate`) that React Router wraps.
- **`<BrowserRouter>`** — Uses real URLs and the HTML5 History API. Requires the server to serve `index.html` for unknown paths.
- **`<HashRouter>`** — Uses `#/path` URLs and the `hashchange` event. No server config needed.
- **`<MemoryRouter>`** — In-memory history; used in tests where there is no DOM history.
- **Data router** — The v6.4+ API (`createBrowserRouter`) that supports route-level `loader` and `action` functions for parallel data fetching. Not used in this codebase.
- **`replace` navigation** — Replaces the current history entry instead of pushing a new one. Essential for redirects to avoid back-button loops.
- **Splat route** — `path="*"`, matches any remaining path. Used for 404 pages.
- **Magic link** — Auth pattern where a single-use token in a URL replaces a password. Implemented in `SetPasswordPage` via `useSearchParams`.
