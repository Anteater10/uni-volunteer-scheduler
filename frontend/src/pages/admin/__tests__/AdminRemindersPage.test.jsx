// Phase 24 — AdminRemindersPage tests
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("../../../lib/api", () => {
  const listUpcoming = vi.fn();
  const sendNow = vi.fn();
  const api = {
    admin: {
      reminders: {
        listUpcoming,
        sendNow,
      },
    },
  };
  return { api, default: api };
});

vi.mock("../AdminLayout", () => ({
  useAdminPageTitle: () => {},
}));

vi.mock("../../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import { api } from "../../../lib/api";
import AdminRemindersPage from "../AdminRemindersPage";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AdminRemindersPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const ROW = {
  signup_id: "11111111-1111-1111-1111-111111111111",
  volunteer_email: "vee@example.com",
  volunteer_name: "Vee Rem",
  event_id: "22222222-2222-2222-2222-222222222222",
  event_title: "CRISPR Week 4",
  slot_id: "33333333-3333-3333-3333-333333333333",
  slot_start_time: "2030-06-05T17:00:00Z",
  kind: "pre_24h",
  scheduled_for: "2030-06-04T17:00:00Z",
  already_sent: false,
  opted_out: false,
};

describe("AdminRemindersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders rows returned by the backend", async () => {
    api.admin.reminders.listUpcoming.mockResolvedValueOnce([ROW]);

    renderPage();

    await waitFor(() =>
      expect(api.admin.reminders.listUpcoming).toHaveBeenCalledWith(7)
    );
    expect(await screen.findByText("CRISPR Week 4")).toBeInTheDocument();
    expect(screen.getByText("vee@example.com")).toBeInTheDocument();
    expect(screen.getByText("24h")).toBeInTheDocument();
  });

  it("renders the empty state when the list is empty", async () => {
    api.admin.reminders.listUpcoming.mockResolvedValueOnce([]);

    renderPage();

    expect(
      await screen.findByText(/no upcoming reminders/i)
    ).toBeInTheDocument();
  });

  it("calls sendNow with the row's signup id + kind after confirmation", async () => {
    api.admin.reminders.listUpcoming.mockResolvedValue([ROW]);
    api.admin.reminders.sendNow.mockResolvedValueOnce({
      signup_id: ROW.signup_id,
      kind: ROW.kind,
      sent: true,
      reason: "ok",
    });

    renderPage();

    const button = await screen.findByRole("button", { name: /send now/i });
    await userEvent.click(button);
    // Modal opens — click confirm button (there are now two "Send now" buttons;
    // the second is inside the modal)
    const confirmButtons = await screen.findAllByRole("button", {
      name: /send now/i,
    });
    // The modal's button is the second one
    await userEvent.click(confirmButtons[confirmButtons.length - 1]);

    await waitFor(() =>
      expect(api.admin.reminders.sendNow).toHaveBeenCalledWith(
        ROW.signup_id,
        ROW.kind
      )
    );
  });
});
