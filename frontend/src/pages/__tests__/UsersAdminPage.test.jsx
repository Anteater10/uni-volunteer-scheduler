// src/pages/__tests__/UsersAdminPage.test.jsx
//
// Phase 16 Plan 05 — UsersAdminPage rewrite tests.
// Covers ADMIN-18..21 + ADMIN-24 CCPA and the D-43.1 shared-err regression.

import React from "react";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — declared before component imports so vi.mock hoisting works
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    admin: {
      users: {
        list: vi.fn(),
        invite: vi.fn(),
        update: vi.fn(),
        deactivate: vi.fn(),
        reactivate: vi.fn(),
        ccpaExport: vi.fn(),
        ccpaDelete: vi.fn(),
      },
    },
  },
}));

vi.mock("../../state/toast", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({
    user: { id: "current-user-id", email: "me@example.com", role: "admin" },
  }),
}));

vi.mock("../admin/AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

import api from "../../lib/api";
import UsersAdminPage from "../UsersAdminPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UsersAdminPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const ALICE = {
  id: "1",
  email: "alice@example.com",
  name: "Alice",
  role: "admin",
  is_active: true,
  last_login_at: null,
  university_id: "",
  notify_email: true,
};

const BOB = {
  id: "2",
  email: "bob@example.com",
  name: "Bob",
  role: "organizer",
  is_active: true,
  last_login_at: "2026-04-14T10:00:00Z",
  university_id: "",
  notify_email: true,
};

beforeEach(() => {
  vi.clearAllMocks();
  api.admin.users.list.mockResolvedValue([ALICE, BOB]);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("UsersAdminPage", () => {
  it("renders the table with all 5 expected columns", async () => {
    renderPage();
    await screen.findByText("alice@example.com");
    expect(screen.getByRole("columnheader", { name: "Name" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Email" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Role" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Last login" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
  });

  it("role filter dropdown does not include 'participant'", async () => {
    renderPage();
    await screen.findByText("alice@example.com");
    const roleFilter = screen.getByLabelText(/filter by role/i);
    const optionValues = Array.from(roleFilter.querySelectorAll("option")).map(
      (o) => o.value,
    );
    expect(optionValues).not.toContain("participant");
  });

  it("invite form does not have a password field", async () => {
    renderPage();
    await screen.findByText("alice@example.com");
    fireEvent.click(screen.getByRole("button", { name: /invite user/i }));
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    // Role select in invite form also lacks participant
    const inviteRole = screen.getByLabelText(/^role$/i);
    const values = Array.from(inviteRole.querySelectorAll("option")).map(
      (o) => o.value,
    );
    expect(values).not.toContain("participant");
  });

  it("'Show deactivated' toggle starts unchecked", async () => {
    renderPage();
    await screen.findByText("alice@example.com");
    const toggle = screen.getByLabelText(/show deactivated/i);
    expect(toggle).not.toBeChecked();
  });

  it("[D-43.1 regression] keeps the user list visible when invite fails with 'Email already exists'", async () => {
    api.admin.users.invite.mockRejectedValue(new Error("Email already exists"));
    renderPage();
    await screen.findByText("alice@example.com");

    fireEvent.click(screen.getByRole("button", { name: /invite user/i }));

    const drawer = screen.getByRole("dialog");
    fireEvent.change(within(drawer).getByLabelText(/name/i), {
      target: { value: "New Person" },
    });
    fireEvent.change(within(drawer).getByLabelText(/email/i), {
      target: { value: "alice@example.com" },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: /send invite/i }));

    await waitFor(() =>
      expect(screen.getByText("Email already exists")).toBeInTheDocument(),
    );
    // CRITICAL: list is still rendered, NOT the load-error empty state
    expect(screen.queryByText(/couldn't load users/i)).toBeNull();
    expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  });

  it("disables Deactivate on the last active admin row", async () => {
    api.admin.users.list.mockResolvedValue([ALICE]); // Alice is the only admin
    renderPage();
    await screen.findByText("alice@example.com");
    fireEvent.click(screen.getByText("alice@example.com"));
    const drawer = screen.getByRole("dialog");
    const deactivateBtn = within(drawer).getByRole("button", { name: /deactivate/i });
    expect(deactivateBtn).toBeDisabled();
    expect(deactivateBtn).toHaveAttribute(
      "title",
      expect.stringMatching(/last active admin|your own account/i),
    );
  });

  it("shows CCPA Export + CCPA Delete buttons in the edit drawer", async () => {
    renderPage();
    await screen.findByText("bob@example.com");
    fireEvent.click(screen.getByText("bob@example.com"));
    const drawer = screen.getByRole("dialog");
    expect(
      within(drawer).getByRole("button", { name: /ccpa data export/i }),
    ).toBeInTheDocument();
    expect(
      within(drawer).getByRole("button", { name: /ccpa delete account/i }),
    ).toBeInTheDocument();
  });
});
