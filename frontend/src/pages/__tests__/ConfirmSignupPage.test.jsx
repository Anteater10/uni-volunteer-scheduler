// src/pages/__tests__/ConfirmSignupPage.test.jsx
//
// Component tests for ConfirmSignupPage — 4 test cases.

import React from "react";
import { render, screen, waitFor, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — declared before component imports so vi.mock hoisting works
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      confirmSignup: vi.fn(),
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
import ConfirmSignupPage from "../public/ConfirmSignupPage";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MANAGE_RESPONSE = {
  volunteer_id: "vol-abc",
  event_id: "evt-xyz",
  signups: [
    {
      signup_id: "sig-001",
      status: "confirmed",
      slot: {
        id: "slot-001",
        slot_type: "period",
        date: "2026-04-22",
        start_time: "2026-04-22T09:00:00",
        end_time: "2026-04-22T11:00:00",
        location: "Room 101",
        capacity: 20,
        filled: 5,
      },
    },
  ],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderWithToken(token) {
  const path = token ? `/signup/confirm?token=${token}` : "/signup/confirm";
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/signup/confirm" element={<ConfirmSignupPage />} />
        </Routes>
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

describe("ConfirmSignupPage", () => {
  it("1. confirm success — shows spinner then transitions to manage view", async () => {
    api.public.confirmSignup.mockResolvedValue({
      confirmed: true,
      signup_count: 1,
      idempotent: false,
    });
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);

    const { container } = renderWithToken("valid_token_abc123");

    // Skeleton loading region shown initially (Phase 15-05: replaced
    // animate-spin spinner with aria-busy Skeleton stack).
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();

    // After confirm resolves, manage view appears
    await waitFor(() => {
      expect(screen.getByText("Room 101")).toBeInTheDocument();
    });

    // Success banner
    expect(screen.getByText(/your signup is confirmed/i)).toBeInTheDocument();
  });

  it("2. confirm error — shows 'Link expired or invalid' error card", async () => {
    const err = new Error("token expired");
    err.status = 400;
    api.public.confirmSignup.mockRejectedValue(err);

    renderWithToken("expired_token_xyz");

    await waitFor(() => {
      // Phase 15-05: ErrorState with UI-SPEC magic-link-expired copy.
      expect(screen.getByText("This link has expired")).toBeInTheDocument();
    });

    // Body copy + "Back to events" primary action present.
    expect(
      screen.getByText(/Magic links are good for 24 hours/i)
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /back to events/i })
    ).toBeInTheDocument();

    // No retry button (per decision 7)
    expect(
      screen.queryByRole("button", { name: /retry/i })
    ).not.toBeInTheDocument();
  });

  it("3. already confirmed (idempotent) — still shows manage view", async () => {
    api.public.confirmSignup.mockResolvedValue({
      confirmed: true,
      signup_count: 0,
      idempotent: true,
    });
    api.public.getManageSignups.mockResolvedValue(MANAGE_RESPONSE);

    const { container } = renderWithToken("used_token_def456");

    // Skeleton loading region shown initially (Phase 15-05).
    expect(container.querySelector('[aria-busy="true"]')).toBeInTheDocument();

    // After idempotent confirm resolves, manage view still appears
    await waitFor(() => {
      expect(screen.getByText("Room 101")).toBeInTheDocument();
    });
  });

  it("4. no token in URL — shows error card immediately", async () => {
    // No token — should go to error state without calling the API
    renderWithToken(null);

    await waitFor(() => {
      // Phase 15-05: shared ErrorState with magic-link copy.
      expect(screen.getByText("This link has expired")).toBeInTheDocument();
    });

    // confirmSignup should NOT have been called
    expect(api.public.confirmSignup).not.toHaveBeenCalled();
  });
});
