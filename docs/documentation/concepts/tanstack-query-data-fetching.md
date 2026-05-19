# TanStack Query — Reference

## TL;DR

TanStack Query (formerly React Query) is a server-state cache for React. It deduplicates concurrent fetches by query key, caches responses with configurable staleness, refetches on configurable triggers, and provides a mutation API with optimistic-update primitives. The `QueryClient` holds a `Map` keyed by serialized query keys; `useQuery` subscribes a component to a key, `useMutation` wraps a single non-idempotent operation, and `queryClient.invalidateQueries` marks any key with a matching prefix stale.

This codebase uses `@tanstack/react-query@5.90`. The client is configured at `frontend/src/main.jsx` with `retry: 1` and `refetchOnWindowFocus: false` as global defaults. Pages opt in to per-query overrides (polling, longer `staleTime`, focus refetch) as needed.

## API surface

### Provider

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 0,
      gcTime: 5 * 60 * 1000,
    },
  },
});

<QueryClientProvider client={queryClient}>
  {/* ... */}
</QueryClientProvider>
```

### useQuery

```ts
type QueryKey = readonly unknown[];

interface UseQueryOptions<TData, TError = Error> {
  queryKey: QueryKey;
  queryFn: (ctx: QueryFunctionContext) => Promise<TData>;
  enabled?: boolean;
  staleTime?: number;          // ms; default 0
  gcTime?: number;              // ms; default 300_000
  retry?: number | boolean | ((failureCount: number, error: TError) => boolean);
  refetchOnWindowFocus?: boolean | "always";
  refetchOnReconnect?: boolean | "always";
  refetchOnMount?: boolean | "always";
  refetchInterval?: number | false | ((query: Query) => number | false);
  refetchIntervalInBackground?: boolean;
  select?: (data: TData) => unknown;
  placeholderData?: TData | ((prev: TData | undefined) => TData);
  meta?: Record<string, unknown>;
}

interface UseQueryResult<TData, TError> {
  data: TData | undefined;
  error: TError | null;
  status: "pending" | "error" | "success";
  fetchStatus: "fetching" | "paused" | "idle";
  isPending: boolean;           // status === "pending"
  isError: boolean;
  isSuccess: boolean;
  isFetching: boolean;          // fetchStatus === "fetching"
  isStale: boolean;
  dataUpdatedAt: number;
  refetch: () => Promise<UseQueryResult<TData, TError>>;
}

function useQuery<TData, TError = Error>(
  options: UseQueryOptions<TData, TError>
): UseQueryResult<TData, TError>;
```

### useMutation

```ts
interface UseMutationOptions<TData, TError, TVariables, TContext> {
  mutationFn: (variables: TVariables) => Promise<TData>;
  onMutate?: (variables: TVariables) => Promise<TContext | void> | TContext | void;
  onSuccess?: (data: TData, variables: TVariables, context: TContext) => void;
  onError?: (error: TError, variables: TVariables, context: TContext | undefined) => void;
  onSettled?: (data: TData | undefined, error: TError | null, variables: TVariables, context: TContext | undefined) => void;
  retry?: number | boolean;
}

interface UseMutationResult<TData, TError, TVariables> {
  mutate: (variables: TVariables, opts?: MutateOptions) => void;
  mutateAsync: (variables: TVariables) => Promise<TData>;
  data: TData | undefined;
  error: TError | null;
  isPending: boolean;
  isSuccess: boolean;
  isError: boolean;
  reset: () => void;
}

function useMutation<TData, TError = Error, TVariables = void, TContext = unknown>(
  options: UseMutationOptions<TData, TError, TVariables, TContext>
): UseMutationResult<TData, TError, TVariables>;
```

### useQueryClient and imperative APIs

```ts
function useQueryClient(): QueryClient;

class QueryClient {
  getQueryData<T>(queryKey: QueryKey): T | undefined;
  setQueryData<T>(queryKey: QueryKey, updater: T | ((old: T | undefined) => T)): T;

  invalidateQueries(filters?: { queryKey?: QueryKey; exact?: boolean; refetchType?: "active" | "inactive" | "all" | "none" }): Promise<void>;
  cancelQueries(filters?: { queryKey?: QueryKey }): Promise<void>;
  refetchQueries(filters?: { queryKey?: QueryKey }): Promise<void>;
  removeQueries(filters?: { queryKey?: QueryKey }): void;
  prefetchQuery(options: UseQueryOptions): Promise<void>;
}
```

## Mental model

**Cache identity is the query key.** Two `useQuery` calls with the same key share one entry. The key is `JSON.stringify`'d to produce a string Map key, so it must be serializable. Use arrays. Put parameters that affect the response *in* the key.

**Fresh vs stale vs garbage-collected.** Data is fresh for `staleTime` ms after a successful fetch. While fresh, no refetch happens on subscribe. After it expires, data is stale — still served from cache, refetched in background on next subscribe / focus / reconnect. After the last observer unmounts, the entry survives `gcTime` ms before being dropped.

**Queries deduplicate; mutations don't.** Two components asking for the same key share one network request. Two `mutate()` calls always fire two requests.

**Invalidation is a prefix match.** `invalidateQueries({ queryKey: ["events"] })` matches every query whose key starts with `["events"]`. Structure keys hierarchically: `["events"]`, `["events", id]`, `["events", id, "signups"]`.

**Optimistic updates need five things.** Cancel in-flight queries, snapshot current data, write optimistic value, on error restore snapshot, on settled invalidate to reconcile.

**`isPending` means "no data yet."** v5 renamed: use `isPending` for first-load spinners, `isFetching` for background-refresh indicators. Both can be true simultaneously.

**Server state ≠ client state.** Don't store API responses in `useState`. Read from `q.data` directly.

## Usage in this codebase

### `frontend/src/main.jsx`

QueryClient instantiated with `retry: 1` (snappier failure UX, one retry on transient errors) and `refetchOnWindowFocus: false` (no automatic refetch on tab focus globally — pages opt in). Provider wraps the entire app, including `<BrowserRouter>` and `<AuthProvider>`.

### `frontend/src/pages/admin/EventsSection.jsx`

Canonical list + CRUD pattern. One `useQuery({ queryKey: ["adminEventsList"] })` for the list. Four mutations — create, update, delete, clone — each calling `qc.invalidateQueries({ queryKey: ["adminEventsList"] })` in `onSuccess`. The mutations show toasts via the project's toast helper. The form's module-template dropdown uses a second query with `staleTime: 30_000` since template data changes rarely during a session.

### `frontend/src/pages/UsersAdminPage.jsx`

Parameterized key: `["adminUsers", { include_inactive: showDeactivated }]`. Toggling the "show deactivated" checkbox is a key change — new query, new fetch, old data preserved under the old key. Four mutations (invite, update, deactivate, reactivate) each invalidate `["adminUsers"]` (the prefix), which refetches both active and inactive lists if they're cached. The page maintains separate `createError` and `updateError` state because mutations share the same query but have distinct UX surfaces (D-43.1 bug fix).

### `frontend/src/pages/OrganizerRosterPage.jsx`

Polling + optimistic updates. The roster query has `refetchInterval: 5000, refetchIntervalInBackground: false` — polls every 5s while the tab is focused, pauses when it isn't. The check-in mutation does a full optimistic update:

```jsx
onMutate: async (signupId) => {
  await qc.cancelQueries({ queryKey: ["roster", eventId] });
  const prev = qc.getQueryData(["roster", eventId]);
  qc.setQueryData(["roster", eventId], (old) => /* ... */);
  return { prev };
},
onError: (_err, _id, context) => {
  if (context?.prev) qc.setQueryData(["roster", eventId], context.prev);
  toast.error("Check-in failed. Please retry.");
},
onSettled: () => qc.invalidateQueries({ queryKey: ["roster", eventId] }),
```

This is the canonical pattern; copy it for any "tap to commit, undo on failure" interaction.

### `frontend/src/pages/admin/ImportsSection.jsx`

Conditional polling. `refetchInterval` is a function of the current data: returns `2000` if any import is `"pending"` or `"processing"`, returns `false` otherwise. Saves bandwidth when there's nothing to wait for. The upload mutation invalidates `["adminImports"]` on success.

### `frontend/src/pages/public/EventsBrowsePage.jsx`

`staleTime: 5 * 60 * 1000` on the current-week query — that data only changes once a week so a five-minute freshness window is safe and avoids redundant fetches as users navigate.

### `frontend/src/pages/organizer/OrganizerDashboard.jsx`

Opts back into `refetchOnWindowFocus: true` (overriding the global default) because organizers tab between this dashboard and the roster page and expect counts to refresh when they return.

### `frontend/src/components/admin/SiteSettingsCard.jsx`

Uses `qc.setQueryData(["adminSiteSettings"], row)` after a save to write the server response straight into the cache — avoids the round-trip of an invalidation + refetch when the server returns the canonical row.

## Operational concerns

### React Query DevTools

Not currently installed in this codebase but should be. `npm i -D @tanstack/react-query-devtools` then render `<ReactQueryDevtools />` inside the provider in development. Lets you see every query, its status, observers, last fetch time, and lets you manually invalidate or remove entries. Indispensable for debugging "why isn't this list refreshing?" issues.

### Performance

- **Re-renders.** `useQuery` re-renders on any change to `data`, `error`, or `status`. Use `select` to project just the slice you need; the hook then only re-renders when the projection changes.
- **Key stability.** Object literals in keys (`["users", { filter }]`) work because the library JSON-stringifies, but referentially-stable keys are still cheaper to compare. If you build keys from many filters, consider stable serialization.
- **Bundle.** The library is ~13kb min+gzip. Negligible for an admin app, non-trivial for a marketing site. SWR is a lighter alternative if you don't need mutations or infinite queries.

### Common bugs

- **Filter change does nothing.** Filter not in the key. Add it.
- **Data flashes to "loading" after every mutation.** You're invalidating but the page has no `placeholderData` and no `keepPreviousData`. Either accept the flash or use `placeholderData: (prev) => prev` (v5 idiom) to keep showing the old data during the refetch.
- **List has duplicates after optimistic add.** The `onSuccess` is invalidating before the server's response is reconciled, and the optimistic write isn't being removed. Use `onSettled: invalidate`, not `onSuccess`, for the refetch.
- **Mutation succeeds, UI doesn't update.** Mismatched invalidation key. Check that `qc.invalidateQueries({ queryKey: [...] })` exactly prefixes the query key.
- **Polling never stops.** `refetchInterval: 5000` polls forever. To stop conditionally, pass a function: `refetchInterval: (query) => done ? false : 5000`.
- **`useQuery` with conditional skip.** Don't wrap the hook in an `if`. Use `enabled: !!id`.
- **Stale `queryFn` closure.** If `queryFn` reads a variable, that variable must be in the key. Otherwise the cache hits on the old key while your function silently uses the new value (or vice versa).

### Testing

In Vitest, wrap renders with a fresh `QueryClientProvider`:

```jsx
const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
render(
  <QueryClientProvider client={qc}>
    <MyComponent />
  </QueryClientProvider>
);
```

Disable retries in test to fail fast. Use `qc.setQueryData` to seed the cache when you want to assert against a known state without mocking the network.

### Suspense mode

v5 supports `useSuspenseQuery` — same shape as `useQuery` but throws a promise while pending instead of returning `isPending: true`. Pair with `<Suspense fallback={...}>` and an error boundary. This codebase does not use suspense queries; it uses the imperative `isPending` branch in each component.

### Network resilience

Default retry is 3 with exponential backoff (1s, 2s, 4s). This codebase sets `retry: 1` globally for snappier error states. Critical reads (e.g. roster) might warrant a higher retry count; one-shot writes generally shouldn't auto-retry because the server might have processed the first request — see "non-idempotent mutations."

### Non-idempotent mutations

By default, `useMutation` does not retry on failure (v5 default). If your mutation is non-idempotent (POST that creates a row, charge a card), do not enable retry. If your mutation is idempotent (PUT with the same body, DELETE by id), retry is safe — set `retry: 2` or so. This codebase's mutations do not enable retry, which is the right default.

## Glossary

- **Query** — A cached read identified by a query key. Created on first `useQuery`, populated by `queryFn`, refetched per its options.
- **Mutation** — A one-shot write operation managed by `useMutation`. Does not touch the cache by itself.
- **Query key** — Serializable array that uniquely identifies a query in the cache. Used for dedup, invalidation (by prefix), and direct cache reads/writes.
- **`queryFn`** — Async function that produces the data. Receives a `QueryFunctionContext` (which includes the queryKey and a signal for cancellation).
- **Observer** — A component subscribed to a query via `useQuery`. The cache tracks the observer count; an entry with zero observers starts `gcTime` countdown.
- **`staleTime`** — Duration after which a fresh query becomes stale. Default 0.
- **`gcTime`** (formerly `cacheTime`) — Duration that an unobserved query lingers in the cache before garbage collection. Default 5 minutes.
- **Fresh** — Data is within `staleTime` of last fetch. Subscribing doesn't refetch.
- **Stale** — Data is older than `staleTime`. Served from cache, but a refetch fires in the background.
- **`isPending`** — Status is "pending": no data yet, the first fetch is in flight. v5 rename of v4's `isLoading`.
- **`isFetching`** — A network request is in flight. Can be true while `isSuccess` is also true (background refetch).
- **`invalidateQueries`** — Marks every query matching the filter as stale and refetches each one that has an observer. Filter is a prefix match by default.
- **`setQueryData`** — Synchronously writes a value into the cache for a key. Used in optimistic updates and after-save reconciliation.
- **`cancelQueries`** — Aborts in-flight fetches for matching keys. Used before an optimistic write to prevent stale responses from clobbering it.
- **`onMutate`** — Pre-flight hook in `useMutation`. Returns a context object available to later callbacks. Used to set up optimistic state.
- **`onSettled`** — Post-mutation hook that fires on both success and error. Typically calls `invalidateQueries` to reconcile cache with server.
- **Optimistic update** — Writing the expected post-mutation state into the cache before the server responds, so the UI feels instant. Requires snapshot+rollback for failure cases.
- **`refetchInterval`** — Polling interval in ms, or a function of the query state returning ms or `false`.
- **`placeholderData`** — Initial value shown before the first fetch resolves. Doesn't get cached.
- **`enabled`** — Boolean gate. When false, the query doesn't run and stays in "pending." Used for dependent queries (don't fetch user until you have an id).
- **Suspense query** — `useSuspenseQuery` (v5) — same as `useQuery` but integrates with `<Suspense>` for declarative loading boundaries.
- **`QueryClient`** — The cache root. One per app. Holds all queries, mutations, and defaults.
