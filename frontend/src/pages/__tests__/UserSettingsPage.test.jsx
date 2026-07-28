import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// Hoisted so individual tests can reshape the signed-in user.
const authState = vi.hoisted(() => ({
  user: {
    id: "u-1",
    name: "Andy S",
    email: "andy@ucsb.edu",
    role: "admin",
    university_id: "1234567",
    notify_email: true,
  },
  reloadMe: null,
  logout: null,
}));

vi.mock("../../state/useAuth", () => ({
  useAuth: () => ({
    user: authState.user,
    reloadMe: authState.reloadMe,
    logout: authState.logout,
  }),
}));

vi.mock("../../lib/api", () => {
  const apiMock = {
    updateMe: vi.fn(async () => ({})),
    changePassword: vi.fn(async () => ({ status: "ok" })),
  };
  return { default: apiMock, api: apiMock };
});

// The copilot memory panel does its own fetch on mount; it is gated behind the
// flag in the page, but stub it so an accidental render can't hit the network.
vi.mock("../../copilot/CopilotMemorySettings", () => ({
  default: () => <div data-testid="copilot-memory" />,
}));

import { api } from "../../lib/api";
import UserSettingsPage from "../UserSettingsPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <UserSettingsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("UserSettingsPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authState.user = {
      id: "u-1",
      name: "Andy S",
      email: "andy@ucsb.edu",
      role: "admin",
      university_id: "1234567",
      notify_email: true,
    };
    authState.reloadMe = vi.fn(async () => authState.user);
    authState.logout = vi.fn();
  });

  it("seeds the form from the signed-in user", () => {
    renderPage();
    expect(screen.getByLabelText(/display name/i)).toHaveValue("Andy S");
    expect(screen.getByLabelText(/university id/i)).toHaveValue("1234567");
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("shows email and role as read-only text, not inputs", () => {
    renderPage();
    // Both must be visible — they identify the user in the audit log — but
    // neither is self-editable, so they must not render as form fields.
    // (PR #51: the wide layout repeats them in the identity card, so allow
    // more than one occurrence.)
    expect(screen.getAllByText("andy@ucsb.edu").length).toBeGreaterThan(0);
    expect(screen.getAllByText("admin").length).toBeGreaterThan(0);
    expect(screen.queryByLabelText(/^email$/i)).toBeNull();
    expect(screen.queryByLabelText(/^role$/i)).toBeNull();
  });

  it("keeps Save disabled until something changes", async () => {
    renderPage();
    const save = screen.getByRole("button", { name: /save changes/i });
    expect(save).toBeDisabled();

    await userEvent.type(screen.getByLabelText(/display name/i), "!");
    expect(save).toBeEnabled();
    expect(screen.getByText(/unsaved changes/i)).toBeInTheDocument();
  });

  it("PATCHes only the self-editable fields and refreshes the cached user", async () => {
    renderPage();
    const nameField = screen.getByLabelText(/display name/i);
    await userEvent.clear(nameField);
    await userEvent.type(nameField, "Andy Subramanian");
    await userEvent.click(screen.getByRole("checkbox"));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(api.updateMe).toHaveBeenCalledTimes(1));
    expect(api.updateMe).toHaveBeenCalledWith({
      name: "Andy Subramanian",
      university_id: "1234567",
      notify_email: false,
    });
    await waitFor(() => expect(authState.reloadMe).toHaveBeenCalled());
  });

  it("sends null for a cleared university ID so the column clears", async () => {
    renderPage();
    await userEvent.clear(screen.getByLabelText(/university id/i));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    await waitFor(() => expect(api.updateMe).toHaveBeenCalled());
    expect(api.updateMe.mock.calls[0][0].university_id).toBeNull();
  });

  it("refuses to save an empty display name", async () => {
    renderPage();
    await userEvent.clear(screen.getByLabelText(/display name/i));
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText(/can't be empty/i)).toBeInTheDocument();
    expect(api.updateMe).not.toHaveBeenCalled();
  });

  it("surfaces a save failure instead of claiming success", async () => {
    api.updateMe.mockRejectedValueOnce(new Error("Network down"));
    renderPage();
    await userEvent.type(screen.getByLabelText(/display name/i), "!");
    await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

    expect(await screen.findByText("Network down")).toBeInTheDocument();
  });

  it("logs out from the session section", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: /log out/i }));
    expect(authState.logout).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // PR #51 — change password
  // -------------------------------------------------------------------------

  it("renders the password section with three fields", () => {
    renderPage();
    expect(screen.getByLabelText(/current password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^new password/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/confirm new password/i)).toBeInTheDocument();
  });

  it("submits the change and clears the fields on success", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText(/current password/i), "old-pass-123");
    await userEvent.type(screen.getByLabelText(/^new password/i), "new-pass-456");
    await userEvent.type(screen.getByLabelText(/confirm new password/i), "new-pass-456");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    await waitFor(() => {
      expect(api.changePassword).toHaveBeenCalledWith("old-pass-123", "new-pass-456");
    });
    expect(screen.getByLabelText(/current password/i)).toHaveValue("");
  });

  it("refuses mismatched confirmation without calling the API", async () => {
    renderPage();
    await userEvent.type(screen.getByLabelText(/current password/i), "old-pass-123");
    await userEvent.type(screen.getByLabelText(/^new password/i), "new-pass-456");
    await userEvent.type(screen.getByLabelText(/confirm new password/i), "different");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(await screen.findByText(/don't match/i)).toBeInTheDocument();
    expect(api.changePassword).not.toHaveBeenCalled();
  });

  it("surfaces a change-password failure", async () => {
    api.changePassword.mockRejectedValueOnce(new Error("Current password is incorrect."));
    renderPage();
    await userEvent.type(screen.getByLabelText(/current password/i), "wrong");
    await userEvent.type(screen.getByLabelText(/^new password/i), "new-pass-456");
    await userEvent.type(screen.getByLabelText(/confirm new password/i), "new-pass-456");
    await userEvent.click(screen.getByRole("button", { name: /change password/i }));
    expect(
      await screen.findByText(/current password is incorrect/i),
    ).toBeInTheDocument();
  });
});
