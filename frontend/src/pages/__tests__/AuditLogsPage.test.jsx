// src/pages/__tests__/AuditLogsPage.test.jsx
//
// Phase 16 Plan 04 Task 2 — Audit Log page regression tests.
// Covers 5-column table, SideDrawer on row click, search -> URL query param,
// explainer sentence verbatim, and the D-19 no-UUIDs gate.

import React from "react";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Routes, Route, useLocation } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => {
  const auditLogs = vi.fn();
  const usersList = vi.fn();
  const api = {
    admin: {
      auditLogs,
      users: { list: usersList },
    },
  };
  return {
    default: api,
    api,
    downloadBlob: vi.fn(),
  };
});

vi.mock("../admin/AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import api, { downloadBlob } from "../../lib/api";
import AuditLogsPage from "../AuditLogsPage";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ROWS = [
  {
    id: "log-1",
    timestamp: new Date(Date.now() - 2 * 60_000).toISOString(),
    actor_label: "Andy Admin",
    actor_role: "admin",
    action_label: "Invited a new user",
    entity_label: "Jane Newcomer",
    extra: { email: "jane@example.com" },
  },
  {
    id: "log-2",
    timestamp: new Date(Date.now() - 10 * 60_000).toISOString(),
    actor_label: "Olivia Organizer",
    actor_role: "organizer",
    action_label: "Cancelled a signup",
    entity_label: "a student at DNA Extraction",
    extra: {},
  },
  {
    id: "log-3",
    timestamp: new Date(Date.now() - 30 * 60_000).toISOString(),
    actor_label: "System",
    actor_role: null,
    action_label: "Logged in",
    entity_label: "Andy Admin",
    extra: {},
  },
];

const USERS = [
  { id: "u-1", name: "Andy Admin", email: "andy@example.com", role: "admin" },
  { id: "u-2", name: "Olivia Organizer", email: "o@example.com", role: "organizer" },
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

// Tiny probe to read the current URL search string from inside the router.
function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc-search">{loc.search}</div>;
}

function renderPage(initialEntries = ["/admin/audit-logs"]) {
  return render(
    <MemoryRouter initialEntries={initialEntries}>
      <QueryClientProvider client={makeQueryClient()}>
        <Routes>
          <Route
            path="/admin/audit-logs"
            element={
              <>
                <AuditLogsPage />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AuditLogsPage", () => {
  beforeEach(() => {
    api.admin.auditLogs.mockReset();
    api.admin.users.list.mockReset();
    downloadBlob.mockReset();
    api.admin.auditLogs.mockResolvedValue({
      items: ROWS,
      total: 3,
      page: 1,
      page_size: 25,
      pages: 1,
    });
    api.admin.users.list.mockResolvedValue({ items: USERS });
  });

  it("renders the 5-column table header in the correct order", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Jane Newcomer")).toBeInTheDocument(),
    );
    const headers = screen
      .getAllByRole("columnheader")
      .map((th) => th.textContent.trim());
    expect(headers).toEqual([
      "When",
      "Who",
      "What",
      "Target",
      "Details",
    ]);
  });

  it("renders the explainer sentence verbatim", async () => {
    renderPage();
    expect(
      screen.getByText(
        /This page shows a history of every important change to the system — who did what, when, and to what\. Use the filters to narrow down what you're looking for\./,
      ),
    ).toBeInTheDocument();
  });

  it("opens the SideDrawer with JSON payload when a row is clicked", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Jane Newcomer")).toBeInTheDocument(),
    );
    // Click the humanized entity label cell — unambiguous (not in any dropdown).
    fireEvent.click(screen.getByText("Jane Newcomer"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Raw payload/i)).toBeInTheDocument();
    // JSON includes the action_label
    expect(
      within(dialog).getByText(/"action_label": "Invited a new user"/),
    ).toBeInTheDocument();
    // Copy button present
    expect(
      within(dialog).getByRole("button", { name: /Copy to clipboard/i }),
    ).toBeInTheDocument();
  });

  it("typing in the search box updates the `q` URL param", async () => {
    renderPage();
    await waitFor(() =>
      expect(screen.getByText("Invited a new user")).toBeInTheDocument(),
    );
    const search = screen.getByPlaceholderText(/Search/i);
    fireEvent.change(search, { target: { value: "invite" } });
    await waitFor(() => {
      const loc = screen.getByTestId("loc-search").textContent;
      expect(loc).toContain("q=invite");
      expect(loc).toContain("page=1");
    });
  });

  it("D-19 gate: no UUIDs in the rendered table body", async () => {
    const { container } = renderPage();
    await waitFor(() =>
      expect(screen.getByText("Invited a new user")).toBeInTheDocument(),
    );
    const text = container.textContent || "";
    const uuidRe = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i;
    expect(uuidRe.test(text)).toBe(false);
  });

  it("Export button calls downloadBlob with current filter params", async () => {
    renderPage(["/admin/audit-logs?q=invite&kind=user_invite"]);
    await waitFor(() =>
      expect(screen.getByText("Invited a new user")).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByRole("button", { name: /Export filtered view/i }),
    );
    expect(downloadBlob).toHaveBeenCalledWith(
      "/admin/audit-logs.csv",
      "audit-logs.csv",
      expect.objectContaining({
        params: expect.objectContaining({ q: "invite", kind: "user_invite" }),
      }),
    );
  });
});
