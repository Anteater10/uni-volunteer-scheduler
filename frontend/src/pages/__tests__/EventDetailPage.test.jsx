// src/pages/__tests__/EventDetailPage.test.jsx
//
// Component tests for EventDetailPage: slot checkboxes, identity form, state machine,
// orientation warning modal, success card, and error handling.
// 10 test cases.

import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — declared before component imports so vi.mock hoisting works
// ---------------------------------------------------------------------------

vi.mock("../../lib/api", () => ({
  default: {
    public: {
      getEvent: vi.fn(),
      createSignup: vi.fn(),
      orientationStatus: vi.fn(),
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
import EventDetailPage from "../public/EventDetailPage";

// ---------------------------------------------------------------------------
// Test fixtures
// ---------------------------------------------------------------------------

const ORIENTATION_SLOT = {
  id: "slot-orient-1",
  slot_type: "orientation",
  date: "2026-04-22",
  start_time: "2026-04-22T09:00:00",
  end_time: "2026-04-22T11:00:00",
  location: "Room 101",
  capacity: 20,
  filled: 5,
};

const PERIOD_SLOT = {
  id: "slot-period-1",
  slot_type: "period",
  date: "2026-04-23",
  start_time: "2026-04-23T13:00:00",
  end_time: "2026-04-23T15:00:00",
  location: "Room 202",
  capacity: 20,
  filled: 7,
};

const FULL_SLOT = {
  id: "slot-full-1",
  slot_type: "period",
  date: "2026-04-24",
  start_time: "2026-04-24T10:00:00",
  end_time: "2026-04-24T12:00:00",
  location: "Room 303",
  capacity: 10,
  filled: 10, // full
};

const MOCK_EVENT = {
  id: "evt-1",
  title: "CRISPR at Carpinteria HS",
  quarter: "spring",
  year: 2026,
  week_number: 5,
  school: "Carpinteria HS",
  module_slug: "crispr",
  start_date: "2026-04-22T00:00:00",
  end_date: "2026-04-28T00:00:00",
  slots: [ORIENTATION_SLOT, PERIOD_SLOT, FULL_SLOT],
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

/**
 * Render EventDetailPage with the event ID pre-populated in the route params.
 */
function renderDetailPage(eventId = "evt-1") {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/events/${eventId}`]}>
        <Routes>
          <Route path="/events/:eventId" element={<EventDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

/**
 * Fill in the identity form with valid data.
 */
async function fillIdentityForm() {
  await userEvent.type(screen.getByLabelText(/^first name$/i), "Alice");
  await userEvent.type(screen.getByLabelText(/^last name$/i), "Smith");
  await userEvent.type(screen.getByLabelText(/^email$/i), "alice@example.com");
  await userEvent.type(screen.getByLabelText(/^phone$/i), "(213) 867-5309");
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EventDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.public.getEvent.mockResolvedValue(MOCK_EVENT);
  });

  // -------------------------------------------------------------------------
  // Test 1: Renders slot cards with checkboxes when event data loads
  // -------------------------------------------------------------------------
  it("renders slot cards with checkboxes when event data loads", async () => {
    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText("CRISPR at Carpinteria HS")).toBeInTheDocument();
    });

    // Section headings
    expect(screen.getByText(/Orientation Slots/i)).toBeInTheDocument();
    expect(screen.getByText(/Period Slots/i)).toBeInTheDocument();

    // Checkboxes for the available slots
    const checkboxes = screen.getAllByRole("checkbox");
    expect(checkboxes.length).toBeGreaterThanOrEqual(2);
  });

  // -------------------------------------------------------------------------
  // Test 2: Checking a slot checkbox reveals the identity form
  // -------------------------------------------------------------------------
  it("reveals identity form when a slot checkbox is checked", async () => {
    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Orientation Slots/i)).toBeInTheDocument();
    });

    // Initially the form should not be visible
    expect(screen.queryByLabelText(/^first name$/i)).not.toBeInTheDocument();

    // Check the orientation slot checkbox (index 0, first enabled)
    const checkboxes = screen.getAllByRole("checkbox");
    const enabledCheckbox = checkboxes.find((cb) => !cb.disabled);
    expect(enabledCheckbox).toBeDefined();
    fireEvent.click(enabledCheckbox);

    // Form should now appear
    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/^last name$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^email$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^phone$/i)).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 3: Submitting with empty fields shows validation errors
  // -------------------------------------------------------------------------
  it("shows validation errors when submitting with empty fields", async () => {
    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Orientation Slots/i)).toBeInTheDocument();
    });

    // Click a slot to reveal form
    const checkboxes = screen.getAllByRole("checkbox");
    const enabledCheckbox = checkboxes.find((cb) => !cb.disabled);
    fireEvent.click(enabledCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    // Submit with empty fields
    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(screen.getByText(/first name is required/i)).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Test 4: Submitting with period slot + no orientation slot calls orientationStatus
  // -------------------------------------------------------------------------
  it("calls orientationStatus when period slot selected with no orientation slot", async () => {
    api.public.orientationStatus.mockResolvedValue({
      has_attended_orientation: true,
    });
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "vol-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
    });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Period Slots/i)).toBeInTheDocument();
    });

    // The checkboxes are ordered: orientation (index 0), period available (index 1), period full (index 2, disabled)
    // Select only the period slot (index 1) — no orientation slot selected
    const checkboxes = screen.getAllByRole("checkbox");
    const periodCheckbox = checkboxes[1]; // period slot (available, not full)
    expect(periodCheckbox).not.toBeDisabled();
    fireEvent.click(periodCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    await fillIdentityForm();

    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(api.public.orientationStatus).toHaveBeenCalledWith("alice@example.com");
    });
  });

  // -------------------------------------------------------------------------
  // Test 5: When orientationStatus returns false, orientation modal appears
  // -------------------------------------------------------------------------
  it("shows orientation modal when orientationStatus returns has_attended_orientation:false", async () => {
    api.public.orientationStatus.mockResolvedValue({
      has_attended_orientation: false,
      last_attended_at: null,
    });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Period Slots/i)).toBeInTheDocument();
    });

    // Select period slot only (index 1) — no orientation slot selected
    const checkboxes = screen.getAllByRole("checkbox");
    const periodCheckbox = checkboxes[1];
    expect(periodCheckbox).not.toBeDisabled();
    fireEvent.click(periodCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    await fillIdentityForm();

    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/have you completed orientation/i)
      ).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /yes, i have completed orientation/i })
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /no.*show me orientation/i })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 6: When orientationStatus returns true, skips modal and submits
  // -------------------------------------------------------------------------
  it("skips orientation modal when has_attended_orientation is true", async () => {
    api.public.orientationStatus.mockResolvedValue({
      has_attended_orientation: true,
    });
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "vol-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
    });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Period Slots/i)).toBeInTheDocument();
    });

    // Select period slot only (index 1) — no orientation slot selected
    const checkboxes = screen.getAllByRole("checkbox");
    const periodCheckbox = checkboxes[1];
    expect(periodCheckbox).not.toBeDisabled();
    fireEvent.click(periodCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    await fillIdentityForm();

    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    // Wait for signup to complete — orientation modal should NOT appear
    await waitFor(() => {
      expect(api.public.createSignup).toHaveBeenCalled();
    });

    expect(screen.queryByText(/have you completed orientation/i)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 7: Successful signup shows SignupSuccessCard with "Check your email!"
  // -------------------------------------------------------------------------
  it("shows success card with 'Check your email!' after successful signup", async () => {
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "vol-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
    });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Orientation Slots/i)).toBeInTheDocument();
    });

    // Select orientation slot (index 0) — no period check needed since orientation is included
    const checkboxes = screen.getAllByRole("checkbox");
    const orientCheckbox = checkboxes[0];
    expect(orientCheckbox).not.toBeDisabled();
    fireEvent.click(orientCheckbox);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    await fillIdentityForm();

    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(screen.getByText(/check your email/i)).toBeInTheDocument();
    });

    // "Thanks, Alice!" is split across elements; check the containing paragraph
    expect(
      screen.getByText((_, element) => {
        return (
          element?.tagName === "P" &&
          element.textContent.includes("Thanks,") &&
          element.textContent.includes("Alice")
        );
      })
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 8: Dismissing success card resets form to browse state
  // -------------------------------------------------------------------------
  it("resets form to browse state after dismissing success card", async () => {
    api.public.createSignup.mockResolvedValue({
      volunteer_id: "vol-1",
      signup_ids: ["sig-1"],
      magic_link_sent: true,
    });

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Orientation Slots/i)).toBeInTheDocument();
    });

    // Select orientation slot (index 0) — no orientation check triggered
    const checkboxes = screen.getAllByRole("checkbox");
    const enabledCb = checkboxes[0];
    expect(enabledCb).not.toBeDisabled();
    fireEvent.click(enabledCb);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    await fillIdentityForm();
    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(screen.getByText(/check your email/i)).toBeInTheDocument();
    });

    // Dismiss the success card
    fireEvent.click(screen.getByRole("button", { name: /done/i }));

    // Success card should be gone
    await waitFor(() => {
      expect(screen.queryByText(/check your email/i)).not.toBeInTheDocument();
    });

    // Identity form should be gone (no slots selected after reset)
    expect(screen.queryByLabelText(/^first name$/i)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Test 9: 429 error shows rate-limit toast message
  // -------------------------------------------------------------------------
  it("shows rate-limit toast message on 429 error", async () => {
    const rateErr = new Error("rate limited");
    rateErr.status = 429;
    api.public.createSignup.mockRejectedValue(rateErr);

    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Orientation Slots/i)).toBeInTheDocument();
    });

    // Select orientation slot (index 0) — no orientation check triggered
    const checkboxes = screen.getAllByRole("checkbox");
    const enabledCb = checkboxes[0];
    expect(enabledCb).not.toBeDisabled();
    fireEvent.click(enabledCb);

    await waitFor(() => {
      expect(screen.getByLabelText(/^first name$/i)).toBeInTheDocument();
    });

    await fillIdentityForm();
    fireEvent.click(screen.getByRole("button", { name: /sign up/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        expect.stringMatching(/too many submissions|please wait/i)
      );
    });
  });

  // -------------------------------------------------------------------------
  // Test 10: Full slots have disabled checkboxes
  // -------------------------------------------------------------------------
  it("renders disabled checkbox for full slots", async () => {
    renderDetailPage();

    await waitFor(() => {
      expect(screen.getByText(/Period Slots/i)).toBeInTheDocument();
    });

    // The FULL_SLOT is the last checkbox (index 2) and should be disabled
    const checkboxes = screen.getAllByRole("checkbox");
    // Find the disabled one (the full slot)
    const disabledCheckboxes = checkboxes.filter((cb) => cb.disabled);
    expect(disabledCheckboxes.length).toBe(1);
    expect(disabledCheckboxes[0]).toBeDisabled();

    // Also confirm "Full" text is shown in the slot list
    expect(screen.getByText("Full")).toBeInTheDocument();
  });
});
