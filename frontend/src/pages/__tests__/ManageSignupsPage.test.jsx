// src/pages/__tests__/ManageSignupsPage.test.jsx
//
// Component tests for ManageSignupsPage — 7 test cases.

import React from "react";
import { render, screen, waitFor, fireEvent, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — declared before component imports so vi.mock hoisting works
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getManageSignups: vi.fn(),
      cancelSignup: vi.fn(),
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
import { toast } from "../../state/toast";
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

  it("2. cancel single — modal opens, signup removed on confirm, toast shown", async () => {
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);
    api.public.cancelSignup.mockResolvedValue({ cancelled: true, signup_id: "sig-001" });

    renderPage();

    // Wait for signups to load
    await waitFor(() => {
      expect(screen.getByText("Room 101")).toBeInTheDocument();
    });

    // Click Cancel on the first signup
    const cancelButtons = screen.getAllByRole("button", { name: /cancel/i });
    // The first one is for SIGNUP_1
    fireEvent.click(cancelButtons[0]);

    // Modal should appear
    await waitFor(() => {
      expect(screen.getByText("Cancel this signup?")).toBeInTheDocument();
    });

    // Confirm cancellation
    const yesBtn = screen.getByRole("button", { name: /yes, cancel/i });
    await act(async () => {
      fireEvent.click(yesBtn);
    });

    // Signup should be removed from list
    await waitFor(() => {
      expect(screen.queryByText("Room 101")).not.toBeInTheDocument();
    });

    expect(toast.success).toHaveBeenCalledWith("Signup cancelled.");
  });

  it("3. cancel all — sequential loop removes both signups, success toast shown", async () => {
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);
    api.public.cancelSignup.mockResolvedValue({ cancelled: true });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Room 101")).toBeInTheDocument();
    });

    // Click "Cancel all signups"
    const cancelAllBtn = screen.getByRole("button", { name: /cancel all signups/i });
    fireEvent.click(cancelAllBtn);

    // Modal should appear
    await waitFor(() => {
      expect(screen.getByText(/cancel all 2 signups/i)).toBeInTheDocument();
    });

    // Confirm
    const yesAllBtn = screen.getByRole("button", { name: /yes, cancel all/i });
    await act(async () => {
      fireEvent.click(yesAllBtn);
    });

    // Both signups removed
    await waitFor(() => {
      expect(screen.queryByText("Room 101")).not.toBeInTheDocument();
      expect(screen.queryByText("Room 202")).not.toBeInTheDocument();
    });

    expect(api.public.cancelSignup).toHaveBeenCalledTimes(2);
    expect(toast.success).toHaveBeenCalledWith("All signups cancelled.");
  });

  it("4. token error — shows 'Link expired or invalid' card", async () => {
    const err = new Error("token invalid or expired");
    err.status = 400;
    api.public.getManageSignups.mockRejectedValue(err);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Link expired or invalid")).toBeInTheDocument();
    });
  });

  it("5. loading state — shows skeleton elements", () => {
    // Return a promise that never resolves so we stay in loading state
    api.public.getManageSignups.mockReturnValue(new Promise(() => {}));

    renderPage();

    // Skeletons should render during loading
    const skeletons = document.querySelectorAll(".rounded-xl");
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it("6. empty state — shows 'No upcoming signups' message", async () => {
    api.public.getManageSignups.mockResolvedValue({
      volunteer_id: "vol-abc",
      event_id: "evt-xyz",
      signups: [],
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No upcoming signups found for this event.")).toBeInTheDocument();
    });
  });

  it("7. 403 on cancel — shows permission error toast", async () => {
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);
    const err = new Error("token does not own this signup");
    err.status = 403;
    api.public.cancelSignup.mockRejectedValue(err);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Room 101")).toBeInTheDocument();
    });

    // Click Cancel
    const cancelButtons = screen.getAllByRole("button", { name: /cancel/i });
    fireEvent.click(cancelButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Cancel this signup?")).toBeInTheDocument();
    });

    const yesBtn = screen.getByRole("button", { name: /yes, cancel/i });
    await act(async () => {
      fireEvent.click(yesBtn);
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        "You don't have permission to cancel this signup."
      );
    });
  });
});
