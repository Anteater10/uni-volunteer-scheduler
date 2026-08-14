/**
 * W5.17 — route-level authorization, pinned.
 *
 * The W5 authz sweep covered backend routers only. Nothing asserted the
 * frontend's half: which roles may *reach* which screen. That gating lives in
 * one nested `<ProtectedRoute roles={["admin"]}>` block in App.jsx, so adding a
 * route one line above or below it silently changes its audience, and no test
 * — until this one — would have noticed.
 *
 * This is defence in depth, not the boundary: every admin-only route here was
 * verified during the review to be admin-only on the backend too (analytics,
 * audit logs, quarters, users, orientation credits all take
 * `require_role(admin)`). A regression here is a UI leak, not a data leak. It
 * still matters — rendering the Users screen to an organizer tells them the
 * screen exists and what is on it, which is a disclosure of its own.
 *
 * Nothing here mounts a real page: ProtectedRoute short-circuits before the
 * element renders on the deny path, and on the allow path the assertion is only
 * the *absence* of the refusal, so the pages' own data fetching is irrelevant.
 */
import React from "react";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const authState = vi.hoisted(() => ({ role: "admin", isAuthed: true }));

vi.mock("../state/useAuth", () => ({
  useAuth: () => ({
    user: authState.isAuthed
      ? { name: "Test", email: "test@example.com", role: authState.role }
      : null,
    role: authState.isAuthed ? authState.role : null,
    isAuthed: authState.isAuthed,
    initializing: false,
    logout: vi.fn(),
  }),
}));

// The admin shell fetches quarters and site settings on mount. Anything not
// named here resolves to an empty array, so a page that starts fetching on the
// allow path cannot fail the test with an unrelated network error.
vi.mock("../lib/api", () => {
  const stub = async () => [];
  const deep = () =>
    new Proxy(vi.fn(stub), {
      get: (target, prop) => {
        if (prop in target) return target[prop];
        if (!target[prop]) target[prop] = deep();
        return target[prop];
      },
    });
  const apiMock = deep();
  apiMock.public.getQuarters = vi.fn(async () => []);
  apiMock.admin.siteSettings.get = vi.fn(async () => ({
    show_audit_logs_tab: false,
  }));
  return { default: apiMock, api: apiMock };
});

import App from "../App";

const ADMIN_ONLY = [
  "/admin/users",
  "/admin/audit-logs",
  "/admin/exports",
  "/admin/orientation-credits",
  "/admin/quarters",
];

// Shared staff surfaces. /admin/copilot-feedback is deliberately here: the K33
// acceptance (docs/security-review-w5.md) rules that organizers keep this
// access, so it is pinned as *intended* shared rather than left ambiguous.
const STAFF_SHARED = [
  "/admin/events",
  "/admin/operations",
  "/admin/modules",
  "/admin/copilot-feedback",
  "/admin/settings",
  "/organizer/today",
  "/notifications",
];

function renderAt(path) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  authState.role = "admin";
  authState.isAuthed = true;
});

describe("route authorization", () => {
  describe.each(ADMIN_ONLY)("%s — admin only", (path) => {
    it("refuses an organizer", () => {
      authState.role = "organizer";
      renderAt(path);
      expect(screen.getByText("Forbidden")).toBeInTheDocument();
    });

    it("admits an admin", () => {
      authState.role = "admin";
      renderAt(path);
      expect(screen.queryByText("Forbidden")).not.toBeInTheDocument();
    });
  });

  describe.each(STAFF_SHARED)("%s — admin and organizer", (path) => {
    it("admits an organizer", () => {
      authState.role = "organizer";
      renderAt(path);
      expect(screen.queryByText("Forbidden")).not.toBeInTheDocument();
    });
  });

  it("sends a signed-out visitor to the login page, not to the screen", () => {
    authState.isAuthed = false;
    renderAt("/admin/users");
    expect(screen.queryByText("Forbidden")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: /welcome back/i }),
    ).toBeInTheDocument();
  });

  it("refuses a participant every staff surface", () => {
    authState.role = "participant";
    renderAt("/admin/events");
    expect(screen.getByText("Forbidden")).toBeInTheDocument();
  });
});
