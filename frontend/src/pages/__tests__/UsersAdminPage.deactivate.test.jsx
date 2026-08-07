// K13 — Deactivate used to fire on one click.
//
// It sat in the same drawer as a type-to-confirm CCPA delete: the two most
// destructive buttons on the page, a few pixels apart, with completely
// different guards. A deactivated user is signed out and cannot sign back in,
// which for an organizer means it happens the morning of a school visit.

import React from "react";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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

const ADMIN = {
  id: "1",
  email: "alice@example.com",
  name: "Alice",
  role: "admin",
  is_active: true,
  last_login_at: null,
  university_id: "",
  notify_email: true,
};

// A second admin, so deactivating Bob is not blocked by the last-active-admin
// guard and the dialog is what stands in the way.
const BOB = {
  id: "2",
  email: "bob@example.com",
  name: "Bob",
  role: "admin",
  is_active: true,
  last_login_at: "2026-04-14T10:00:00Z",
  university_id: "",
  notify_email: true,
};

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

async function openBobsDrawer() {
  renderPage();
  await screen.findByText("bob@example.com");
  fireEvent.click(screen.getByText("bob@example.com"));
  await screen.findByRole("button", { name: /^deactivate$/i });
}

beforeEach(() => {
  vi.clearAllMocks();
  api.admin.users.list.mockResolvedValue([ADMIN, BOB]);
  api.admin.users.deactivate.mockResolvedValue({});
});

describe("UsersAdminPage — deactivate is confirmed first (K13)", () => {
  it("does not call the API on the first click", async () => {
    await openBobsDrawer();

    fireEvent.click(screen.getByRole("button", { name: /^deactivate$/i }));

    expect(await screen.findByRole("dialog", { name: /deactivate this account/i })).toBeInTheDocument();
    expect(api.admin.users.deactivate).not.toHaveBeenCalled();
  });

  it("names the user, so it is obvious which account is about to go", async () => {
    await openBobsDrawer();
    fireEvent.click(screen.getByRole("button", { name: /^deactivate$/i }));

    const dialog = await screen.findByRole("dialog", { name: /deactivate this account/i });
    expect(dialog).toHaveTextContent("Bob");
    // Reversible, and the dialog has to say so — otherwise an admin who needs
    // to do this will hesitate over something that is undoable in one click.
    expect(dialog).toHaveTextContent(/reactivate them at any time/i);
  });

  it("leaves the account alone when cancelled", async () => {
    await openBobsDrawer();
    fireEvent.click(screen.getByRole("button", { name: /^deactivate$/i }));
    await screen.findByRole("dialog", { name: /deactivate this account/i });

    fireEvent.click(screen.getByRole("button", { name: /^cancel$/i }));

    await waitFor(() => expect(screen.queryByRole("dialog", { name: /deactivate this account/i })).toBeNull());
    expect(api.admin.users.deactivate).not.toHaveBeenCalled();
  });

  it("deactivates once confirmed", async () => {
    await openBobsDrawer();
    fireEvent.click(screen.getByRole("button", { name: /^deactivate$/i }));
    const dialog = await screen.findByRole("dialog", { name: /deactivate this account/i });

    fireEvent.click(
      within(dialog).getByRole("button", { name: /^deactivate$/i }),
    );

    await waitFor(() =>
      expect(api.admin.users.deactivate).toHaveBeenCalledWith("2"),
    );
  });
});
