// Phase 24 — AdminRemindersPage tests
import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
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
    // The reminder kind is now shown as a grouped section header rather than
    // a per-row badge.
    expect(screen.getByText("24 hours before")).toBeInTheDocument();
    expect(
      screen.getByTestId("reminders-group-pre_24h")
    ).toBeInTheDocument();
  });

  it("renders the empty state when the list is empty", async () => {
    api.admin.reminders.listUpcoming.mockResolvedValueOnce([]);

    renderPage();

    expect(
      await screen.findByText(/no upcoming reminders/i)
    ).toBeInTheDocument();
  });

  it("groups many reminders by kind in kickoff → 24h → 2h order, only for kinds present", async () => {
    api.admin.reminders.listUpcoming.mockResolvedValueOnce([
      { ...ROW, signup_id: "aaaaaaaa-0000-0000-0000-000000000001", kind: "pre_2h" },
      { ...ROW, signup_id: "aaaaaaaa-0000-0000-0000-000000000002", kind: "kickoff" },
      { ...ROW, signup_id: "aaaaaaaa-0000-0000-0000-000000000003", kind: "kickoff" },
      { ...ROW, signup_id: "aaaaaaaa-0000-0000-0000-000000000004", kind: "pre_24h" },
    ]);

    renderPage();

    await screen.findByTestId("reminders-group-kickoff");
    // Sections render in the canonical firing order, regardless of the order
    // the API returned the rows in.
    const sections = screen.getAllByTestId(/^reminders-group-/);
    expect(sections.map((s) => s.getAttribute("data-testid"))).toEqual([
      "reminders-group-kickoff",
      "reminders-group-pre_24h",
      "reminders-group-pre_2h",
    ]);
    // Each section holds only its own rows (header row + data rows).
    expect(
      within(sections[0]).getAllByText("vee@example.com"),
    ).toHaveLength(2);
    expect(
      within(sections[1]).getAllByText("vee@example.com"),
    ).toHaveLength(1);
    expect(
      within(sections[2]).getAllByText("vee@example.com"),
    ).toHaveLength(1);
  });

  it("renders only the section for the single kind present", async () => {
    api.admin.reminders.listUpcoming.mockResolvedValueOnce([ROW]);

    renderPage();

    await screen.findByTestId("reminders-group-pre_24h");
    expect(screen.queryByTestId("reminders-group-kickoff")).toBeNull();
    expect(screen.queryByTestId("reminders-group-pre_2h")).toBeNull();
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
