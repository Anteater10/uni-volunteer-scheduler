// src/pages/__tests__/ManageSignupsPage.test.jsx
//
// Component tests for ManageSignupsPage — 10 test cases.
//
// 2026-08-02 read-only signups: the page no longer supports cancel/move —
// schedule changes are coordinated by emailing the organizers. Tests that
// exercised the removed cancel/move/cancel-all controls were deleted; new
// coverage asserts the controls are gone and the contact notice renders.

import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — declared before component imports so vi.mock hoisting works
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getManageSignups: vi.fn(),
    },
  },
}));

vi.mock("../../state/toast", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}));

import api from "../../lib/api";
import ManageSignupsPage from "../public/ManageSignupsPage";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const SIGNUP_1 = {
  signup_id: "sig-001",
  status: "confirmed",
  slot: {
    id: "slot-001",
    slot_type: "orientation",
    date: "2026-04-22",
    start_time: "2026-04-22T09:00:00",
    end_time: "2026-04-22T11:00:00",
    location: "Room 101",
    capacity: 20,
    filled: 5,
  },
};

const SIGNUP_2 = {
  signup_id: "sig-002",
  status: "pending",
  slot: {
    id: "slot-002",
    slot_type: "period",
    date: "2026-04-23",
    start_time: "2026-04-23T13:00:00",
    end_time: "2026-04-23T15:00:00",
    location: "Room 202",
    capacity: 20,
    filled: 3,
  },
};

const MANAGE_RESPONSE = {
  volunteer_id: "vol-abc",
  volunteer_first_name: "Hung",
  volunteer_last_name: "Khuu",
  event_id: "evt-xyz",
  signups: [SIGNUP_1, SIGNUP_2],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderPage(token = "test_token_abc123") {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/signup/manage?token=${token}`]}>
        <Routes>
          <Route path="/signup/manage" element={<ManageSignupsPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

function renderPageWithOverride(token = "override_token_xyz") {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/"]}>
        <ManageSignupsPage tokenOverride={token} />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ManageSignupsPage", () => {
  it("1. renders signup list with slot types and locations", async () => {
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Room 101")).toBeInTheDocument();
      expect(screen.getByText("Room 202")).toBeInTheDocument();
    });

    // Slot type badges
    expect(screen.getByText("Orientation")).toBeInTheDocument();
    expect(screen.getByText("Period")).toBeInTheDocument();
  });

  it("2. token error — shows 'Link expired or invalid' card", async () => {
    const err = new Error("token invalid or expired");
    err.status = 400;
    api.public.getManageSignups.mockRejectedValue(err);

    renderPage();

    await waitFor(() => {
      // Phase 15-05: shared ErrorState with UI-SPEC network-error copy.
      expect(screen.getByText("We couldn't load this page")).toBeInTheDocument();
    });
  });

  it("3. loading state — shows skeleton elements", () => {
    // Return a promise that never resolves so we stay in loading state
    api.public.getManageSignups.mockReturnValue(new Promise(() => {}));

    renderPage();

    // Skeletons should render during loading
    const skeletons = document.querySelectorAll(".rounded-xl");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("4. empty state — shows 'No upcoming signups' message", async () => {
    api.public.getManageSignups.mockResolvedValue({
      volunteer_id: "vol-abc",
      volunteer_first_name: "Hung",
      volunteer_last_name: "Khuu",
      event_id: "evt-xyz",
      signups: [],
    });

    renderPage();

    await waitFor(() => {
      // Phase 15-05: UI-SPEC empty-state copy + "View events" primary action.
      expect(
        screen.getByText("You haven't signed up for anything yet")
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /view events/i })
    ).toBeInTheDocument();
  });

  it("5. greets the volunteer by first name in the page header", async () => {
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Hi Hung")).toBeInTheDocument();
    });
  });

  it("6. falls back to 'Your signups' when name fields are absent", async () => {
    api.public.getManageSignups.mockResolvedValue({
      volunteer_id: "vol-abc",
      event_id: "evt-xyz",
      signups: [SIGNUP_1, SIGNUP_2],
    });

    renderPage();

    // Kicker copy also reads "Your signups" now, so the heading must be
    // targeted specifically (by role) to avoid an ambiguous text match.
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Your signups", level: 1 })
      ).toBeInTheDocument();
    });
  });

  // Phase 25 (WAIT-01) — waitlist position badge renders with the FIFO rank.
  it("7. shows 'Waitlist #N' badge for waitlisted signups", async () => {
    const WAITLISTED_SIGNUP = {
      signup_id: "sig-wait",
      status: "waitlisted",
      waitlist_position: 3,
      slot: {
        id: "slot-wait",
        slot_type: "period",
        date: "2026-04-24",
        start_time: "2026-04-24T10:00:00",
        end_time: "2026-04-24T12:00:00",
        location: "Room 303",
        capacity: 5,
        filled: 5,
      },
    };
    api.public.getManageSignups.mockResolvedValue({
      volunteer_id: "vol-abc",
      volunteer_first_name: "Hung",
      volunteer_last_name: "Khuu",
      event_id: "evt-xyz",
      signups: [WAITLISTED_SIGNUP],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Waitlist #3/i)).toBeInTheDocument();
    });
    const badge = screen.getByTestId("waitlist-badge");
    expect(badge).toHaveTextContent(/Waitlist #3/i);
  });

  // 2026-08-02 read-only signups — cancel/move controls are gone; schedule
  // changes are coordinated by emailing the organizers instead.
  it("8. renders read-only: no cancel or move controls", async () => {
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);

    renderPage();

    await screen.findAllByText(/Confirmed|Pending/);
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /move/i })).toBeNull();
  });

  it("9. shows the organizer contact notice with the configured address", async () => {
    api.public.getManageSignups.mockResolvedValue({
      ...MANAGE_RESPONSE,
      contact_email: "scitrek@ucsb.edu",
    });

    renderPage();

    const notice = await screen.findByTestId("contact-notice");
    expect(notice).toHaveTextContent("scitrek@ucsb.edu");
  });

  it("10. contact notice falls back when no address configured", async () => {
    api.public.getManageSignups.mockResolvedValue({
      ...MANAGE_RESPONSE,
      contact_email: null,
    });

    renderPage();

    const notice = await screen.findByTestId("contact-notice");
    expect(notice).toHaveTextContent(/reply to your confirmation email/i);
  });
});
