# TanStack Query: Server-State for React

This is a lecture for interview prep on TanStack Query (formerly React Query). The objective is to be able to explain *why* it exists, what "server state" means as a category, and how the cache, staleness model, and invalidation tree actually work. The codebase we work in (uni-volunteer-scheduler) uses `@tanstack/react-query@5.90`, so everything below targets the v5 API.

If you can answer "why not just use `useEffect` and `fetch`?" without saying anything wrong about race conditions, refetches, or cache invalidation, you have the foundation. Adding optimistic updates and `onMutate` rollback gets you to senior-level.

## The design choice

TanStack Query is a cache for **server state**. The library's central thesis is that data which lives on a server has fundamentally different invariants from data which lives in your React tree:

- Server data **goes stale** (somebody else updated it).
- Server data is **shared** (two components want the same user list).
- Server data has **failure modes** (network errors, retries, timeouts).
- Server data needs to be **kept in sync** (refetch on tab focus, on network reconnect).

`useState` and `useReducer` are fine for client state — UI flags, form drafts, modal-open booleans. They don't help with anything in the list above. The natural reflex is to write `useEffect(() => { fetch(...).then(setData) }, [id])`. This works for a five-minute demo and breaks the moment you have any of:

- Two components needing the same data (you fetch twice).
- A user clicking between two `id`s rapidly (race condition — the slow response of the first id arrives after the second, overwrites it).
- A user leaving and returning to the page (refetch? cached? stale?).
- A mutation that changes the data (now every component holding that data needs to know).
- A user opening a second tab and changing something (refetch on focus?).

Every team that builds a non-trivial React app eventually invents some piece of TanStack Query badly. The library exists because that work was being repeated by every shop.

### Server state vs client state

- **Client state** — UI flags, form values, route params (route params are technically derived from URL, but you can think of them as client). Owned by the React tree. `useState` is fine.
- **Server state** — Data fetched from an API. Owned by the server. Can change without your component knowing. Needs caching, deduplication, invalidation, refetching.

TanStack Query handles server state. Redux / Zustand / Context handle client state. If you're storing API responses in Redux, you're inventing TanStack Query (badly) inside Redux. Twenty years ago Redux did try to be the server-state layer; the community has since cleanly bifurcated.

### Alternatives worth naming in interviews

- **SWR** (from Vercel). Same category, smaller API, less feature-rich. Same mental model — `useSWR(key, fetcher)`. SWR is to TanStack Query roughly what Preact is to React: leaner, intentionally less. Fine for simple apps. Lacks first-class mutations, infinite queries, suspense integration in v5.
- **RTK Query** (Redux Toolkit). Server-state in the Redux idiom — you define endpoints in a slice, get auto-generated hooks. Excellent if you already use Redux. Heavyweight if you don't. Type-driven, generates hooks from schemas, integrates with the Redux DevTools.
- **Apollo Client.** GraphQL-specific. Same cache-and-invalidate model, but cache keys are derived from GraphQL queries and `__typename`. Don't use it if you don't use GraphQL.
- **`useEffect` + `fetch`.** The wrong answer for anything non-trivial. Lacks deduplication, cache, retry, refetch-on-focus, mutation/invalidation. Always says more about the codebase than the library.
- **Custom hooks over `fetch`** (`useEvents()`, `useUsers()`). You end up reinventing every TanStack feature. If your custom hook has a `useState` for `data`, `error`, `loading` and a `useEffect` that calls fetch — congratulations, you've reinvented the easy 5% of TanStack Query.

### Pros and cons of TanStack Query

Pros: dedup, automatic background refetch, retry with backoff, optimistic updates, devtools, framework-agnostic core, type-safe in v5 with proper generics, suspense mode if you want it, infinite queries for paginated lists, query invalidation as a tree.

Cons: bundle size is ~13kb min+gzip — non-trivial for tiny apps. The mental model is real (staleTime vs gcTime, query keys as identity, invalidation as marking stale) and trips up juniors. You can over-cache if you don't think about keys. The `onMutate` optimistic-update story has a real learning curve — there are five places to update state correctly and one wrong order causes flicker.

## How it works under the hood

### The query cache

A `QueryClient` holds a `Map<QueryKey, Query>`. The query key is a serializable array; the library `JSON.stringify`s it to produce a string Map key. So `["adminUsers"]` and `["adminUsers", { include_inactive: true }]` are two distinct entries.

A `Query` object holds:

- `data` — the last successful response.
- `error` — the last error, if any.
- `status` — `"pending" | "error" | "success"`.
- `fetchStatus` — `"fetching" | "paused" | "idle"`. Orthogonal to status; you can be `success + fetching` during a background refetch.
- `dataUpdatedAt` — epoch ms of the last successful fetch.
- `observers` — the set of React components currently subscribed via `useQuery`.

### Staleness and gc

Two time settings govern a query's lifecycle:

- **`staleTime`** (default `0` ms). How long after a successful fetch the data is considered fresh. While fresh, `useQuery` returns cached data without a refetch. After it, the data is stale — still returned immediately, but a background refetch fires on next subscribe / window focus / network reconnect.
- **`gcTime`** (default 5 minutes, used to be called `cacheTime` in v4). How long an unobserved query lingers in the cache before garbage collection. If no component is subscribed for `gcTime` ms, the entry is dropped.

So: `staleTime` controls "is the data old enough to refetch?", `gcTime` controls "is anyone still interested in this data?".

Common misunderstanding: `staleTime: 0` does **not** mean "refetch on every render." It means "every time a new component mounts or refocuses, treat the data as stale and refetch in the background, but return the cached data immediately so the UI isn't blank." Defaults are aggressive on refetch but never block the render.

### Subscription model

`useQuery({ queryKey, queryFn })` does:

1. Subscribes the component (creates an observer) to the query identified by `queryKey`.
2. If no `Query` exists for that key — creates one, runs `queryFn`, populates the cache.
3. If a `Query` exists and is fresh — returns cached data, no fetch.
4. If a `Query` exists and is stale — returns cached data, triggers a background fetch, the component will re-render when the fetch completes.
5. On unmount — removes the observer. If observer count reaches 0, starts the `gcTime` timer.

This is why two components calling `useQuery({ queryKey: ["users"] })` do exactly one network request: same key, same query, single fetch, both components subscribe to the result.

### Refetching triggers

By default, a query refetches when:

- A new observer mounts (and the data is stale).
- The window regains focus (`refetchOnWindowFocus: true` default — this codebase disables it globally).
- The network reconnects (`refetchOnReconnect: true` default).
- A polling interval (`refetchInterval`) fires.
- An explicit `invalidateQueries` call marks the entry stale and an observer exists.

### Invalidation tree

`queryClient.invalidateQueries({ queryKey: ["adminUsers"] })` does **two** things:

1. Marks every query whose key **starts with** `["adminUsers"]` as stale (this is the tree part — `["adminUsers", { id: 42 }]` is matched too).
2. For each matched query that has at least one observer, triggers an immediate refetch. Unobserved queries are just marked stale; they'll refetch when next subscribed.

So invalidation is a **prefix match against the key array**. The convention is: leading element identifies the resource, trailing elements parameterize it. `["events"]` is the list, `["events", id]` is one event, `["events", id, "signups"]` is its signups. Invalidate `["events"]` and the whole tree refreshes.

### Mutations

`useMutation({ mutationFn })` does not touch the query cache by itself. A mutation is a one-shot operation (POST, PUT, DELETE). The hook returns `mutate(variables)` and tracks `isPending`, `error`, `data` from the mutation itself. **You** are responsible for telling the cache what to do after the mutation succeeds — usually with `invalidateQueries`.

The lifecycle hooks (`onMutate`, `onSuccess`, `onError`, `onSettled`) are how you wire optimistic updates:

1. **`onMutate(variables)`** — called *before* the request fires. Cancel in-flight queries, snapshot current cache, optimistically write the new value. Return a context object containing the snapshot.
2. **`onError(error, variables, context)`** — called if the mutation fails. Restore the snapshot from `context`.
3. **`onSuccess(data, variables, context)`** — called on success. You can write the server response into the cache here.
4. **`onSettled(data, error, variables, context)`** — called either way. Typically `invalidateQueries` lives here so the cache reconciles to server truth.

### The internal Map keyed by stringified key

Concretely, the cache is `new Map<string, Query>()`. Keys are produced by a stable hash function on the `queryKey` array. The library walks the key, hashing object properties in sorted order so `{ a: 1, b: 2 }` and `{ b: 2, a: 1 }` produce the same hash. This is why object literals in keys work despite referential instability.

If your key contains something non-serializable (a `Date`, a `Map`, a function), the hash is undefined behaviour and you'll get cache misses or worse. Stick to plain JSON-able shapes — primitives, arrays, objects.

### Refetch coordination

When multiple components subscribe to the same key, only one fetch runs. The fetch promise is held on the Query; new subscribers `await` it. When the promise resolves, all subscribers get the result on the same render cycle.

When you call `qc.invalidateQueries({ queryKey })` while a refetch is already in flight, the library is smart enough not to launch a second one — the existing fetch is considered the response to the invalidation.

### Why this beats `useEffect + fetch`

| Concern | TanStack Query | useEffect + fetch |
|---|---|---|
| Two components, same data | One fetch | Two fetches |
| Component remounts within 5min | Cache hit | Refetch |
| User clicks rapidly between `/users/1` and `/users/2` | Latest wins, stale aborted | Race condition |
| Mutation succeeds, list needs refresh | `invalidateQueries(['users'])` — one line | Manual cache update or refetch trigger via `useState` bump |
| User leaves tab, returns 10 min later | Background refetch | Stale data |
| Network drops, returns | Auto refetch | Stuck |
| 500 error | Auto retry with backoff | You write the retry |

## How this codebase uses it

### Setup at `frontend/src/main.jsx`

```jsx
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

<QueryClientProvider client={queryClient}>
  <BrowserRouter>
    <AuthProvider>
      <App />
    </AuthProvider>
  </BrowserRouter>
</QueryClientProvider>
```

Two notable defaults overridden:

- `retry: 1` — one retry on failure (default is 3). Good for snappier error states; bad if your API has flaky timeouts.
- `refetchOnWindowFocus: false` — disables auto-refetch on tab focus globally. Reasonable for an internal app where users might tab away mid-edit; you don't want their work overwritten by a background refetch. Pages that **do** want it (e.g. `OrganizerDashboard`) opt back in explicitly.

### Basic list query: `EventsSection`

```jsx
// frontend/src/pages/admin/EventsSection.jsx
const q = useQuery({
  queryKey: ["adminEventsList"],
  queryFn: () => api.events.list(),
});
```

Plain query, no params, default staleTime. The list is refetched only when explicitly invalidated. The component reads `q.data`, `q.isPending`, `q.error`.

### Parameterized key: `UsersAdminPage`

```jsx
// frontend/src/pages/UsersAdminPage.jsx
const listQ = useQuery({
  queryKey: ["adminUsers", { include_inactive: showDeactivated }],
  queryFn: () =>
    api.admin.users.list(showDeactivated ? { include_inactive: true } : undefined),
});
```

When the user toggles "show deactivated," the key changes, which is a new query. TanStack fetches the new list, caches it under the new key, and the old key sits in cache until `gcTime` expires. Toggling back is instant — the previous key is still cached.

This is the canonical "key as input" pattern: every input that changes the response must be in the key, or you'll serve stale data after a filter change.

### Mutation with invalidation

```jsx
// frontend/src/pages/admin/EventsSection.jsx
const deleteM = useMutation({
  mutationFn: (id) => api.events.delete(id),
  onSuccess: () => {
    qc.invalidateQueries({ queryKey: ["adminEventsList"] });
    toast.success("Event deleted.");
  },
  onError: (e) => toast.error(e?.message || "Delete failed"),
});
```

Pattern: do the mutation, on success invalidate the list query, on error show a toast. No optimistic update — the user sees the list flash to "loading" briefly while the refetch completes. Trade-off: simpler code, slightly less snappy UI.

### Optimistic update with rollback

```jsx
// frontend/src/pages/OrganizerRosterPage.jsx
const checkInMut = useMutation({
  mutationFn: (signupId) => checkInSignup(signupId),
  onMutate: async (signupId) => {
    await qc.cancelQueries({ queryKey: ["roster", eventId] });
    const prev = qc.getQueryData(["roster", eventId]);
    qc.setQueryData(["roster", eventId], (old) => {
      if (!old) return old;
      return {
        ...old,
        checked_in_count: old.checked_in_count + 1,
        rows: old.rows.map((r) =>
          r.signup_id === signupId ? { ...r, status: "checked_in" } : r,
        ),
      };
    });
    return { prev };
  },
  onError: (_err, _signupId, context) => {
    if (context?.prev) qc.setQueryData(["roster", eventId], context.prev);
    toast.error("Check-in failed. Please retry.");
  },
  onSettled: () => {
    qc.invalidateQueries({ queryKey: ["roster", eventId] });
  },
});
```

This is the textbook five-step pattern:

1. **Cancel** in-flight refetches for the same key — otherwise a slow GET response can overwrite our optimistic write.
2. **Snapshot** the current data so we can roll back.
3. **Mutate** the cache optimistically.
4. **Return** the snapshot from `onMutate`; it shows up as `context` in the next callbacks.
5. **Reconcile**: on error, write the snapshot back. On settle, invalidate so we converge to server truth.

The roster page also polls — `refetchInterval: 5000, refetchIntervalInBackground: false` — so the checked-in count updates even if other organizers check people in from their own devices.

### Conditional polling

```jsx
// frontend/src/pages/admin/ImportsSection.jsx
const importsQ = useQuery({
  queryKey: ["adminImports"],
  queryFn: () => api.admin.imports.list(),
  refetchInterval: (query) => {
    const data = query.state.data;
    if (!data) return false;
    const hasActive = data.some(
      (imp) => imp.status === "pending" || imp.status === "processing"
    );
    return hasActive ? 2000 : false;
  },
});
```

`refetchInterval` can be a function of the current query state. Here: poll every 2s only while any CSV import is in flight; stop polling when everything is done. The "stop polling" return value is `false`. Avoids burning the API when there's nothing to wait for.

### `staleTime` for slow-changing data

```jsx
// frontend/src/pages/public/EventsBrowsePage.jsx
const currentWeekQ = useQuery({
  queryKey: ["publicCurrentWeek"],
  queryFn: () => api.public.getCurrentWeek(),
  staleTime: 5 * 60 * 1000,
});
```

The "current week" only changes once a week. A 5-minute `staleTime` means components that mount within 5 minutes of each other share the cached value without a refetch.

## Common pitfalls

**1. Wrong query key shape.** `queryKey: "users"` (string) works but is non-idiomatic. Always use arrays. Use `["users"]`, `["users", id]`, `["users", id, "signups"]` so invalidation by prefix works.

**2. Missing inputs in the key.** A query that depends on a filter but doesn't include the filter in its key will serve stale data after the filter changes. Symptom: filter dropdown changes nothing.

**3. `queryFn` reads from a stale closure.** Define `queryFn` as `() => api.events.list(filter)` where `filter` is in scope. If you forget to include `filter` in the key, even when the closure captures the new value the key is unchanged so the cache hits — and you serve old data fetched from the new filter or vice versa. The rule: every variable used by `queryFn` must appear in the key.

**4. Over-invalidating.** `qc.invalidateQueries()` with no args invalidates **every** query. Useful for "log out, clear everything," catastrophic if called after a single delete. Always pass `{ queryKey: [...] }`.

**5. Optimistic update without `cancelQueries`.** A slow refetch can land after your optimistic write and overwrite it. Always `await qc.cancelQueries({ queryKey })` first.

**6. Optimistic update without rollback.** If your `onMutate` writes to the cache but `onError` doesn't restore the snapshot, a failed mutation leaves the cache in a fictional state. Always return the snapshot from `onMutate` and restore in `onError`.

**7. Triggering `useQuery` conditionally.** Don't do `if (id) useQuery(...)` — hooks must run unconditionally. Instead use the `enabled` option: `useQuery({ queryKey, queryFn, enabled: !!id })`. The query stays "pending" until enabled.

**8. Mixing server state into local `useState`.** `const [users, setUsers] = useState(q.data || [])` — now you have two sources of truth. Background refetches update `q.data` but not your local state. Symptom: data goes stale after refetch. Just read `q.data` directly, derive what you need via `useMemo`.

**9. Polling backgrounds.** `refetchInterval: 5000` polls forever, even when the tab is hidden. Combine with `refetchIntervalInBackground: false` to pause when the tab loses focus.

**10. `staleTime: Infinity` plus no manual invalidation.** Data never refetches. Sometimes desired (truly immutable data) but more often a bug. Make sure you invalidate on the corresponding mutations.

**11. Confusing `isPending` with `isLoading` (v5).** v5 renamed: `isPending` is "no data, first fetch in flight" (was `isLoading` in v4). `isLoading` in v5 is `isPending && isFetching`. Use `isPending` for "we have no data, show a spinner."

**12. Race condition on rapid input changes.** Two queries with different keys fired in quick succession: TanStack handles this internally — only the latest fetch's result writes to its key's cache. But within the same key (rare with proper key design), you can still get a race; that's where `cancelQueries` matters.

**13. Provider remounted on every render.** If you instantiate `new QueryClient()` inside a component body, every render produces a new client and a fresh empty cache. Hoist the instantiation outside the component (this codebase does this correctly in `main.jsx`).

**14. Multiple QueryClients in tests.** Each `render()` call creating its own client means cache state doesn't carry across test cases — usually what you want for isolation, but if you're trying to seed cache for a suite via `setQueryData` and the seed isn't taking, check you're talking to the same client the component sees.

**15. Forgetting `await` on `cancelQueries`.** The function returns a Promise. Without `await`, you fire the optimistic write before the cancellation has actually taken effect, defeating the point.

**16. `select` returning a new reference every time.** The `select` option re-projects on every cache update. If your projection returns a fresh array/object literal, React will think the data changed and re-render. Memoize the projection or use a stable selector.

## Interview Q&A

**Q (junior): Why use TanStack Query instead of `useEffect` and `fetch`?**

Three reasons. First, deduplication — if two components fetch the same data, TanStack does one network call. Second, caching — repeat visits within `staleTime` are instant. Third, mutation invalidation — after a POST, you can invalidate a key and every component watching it refetches automatically. With `useEffect`, you reinvent all three, badly. The bigger argument is the category: TanStack Query handles "server state," which has different invariants from "client state." `useState` was never designed for data that can change without your component knowing.

**Q (junior): What is a query key and why does it matter?**

The query key is the cache identity. Two `useQuery` calls with the same key share one entry. Two with different keys are two entries. The key must include every input that affects the response — if your query depends on a filter, the filter belongs in the key. Otherwise you serve stale data after the filter changes. The key is also the prefix-match target for `invalidateQueries`, so structure it as a tree: `["users"]`, `["users", id]`, `["users", id, "signups"]`.

**Q (mid): Difference between `staleTime` and `gcTime`?**

`staleTime` is how long data is considered fresh after a successful fetch. While fresh, no refetch happens on subscribe. After it expires, the data is stale: still served from cache, but a background refetch fires on next subscribe or window focus. Default is 0 (always stale).

`gcTime` (was `cacheTime` in v4) is how long the cache entry survives **without observers**. When the last `useQuery` for a key unmounts, the entry starts a `gcTime` countdown. If a new observer subscribes before it expires, the entry is reused. Default is 5 minutes.

So `staleTime` is "when should I refetch?", `gcTime` is "when should I forget?".

**Q (mid): How does `invalidateQueries` work?**

It performs a prefix-match against the query key array. `invalidateQueries({ queryKey: ["users"] })` matches `["users"]`, `["users", 1]`, `["users", 1, "signups"]` — anything whose key starts with `["users"]`. For each match, it marks the query stale and, if any component is subscribed, triggers a refetch immediately. Unobserved matches are just marked stale and refetch on next subscribe.

**Q (mid): How do you implement an optimistic update?**

Five steps inside the mutation:

1. `onMutate(variables)` — `await qc.cancelQueries({ queryKey })` to stop in-flight fetches that could land after our optimistic write.
2. Snapshot the current data — `const prev = qc.getQueryData(queryKey)`.
3. Optimistically update the cache — `qc.setQueryData(queryKey, optimisticValue)`.
4. Return `{ prev }` from `onMutate`. This becomes `context` in subsequent callbacks.
5. In `onError`, restore — `qc.setQueryData(queryKey, context.prev)`. In `onSettled`, invalidate to converge to server truth.

Skip the snapshot or skip `cancelQueries` and you get flickers, stale writes, or invented data on error. This codebase does it correctly in `OrganizerRosterPage.jsx` for the check-in mutation.

**Q (senior): When would you choose SWR over TanStack Query, or vice versa?**

SWR is leaner — smaller bundle, smaller API, "stale-while-revalidate" as the headline pattern. Use SWR when: your app fetches mostly GETs, you don't need optimistic mutations with rollback, you don't need infinite queries, bundle size matters. Use TanStack Query when: you need first-class mutations, optimistic updates, retries with backoff, devtools, suspense integration, paginated/infinite lists, or you want the same library to handle background polling with conditional intervals. For an internal admin tool with create/update/delete flows like this codebase, TanStack is the clearly correct choice. For a public marketing site reading mostly static content, SWR is fine.

**Q (senior): A user reports that after they delete an event, the list "sometimes" doesn't update. What do you check?**

Walk through the cache flow. First — does the delete mutation actually call `invalidateQueries` with the right key? Compare the invalidation key to the list query's key; mismatched keys are the #1 cause. Second — is the user observing the list query when the mutation succeeds? If they navigated away to a confirmation page before the response, the list has no observer; it'll refetch next time they subscribe but not now. Third — is there an `onSuccess` returning early or throwing? Errors in `onSuccess` are silent unless you catch them. Fourth — are they on the same `QueryClient`? Multiple `QueryClient` instances (e.g. in a test wrapper or remount) maintain separate caches. Fifth, if it really is intermittent — race between the optimistic update, the refetch from invalidation, and the user's next interaction. Add `await qc.cancelQueries` in `onMutate`.

**Q (senior): How would you implement infinite scroll with TanStack Query?**

Use `useInfiniteQuery` instead of `useQuery`. The query function receives a `pageParam`; you return both data and the next page param. The hook returns `data.pages` (an array of fetched pages) and a `fetchNextPage` function. Wire `fetchNextPage` to an IntersectionObserver on the last list item. Key shape: `["events", "infinite", filters]`. The library handles deduping, caching, and incremental updates; you just provide the cursor logic in `getNextPageParam`. Avoid the trap of merging pages into a single array yourself — let `data.pages.flatMap` do it at render time, and never mutate the cache's page structure.

**Q (senior): When should mutations skip `invalidateQueries` and use `setQueryData` directly?**

When the server returns the canonical post-mutation state and you have a single key holding the same shape. Example: a PATCH `/users/:id` that returns the updated user row — `qc.setQueryData(["users", id], updatedUser)` writes it straight in, no refetch needed. The `SiteSettingsCard` in this codebase does exactly that.

When **not** to: when the mutation affects multiple queries (a delete on `["events", 1]` should invalidate both `["events", 1]` and `["events"]` the list — you can't `setQueryData` the list without refetching it or knowing its exact shape), or when the server's response isn't authoritative for the cache shape (e.g. the cache stores joined data the mutation endpoint doesn't return). In those cases, invalidate.

Hybrid: `setQueryData` the canonical singleton, `invalidateQueries` the affected lists. Best of both — instant single-record update plus list reconciliation in the background.

**Q (senior): Walk me through what happens if a user has the events page open, leaves their tab for an hour, comes back, and clicks "delete event."**

Tab is open, `useQuery({ queryKey: ["adminEventsList"] })` runs once, populates cache. Tab loses focus — query has an observer (the page is still mounted), so no gc. Hour passes. Tab regains focus. Default behaviour would refetch on focus, but this codebase sets `refetchOnWindowFocus: false` globally. So the user sees stale data — events that might have been added, deleted, or modified by another admin in the past hour.

User clicks delete. `deleteM.mutate(id)` fires. The backend probably rejects with a 404 because the event was already deleted by another admin five minutes ago. The mutation's `onError` toasts "Delete failed." Result: bad UX. Fixes: enable `refetchOnWindowFocus` on critical pages, or add a manual "Refresh" button, or display a `dataUpdatedAt` timestamp. The honest truth: the global `refetchOnWindowFocus: false` is a UX trade-off — comfort during edits at the cost of stale list views. Worth knowing it's set and why.

## Further reading

- TanStack Query docs — https://tanstack.com/query/latest
- TanStack Query v5 migration guide — https://tanstack.com/query/latest/docs/framework/react/guides/migrating-to-v5
- "Practical React Query" by TkDodo — https://tkdodo.eu/blog/practical-react-query (the canonical deep-dive)
- "Effective React Query Keys" by TkDodo — https://tkdodo.eu/blog/effective-react-query-keys
- "Mutations" guide — https://tanstack.com/query/latest/docs/framework/react/guides/mutations
- "Optimistic Updates" guide — https://tanstack.com/query/latest/docs/framework/react/guides/optimistic-updates
